"""
Utility script to export all 4 interactive card payloads as JSON files.
These can be directly pasted into the ASI:One Card Playground at:
https://asi1.ai/developer/card-playground or tested on Agentverse.
"""
import json
from pathlib import Path
from cards.templates import (
    build_intake_form_card,
    build_flight_carousel_card,
    build_evidence_detail_card,
    build_human_review_card,
    build_voucher_trap_card
)

OUT_DIR = Path(__file__).parent / "playground_samples"
OUT_DIR.mkdir(exist_ok=True)

def export_samples():
    sample_flight_matches = [
        {"id": "leg-1", "flight_number": "AF1680", "origin": "CDG", "destination": "LHR", "sched_dep": "10:30 UTC", "carrier": "Air France", "distance_km": 348, "status": "CANCELLED"},
        {"id": "leg-2", "flight_number": "BA307", "origin": "CDG", "destination": "LHR", "sched_dep": "14:15 UTC", "carrier": "British Airways", "distance_km": 348, "status": "ON TIME"}
    ]

    sample_verdict = {
        "regime": "EU261",
        "regime_title": "Regulation (EC) No 261/2004",
        "is_eligible": True,
        "amount": 250,
        "currency": "EUR",
        "band_description": "Band 1 (<= 1,500 km)",
        "statutory_citation": "Article 7(1)(a) of Regulation (EC) No 261/2004",
        "claim_strength_score": 85
    }

    sample_weather = {
        "plausibility": "LOW",
        "plausibility_label": "Benign Operational Weather",
        "metrics": {"wind_gusts_kmh": 18, "visibility_meters": 10000, "weather_condition": "Standard"},
        "rebuttal_text": "Independent Open-Meteo reanalysis confirms standard operating conditions at departure.",
        "attribution": "Open-Meteo.com (CC BY 4.0)"
    }

    cards = {
        "1_intake_form.json": json.loads(build_intake_form_card().metadata["card_payload"]),
        "2_flight_carousel.json": json.loads(build_flight_carousel_card(sample_flight_matches).metadata["card_payload"]),
        "3_evidence_detail.json": json.loads(build_evidence_detail_card(sample_verdict, sample_weather).metadata["card_payload"]),
        "4_human_review.json": json.loads(build_human_review_card("CP-DEMO-01", "Alex Morgan", "€250 EUR CASH", "passenger@demo.com").metadata["card_payload"]),
        "5_voucher_trap_review.json": json.loads(build_voucher_trap_card("CP-DEMO-01", "€200 Travel Credit", "€250 EUR Cash").metadata["card_payload"]),
    }

    for fname, payload in cards.items():
        target = OUT_DIR / fname
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"Exported: {target}")

if __name__ == "__main__":
    export_samples()
