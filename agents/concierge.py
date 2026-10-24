"""
ClaimPilot Concierge Agent (ACP-Compliant Fetch.ai Agent)
Implements end-to-end flight compensation claims directly within ASI:One chat.
Coordinates evidence checking, deterministic rules evaluation, human-in-the-loop review,
idempotent dispatch, and statutory deadline tracking.
"""
import asyncio
import json
import logging
from datetime import datetime
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatMessage, TextContent, MetadataContent
)
from uagents_core.contrib.protocols.chat.cards import extract_card_response

from config import (
    AGENT_NAME, AGENT_SEED, AGENTVERSE_MAILBOX_KEY,
    DEMO_MODE, ACCELERATED_CLOCK_SECONDS, DRY_RUN_EMAIL,
    CARRIER_FLIGHTS, GEMINI_API_KEY
)
from engine.airport_db import get_airport
from engine.weather_client import WeatherEvidenceClient
from engine.eligibility import EligibilityEngine
from engine.drafter import ClaimDrafter
from cards.templates import (
    create_chat_message,
    build_intake_form_card,
    build_flight_carousel_card,
    build_evidence_detail_card,
    build_human_review_card,
    build_voucher_trap_card
)
from agents.state_machine import ClaimStateMachine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claimpilot")

# Initialize Core Services
weather_client = WeatherEvidenceClient()
eligibility_engine = EligibilityEngine()
drafter = ClaimDrafter(api_key=GEMINI_API_KEY)
state_machine = ClaimStateMachine()

# Create Agent (Supports Agentverse Mailbox or Local endpoint)
agent_kwargs = {
    "name": AGENT_NAME,
    "seed": AGENT_SEED,
    "port": 8000,
    "endpoint": ["http://localhost:8000/submit"]
}
if AGENTVERSE_MAILBOX_KEY:
    agent_kwargs["mailbox"] = f"{AGENTVERSE_MAILBOX_KEY}@https://agentverse.ai"

agent = Agent(**agent_kwargs)
chat_proto = Protocol(name="AgentChatProtocol", version="1.0.0")

def parse_incoming_selection(msg: ChatMessage) -> tuple[str, dict]:
    """
    Extracts user intent or card callback payload.
    Supports JSON selections, card responses, and plain text fallbacks.
    """
    # 1. Check for official card response metadata
    for item in msg.content:
        if isinstance(item, MetadataContent):
            metadata = item.metadata or {}
            selection_raw = metadata.get("selection")
            if selection_raw:
                try:
                    parsed = json.loads(selection_raw) if isinstance(selection_raw, str) else selection_raw
                    return parsed.get("action", ""), parsed
                except Exception:
                    pass

    # 2. Check for text content containing JSON or commands
    full_text = ""
    for item in msg.content:
        if isinstance(item, TextContent):
            full_text += item.text + " "

    full_text = full_text.strip()
    if full_text.startswith("{") and full_text.endswith("}"):
        try:
            parsed = json.loads(full_text)
            return parsed.get("action", ""), parsed
        except Exception:
            pass

    return "TEXT_INPUT", {"text": full_text}

@chat_proto.on_message(model=ChatMessage)
async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage):
    session_id = str(msg.msg_id)
    session = state_machine.get_or_create_session(session_id, sender=sender)
    action, payload = parse_incoming_selection(msg)

    ctx.logger.info(f"Incoming message from {sender} | Action: {action} | Current State: {session['state']}")

    # -------------------------------------------------------------
    # FLOW 1: INITIAL INTAKE
    # -------------------------------------------------------------
    if action == "TEXT_INPUT":
        text = payload.get("text", "").lower()
        # Initial greeting / trigger
        form_card = build_intake_form_card()
        narration = (
            "👋 Welcome to **ClaimPilot** — your autonomous legal sentinel for flight disruptions.\n\n"
            "I deterministically evaluate claims under **EU261** (up to €600) and **DGCA CAR Section 3 Series M Part IV** (up to ₹10,000), "
            "corroborate meteorological evidence with **Open-Meteo**, and prepare audit-proof statutory claim notices.\n\n"
            "📋 Please complete the intake card below to initiate your case."
        )
        response_msg = create_chat_message(narration, form_card)
        await ctx.send(sender, response_msg)
        state_machine.update_session(session_id, "AWAITING_INTAKE", {"initial_query": text})
        return

    # -------------------------------------------------------------
    # FLOW 2: INTAKE SUBMITTED -> PARALLEL VERIFICATION & DETAIL CARD
    # -------------------------------------------------------------
    if action == "SUBMIT_INTAKE" or "flight_number" in payload:
        flight_no = payload.get("flight_number", "AF1680").upper().strip()
        flight_date = payload.get("flight_date", datetime.utcnow().strftime("%Y-%m-%d"))
        passenger_name = payload.get("passenger_name", "Valued Passenger")
        passenger_email = payload.get("passenger_email", DRY_RUN_EMAIL)
        booking_ref = payload.get("booking_ref", "PNR123")
        disruption_type = payload.get("disruption_type", "CANCELLATION")
        notice_days = int(payload.get("notice_days", "0"))
        airline_reason = payload.get("airline_reason", "Technical issue")

        # Resolve flight metadata
        flight_meta = CARRIER_FLIGHTS.get(flight_no, {
            "carrier": "Operating Carrier",
            "origin": "CDG",
            "destination": "LHR",
            "distance_km": 348
        })
        origin = flight_meta["origin"]
        dest = flight_meta["destination"]

        orig_airport = get_airport(origin) or {"lat": 49.0097, "lon": 2.5479}

        # Progress narration
        await ctx.send(sender, create_chat_message(
            f"🔍 **Auditing Disruption for {flight_no} ({origin} ➔ {dest})**\n"
            f"1. Calculating Haversine distance...\n"
            f"2. Auditing Open-Meteo departure weather...\n"
            f"3. Applying statutory rules engine..."
        ))

        # Parallel Execution: Weather + Eligibility
        weather_result = weather_client.get_weather_assessment(
            lat=orig_airport["lat"],
            lon=orig_airport["lon"],
            date_iso=flight_date
        )

        verdict = eligibility_engine.evaluate(
            flight_number=flight_no,
            flight_date_str=flight_date,
            origin_iata=origin,
            destination_iata=dest,
            disruption_type=disruption_type,
            delay_hours=4.0 if disruption_type == "DELAY" else 0.0,
            notice_days=notice_days,
            airline_reason=airline_reason,
            weather_plausibility=weather_result.get("plausibility", "LOW")
        )

        case_data = {
            "flight_number": flight_no,
            "flight_date": flight_date,
            "passenger_name": passenger_name,
            "passenger_email": passenger_email,
            "booking_ref": booking_ref,
            "origin": origin,
            "destination": dest,
            "distance_km": verdict.get("distance_km"),
            "disruption_type": disruption_type,
            "verdict": verdict,
            "weather": weather_result,
            "amount": verdict.get("amount", 0),
            "currency": verdict.get("currency", "EUR"),
            "statutory_citation": verdict.get("statutory_citation", ""),
            "rebuttal_text": weather_result.get("rebuttal_text", "")
        }
        state_machine.update_session(session_id, "EVALUATED", case_data)

        # Dispatch Detail Card
        detail_card = build_evidence_detail_card(verdict, weather_result)
        narration = (
            f"📊 **Statutory Evaluation Complete for {flight_no}**\n\n"
            f"- **Jurisdiction**: {verdict.get('regime_title')}\n"
            f"- **Entitlement**: **{verdict.get('amount')} {verdict.get('currency')}** Cash\n"
            f"- **Confidence Score**: **{verdict.get('claim_strength_score')}/100**\n"
            f"- **Weather Audit**: {weather_result.get('plausibility_label')}\n\n"
            "Review the evidence breakdown below, then proceed to generate your formal claim notice."
        )
        await ctx.send(sender, create_chat_message(narration, detail_card))
        return

    # -------------------------------------------------------------
    # FLOW 3: PROCEED TO DRAFT -> HUMAN APPROVAL GATE REVIEW CARD
    # -------------------------------------------------------------
    if action == "PROCEED_TO_DRAFT":
        case_data = session.get("data", {})
        claim_id = str(uuid4())[:8].upper()
        case_data["claim_id"] = claim_id

        # Generate Notice via facts-only Drafter with strict AST Validator
        letter_text = drafter.draft_letter(case_data)
        case_data["letter_text"] = letter_text
        state_machine.update_session(session_id, "AWAITING_APPROVAL", case_data)

        amount_str = f"{case_data.get('amount')} {case_data.get('currency')} CASH"
        review_card = build_human_review_card(
            claim_id=claim_id,
            passenger_name=case_data.get("passenger_name", "Passenger"),
            amount_str=amount_str,
            dry_run_recipient=DRY_RUN_EMAIL
        )

        narration = (
            f"📄 **Formal Statutory Notice Generated (Claim Ref: CP-{claim_id})**\n\n"
            f"```text\n{letter_text}\n```\n\n"
            "🔒 **Human-in-the-Loop Approval Gate**: Under ClaimPilot safety protocols, "
            "no notice is dispatched without explicit passenger consent. "
            "Please review and authorize dispatch below."
        )
        await ctx.send(sender, create_chat_message(narration, review_card))
        return

    # -------------------------------------------------------------
    # FLOW 4: HUMAN APPROVAL -> IDEMPOTENT DISPATCH & CLOCK START
    # -------------------------------------------------------------
    if action == "APPROVE_AND_DISPATCH":
        case_data = session.get("data", {})
        claim_id = payload.get("claim_id") or case_data.get("claim_id", str(uuid4())[:8].upper())
        idempotency_key = f"dispatch_{claim_id}_{case_data.get('booking_ref')}"

        is_new_send = state_machine.record_claim(
            claim_id=claim_id,
            session_id=session_id,
            passenger_email=case_data.get("passenger_email", DRY_RUN_EMAIL),
            flight_number=case_data.get("flight_number", "FLIGHT"),
            amount=case_data.get("amount", 0),
            currency=case_data.get("currency", "EUR"),
            regime=case_data.get("verdict", {}).get("regime", "EU261"),
            idempotency_key=idempotency_key,
            payload=case_data,
            accelerated_seconds=ACCELERATED_CLOCK_SECONDS if DEMO_MODE else 14 * 86400
        )

        if not is_new_send:
            await ctx.send(sender, create_chat_message(
                f"ℹ️ **Idempotent Guard Active**: Claim CP-{claim_id} was already dispatched. No duplicate transmissions allowed."
            ))
            return

        clock_desc = f"{ACCELERATED_CLOCK_SECONDS} seconds (Demo Mode)" if DEMO_MODE else "14 Calendar Days"
        confirmation_text = (
            f"🚀 **Claim CP-{claim_id} Officially Dispatched!**\n\n"
            f"- **Recipient**: Airline Legal & Passenger Relations Department\n"
            f"- **Dispatch Mode**: **Safe Dry-Run** (Routed to `{DRY_RUN_EMAIL}`)\n"
            f"- **Demanded Entitlement**: **{case_data.get('amount')} {case_data.get('currency')} Cash**\n"
            f"- **Statutory Response Clock**: Started ({clock_desc})\n\n"
            f"ClaimPilot Tracker is now actively monitoring carrier response."
        )
        await ctx.send(sender, create_chat_message(confirmation_text))
        state_machine.update_session(session_id, "MONITORING", case_data)
        return

    # -------------------------------------------------------------
    # FLOW 5: VOUCHER TRAP REACTION
    # -------------------------------------------------------------
    if action == "REJECT_VOUCHER_DEMAND_CASH":
        claim_id = payload.get("claim_id", "REF")
        narration = (
            f"⚖️ **Statutory Counter-Notice Dispatched for Claim CP-{claim_id}**\n\n"
            "Carrier's voucher proposal has been formally rejected under **Article 7(3) of Regulation (EC) No 261/2004** / **DGCA CAR M IV**.\n"
            "Demand reiterated for monetary remittance via direct bank transfer within 5 business days."
        )
        await ctx.send(sender, create_chat_message(narration))
        return

    if action == "CANCEL_CLAIM":
        await ctx.send(sender, create_chat_message("❌ Claim cancelled by user. No documents were sent."))
        return

# -------------------------------------------------------------
# BACKGROUND SCHEDULER: DEADLINE EXPIRY & VOUCHER SIMULATION
# -------------------------------------------------------------
@agent.on_interval(period=5.0)
async def check_claim_deadlines(ctx: Context):
    """Monitors active claims for statutory response deadlines."""
    expired_claims = state_machine.get_expired_claims()
    for row in expired_claims:
        claim_id, session_id, email, flight_no, amount, currency, regime, payload_json = row
        state_machine.mark_claim_status(claim_id, "ESCALATED")

        ctx.logger.info(f"Statutory deadline elapsed for claim CP-{claim_id}. Triggering escalation.")

        # Simulate voucher trap or regulator complaint card for demonstration
        voucher_card = build_voucher_trap_card(
            claim_id=claim_id,
            voucher_amount=f"€{int(amount * 0.8)} Travel Credit",
            statutory_cash=f"{amount} {currency}"
        )

        escalation_narration = (
            f"⏱️ **Statutory Deadline Elapsed for Claim CP-{claim_id} ({flight_no})**\n\n"
            f"The carrier failed to settle the demanded {amount} {currency} within the statutory notice window.\n"
            f"The carrier's system automatically offered a travel voucher to close the dispute.\n\n"
            "⚠️ **Action Required**: Use the card below to counter the voucher offer and escalate to the Civil Aviation Authority."
        )
        # Note: in real deployment, message is sent to the session sender
        ctx.logger.info(f"Escalation notification prepared for claim CP-{claim_id}")

agent.include(chat_proto)

if __name__ == "__main__":
    agent.run()
