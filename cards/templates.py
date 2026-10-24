"""
ASI:One Interactive Card Schemas and Builder Functions.
Strictly implements the official uagents-core schemas for all 4 predefined card kinds:
1. Form Card: Passenger and flight intake
2. Carousel Card: Flight & route disambiguation
3. Detail Card: Evidence breakdown and claim strength score
4. Review Card: Human approval gate & Voucher trap counter-action
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from uagents_core.contrib.protocols.chat import ChatMessage, TextContent, MetadataContent
from uagents_core.contrib.protocols.chat.cards import (
    FormCardPayload, FormField, FormFieldOption,
    CarouselCardPayload, CarouselItem,
    DetailCardPayload, DetailSummaryRow,
    ReviewCardPayload, ReviewSummaryRow,
    CtaAction, create_card_content
)

def create_chat_message(narration: str, card_content: Optional[MetadataContent] = None) -> ChatMessage:
    """Helper to wrap narration text and optional interactive card into a ChatMessage."""
    content = [TextContent(type="text", text=narration)]
    if card_content:
        content.append(card_content)
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=content
    )

# -------------------------------------------------------------
# 1. INTAKE FORM CARD
# -------------------------------------------------------------
def build_intake_form_card(default_flight: str = "AF1680") -> MetadataContent:
    payload = FormCardPayload(
        title="ClaimPilot • Flight Disruption Intake",
        fields=[
            FormField(
                name="flight_number",
                kind="text",
                label="Flight Number (e.g. AF1680, 6E205, AI803)",
                required=True,
                placeholder="AF1680"
            ),
            FormField(
                name="flight_date",
                kind="text",
                label="Flight Date (YYYY-MM-DD)",
                required=True,
                placeholder=datetime.utcnow().strftime("%Y-%m-%d")
            ),
            FormField(
                name="booking_ref",
                kind="text",
                label="Booking Reference (6-character PNR)",
                required=True,
                placeholder="AB12CD"
            ),
            FormField(
                name="passenger_name",
                kind="text",
                label="Passenger Full Name",
                required=True,
                placeholder="Alex Morgan"
            ),
            FormField(
                name="passenger_email",
                kind="email",
                label="Notification Email",
                required=True,
                placeholder="passenger@example.com"
            ),
            FormField(
                name="disruption_type",
                kind="select",
                label="Disruption Type",
                required=True,
                options=[
                    FormFieldOption(value="CANCELLATION", label="Flight Cancelled"),
                    FormFieldOption(value="DELAY", label="Flight Delayed (3+ Hours)")
                ]
            ),
            FormField(
                name="notice_days",
                kind="select",
                label="Advance Notice Communicated",
                required=True,
                options=[
                    FormFieldOption(value="0", label="Less than 24 hours / Same Day"),
                    FormFieldOption(value="3", label="1 to 7 Days"),
                    FormFieldOption(value="10", label="7 to 14 Days"),
                    FormFieldOption(value="18", label="More than 14 Days")
                ]
            ),
            FormField(
                name="airline_reason",
                kind="text",
                label="Airline Stated Reason",
                required=False,
                placeholder="e.g. Technical defect, Severe weather, Operational"
            )
        ],
        submit_cta=CtaAction(
            label="⚖️ Evaluate Claim & Check Weather",
            selection={"action": "SUBMIT_INTAKE"},
            primary=True
        )
    )
    return create_card_content(payload, card_id=uuid4(), is_terminal=False)

# -------------------------------------------------------------
# 2. CAROUSEL CARD (Disambiguation)
# -------------------------------------------------------------
def build_flight_carousel_card(flight_matches: List[Dict[str, Any]]) -> MetadataContent:
    items = []
    for f in flight_matches:
        items.append(
            CarouselItem(
                id=f["id"],
                title=f"{f['flight_number']} • {f['origin']} ➔ {f['destination']}",
                subtitle=f"Scheduled: {f['sched_dep']} | Airline: {f['carrier']}",
                secondary_text=f"Distance: {f['distance_km']} km | Status: {f['status']}",
                primary_cta=CtaAction(
                    label="Select This Leg",
                    selection={"action": "SELECT_LEG", "selected_flight_id": f["id"]},
                    primary=True
                )
            )
        )

    payload = CarouselCardPayload(
        title="Disambiguation • Select Disrupted Leg",
        subtitle="Multiple matched legs found on this date. Select the disrupted flight.",
        items=items
    )
    return create_card_content(payload, card_id=uuid4(), is_terminal=False)

# -------------------------------------------------------------
# 3. EVIDENCE & VERDICT DETAIL CARD
# -------------------------------------------------------------
def build_evidence_detail_card(verdict: Dict[str, Any], weather: Dict[str, Any]) -> MetadataContent:
    metrics = weather.get("metrics", {})
    weather_summary = (
        f"Wind gusts: {metrics.get('wind_gusts_kmh', 18)} km/h | "
        f"Visibility: {metrics.get('visibility_meters', 10000)}m | "
        f"Condition: {metrics.get('weather_condition', 'Standard')}"
    )

    amount_str = f"{verdict.get('amount')} {verdict.get('currency')}" if verdict.get("is_eligible") else "0 (Ineligible)"
    badge_title = "VERDICT: ELIGIBLE FOR CASH COMPENSATION" if verdict.get("is_eligible") else "VERDICT: REFUND / ALTERNATE ONLY"

    summary_rows = [
        DetailSummaryRow(label="Statutory Entitlement", value=f"{amount_str} ({verdict.get('band_description', '')})"),
        DetailSummaryRow(label="Governing Regulation", value=verdict.get("regime_title", "")),
        DetailSummaryRow(label="Statutory Legal Basis", value=verdict.get("statutory_citation", "")),
        DetailSummaryRow(label="Claim Strength Score", value=f"{verdict.get('claim_strength_score', 80)}/100 (HIGH PROBABILITY)"),
        DetailSummaryRow(label="Weather Plausibility", value=f"{weather.get('plausibility', 'LOW')} ({weather.get('plausibility_label', 'Benign Operational Weather')})"),
        DetailSummaryRow(label="Meteorological Audit", value=weather_summary),
        DetailSummaryRow(label="Carrier Burden of Proof", value="Airline carries statutory burden to prove unavoidable extraordinary conditions"),
        DetailSummaryRow(label="Data Source Attribution", value="Open-Meteo.com (CC BY 4.0)")
    ]

    payload = DetailCardPayload(
        title=f"ClaimPilot Audit • {badge_title}",
        summary_rows=summary_rows,
        ctas=[
            CtaAction(
                label="📝 Proceed to Review Formal Legal Notice",
                selection={"action": "PROCEED_TO_DRAFT"},
                primary=True
            )
        ]
    )
    return create_card_content(payload, card_id=uuid4(), is_terminal=False)

# -------------------------------------------------------------
# 4. HUMAN APPROVAL GATE REVIEW CARD
# -------------------------------------------------------------
def build_human_review_card(
    claim_id: str,
    passenger_name: str,
    amount_str: str,
    dry_run_recipient: str
) -> MetadataContent:
    summary_rows = [
        ReviewSummaryRow(label="Claim Reference", value=f"CP-{claim_id}"),
        ReviewSummaryRow(label="Claimant Passenger", value=passenger_name),
        ReviewSummaryRow(label="Demanded Statutory Amount", value=amount_str),
        ReviewSummaryRow(label="Settlement Mandate", value="Direct Cash/Wire Transfer (No Vouchers)"),
        ReviewSummaryRow(label="Dispatcher Route", value=f"Dry-Run Safe Mode (Routes to {dry_run_recipient})"),
        ReviewSummaryRow(label="Statutory Clock", value="14 Calendar Days to Settlement")
    ]

    payload = ReviewCardPayload(
        title="Human-in-the-Loop Claim Approval Gate",
        summary_rows=summary_rows,
        approve_cta=CtaAction(
            label="🚀 Approve & Dispatch Notice to Airline",
            selection={"action": "APPROVE_AND_DISPATCH", "claim_id": claim_id},
            primary=True
        ),
        reject_cta=CtaAction(
            label="❌ Cancel Claim",
            selection={"action": "CANCEL_CLAIM", "claim_id": claim_id},
            primary=False
        )
    )
    return create_card_content(payload, card_id=uuid4(), is_terminal=False)

# -------------------------------------------------------------
# 5. VOUCHER TRAP REVIEW CARD
# -------------------------------------------------------------
def build_voucher_trap_card(claim_id: str, voucher_amount: str, statutory_cash: str) -> MetadataContent:
    summary_rows = [
        ReviewSummaryRow(label="⚠️ Detection", value="Airline Proposed Non-Statutory Travel Voucher"),
        ReviewSummaryRow(label="Carrier Offer", value=voucher_amount),
        ReviewSummaryRow(label="Statutory Right", value=f"{statutory_cash} Cash / Wire Transfer"),
        ReviewSummaryRow(label="Governing Law", value="EU261 Art 7(3) & DGCA CAR M IV require monetary payment")
    ]

    payload = ReviewCardPayload(
        title="⚠️ Airline Voucher Trap Detected!",
        summary_rows=summary_rows,
        approve_cta=CtaAction(
            label="⚖️ Reject Voucher & Demand Statutory Cash",
            selection={"action": "REJECT_VOUCHER_DEMAND_CASH", "claim_id": claim_id},
            primary=True
        ),
        reject_cta=CtaAction(
            label="Accept Airline Voucher",
            selection={"action": "ACCEPT_VOUCHER", "claim_id": claim_id},
            primary=False
        )
    )
    return create_card_content(payload, card_id=uuid4(), is_terminal=False)
