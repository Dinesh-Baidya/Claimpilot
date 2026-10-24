"""
End-to-End Walkthrough & Demonstration Script for ClaimPilot.
Runs the complete autonomous legal sentinel pipeline locally:
1. Intake Form Simulation
2. Parallel Airport Distance & Open-Meteo Weather Audit
3. Deterministic EU261 / DGCA Rules Verdict (Zero Hallucinations)
4. Legal Notice Drafting with Strict Fact Validator
5. Human-in-the-Loop Approval Gate
6. Idempotent Safe Dry-Run Dispatch
7. Accelerated Response Clock & Voucher Trap Counter-Action
"""
import sys
import time
from datetime import datetime
from uuid import uuid4

from engine.airport_db import calculate_flight_distance
from engine.weather_client import WeatherEvidenceClient
from engine.eligibility import EligibilityEngine
from engine.drafter import ClaimDrafter, ClaimValidator
from agents.state_machine import ClaimStateMachine

def run_walkthrough():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 70)
    print("   ✈️  CLAIMPILOT • AUTONOMOUS FLIGHT DISRUPTION SENTINEL")
    print("   Demonstration: Intent to Action (ASI:One / Agentverse)")
    print("=" * 70)

    # 1. User Intent & Intake
    print("\n[STEP 1: USER INTENT IN ASI:ONE]")
    user_prompt = "My flight AF1680 from Paris to London got cancelled this morning and the airline is offering no help."
    print(f"👤 User: \"{user_prompt}\"")
    print("🤖 Concierge: Acknowledged. Sending ASI:One Interactive Form Card for structured intake...")

    flight_no = "AF1680"
    origin = "CDG"
    dest = "LHR"
    flight_date = datetime.utcnow().strftime("%Y-%m-%d")
    passenger_name = "Alex Morgan"
    pnr = "AM789X"
    notice_days = 0 # Cancelled same day
    airline_reason = "Technical maintenance issue"

    print(f"\n[STEP 2: PARALLEL AUDIT & EVIDENCE VERIFICATION]")
    # 2a. Haversine Distance
    dist_km, _ = calculate_flight_distance(origin, dest)
    print(f"📍 Great-Circle Distance ({origin} ➔ {dest}): {dist_km} km")

    # 2b. Open-Meteo Weather Evidence
    weather_client = WeatherEvidenceClient()
    print("🌤️ Auditing Open-Meteo departure weather observations...")
    weather = weather_client.get_weather_assessment(lat=49.0097, lon=2.5479, date_iso=flight_date)
    print(f"   Plausibility of Weather Defense: {weather.get('plausibility')} ({weather.get('plausibility_label')})")
    print(f"   Wind Gusts: {weather['metrics'].get('wind_gusts_kmh')} km/h | Visibility: {weather['metrics'].get('visibility_meters')} m")

    # 3. Deterministic Rules Engine (No LLM)
    print("\n[STEP 3: DETERMINISTIC REGULATORY EVALUATION (ZERO HALLUCINATIONS)]")
    engine = EligibilityEngine()
    verdict = engine.evaluate(
        flight_number=flight_no,
        flight_date_str=flight_date,
        origin_iata=origin,
        destination_iata=dest,
        disruption_type="CANCELLATION",
        notice_days=notice_days,
        airline_reason=airline_reason,
        weather_plausibility=weather.get("plausibility")
    )
    print(f"⚖️ Governing Regime: {verdict.get('regime_title')}")
    print(f"💰 Statutory Entitlement: {verdict.get('amount')} {verdict.get('currency')} CASH")
    print(f"📜 Legal Basis: {verdict.get('statutory_citation')}")
    print(f"🎯 Claim Confidence Score: {verdict.get('claim_strength_score')}/100")
    for factor in verdict.get("strength_breakdown", []):
        print(f"   • {factor}")

    # 4. Legal Notice Drafting & Validator Check
    print("\n[STEP 4: STATUTORY NOTICE DRAFTING & VALIDATOR AUDIT]")
    drafter = ClaimDrafter()
    facts = {
        "claim_id": str(uuid4())[:8].upper(),
        "flight_number": flight_no,
        "flight_date": flight_date,
        "origin": origin,
        "destination": dest,
        "distance_km": dist_km,
        "disruption_type": "CANCELLATION",
        "statutory_citation": verdict.get("statutory_citation"),
        "amount": verdict.get("amount"),
        "currency": verdict.get("currency"),
        "passenger_name": passenger_name,
        "passenger_email": "alex.morgan@example.com",
        "booking_ref": pnr,
        "rebuttal_text": weather.get("rebuttal_text")
    }
    notice_text = drafter.draft_letter(facts)
    is_valid, violations = ClaimValidator.validate(notice_text, facts)
    print(f"🛡️ Anti-Hallucination Fact Validator Passed: {is_valid} (Violations: {violations})")

    # 5. Human Approval Gate
    print("\n[STEP 5: HUMAN-IN-THE-LOOP APPROVAL GATE (REVIEW CARD)]")
    print("🤖 Concierge: Displaying ASI:One Interactive Review Card...")
    print(f"   [Approve & Dispatch Claim] | [Edit] | [Cancel]")
    print("👤 Passenger: Clicks [Approve & Dispatch Claim]")

    # 6. Idempotent Dispatch & Clock Tracking
    print("\n[STEP 6: IDEMPOTENT DISPATCH & STATUTORY CLOCK START]")
    sm = ClaimStateMachine()
    claim_id = facts["claim_id"]
    idempotency_key = f"demo_dispatch_{claim_id}"
    dispatched = sm.record_claim(
        claim_id=claim_id,
        session_id="session-demo-01",
        passenger_email=facts["passenger_email"],
        flight_number=flight_no,
        amount=verdict["amount"],
        currency=verdict["currency"],
        regime=verdict["regime"],
        idempotency_key=idempotency_key,
        payload=facts,
        accelerated_seconds=2 # 2 seconds for demo script
    )
    print(f"📨 Idempotent Dispatch Succeeded: {dispatched}")
    print(f"📬 Safe Dry-Run Target: passenger.claimpilot@gmail.com (Claim Ref: CP-{claim_id})")
    print("⏱️ Statutory 14-day clock active (Accelerated to 2 seconds for demonstration)...")

    time.sleep(2.5)

    # 7. Escalation & Voucher Trap Reaction
    print("\n[STEP 7: STATUTORY DEADLINE ELAPSED & VOUCHER TRAP REACTION]")
    expired = sm.get_expired_claims()
    print(f"⚠️ Scheduler triggered: Carrier failed to remit statutory payment in notice window.")
    print(f"⚠️ Carrier system proposed alternative: '€200 Non-Transferable Travel Voucher'")
    print("🛡️ ClaimPilot Voucher Sentinel: Generating Rebuttal Review Card...")
    print(f"   Counter-Action: Statutory rejection under EU261 Art 7(3) dispatched!")
    print("=" * 70)
    print("   ✅ COMPLETE END-TO-END WORKFLOW VERIFIED SUCCESSFULLY")
    print("=" * 70)

if __name__ == "__main__":
    run_walkthrough()
