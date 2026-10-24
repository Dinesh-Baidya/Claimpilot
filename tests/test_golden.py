"""
Golden Case Unit Tests for EU261 and DGCA Determinations.
Verifies that statutory amounts, distance bands, and notice exemptions strictly match official regulations.
"""
import pytest
from engine.eligibility import EligibilityEngine

@pytest.fixture
def engine():
    return EligibilityEngine()

# --- EU261 Golden Tests ---

def test_eu261_band1_short_haul_cancellation(engine):
    """
    Flight CDG (Paris) to LHR (London), ~348 km.
    Cancelled with 2 days notice (less than 7 days).
    Expected: Eligible for Band 1 (€250).
    """
    verdict = engine.evaluate(
        flight_number="AF1680",
        flight_date_str="2026-06-15",
        origin_iata="CDG",
        destination_iata="LHR",
        disruption_type="CANCELLATION",
        notice_days=2,
        airline_reason="technical defect",
        weather_plausibility="LOW"
    )
    assert verdict["is_eligible"] is True
    assert verdict["regime"] == "EU261"
    assert verdict["amount"] == 250
    assert verdict["currency"] == "EUR"
    assert "Article 7(1)(a)" in verdict["statutory_citation"]

def test_eu261_band2_medium_haul_delay(engine):
    """
    Flight MAD (Madrid) to WAW (Warsaw), ~2270 km (intra-EU > 1500 km).
    Arrival delay of 4.2 hours.
    Expected: Eligible for Band 2 (€400) under Article 7(1)(b) & ECJ Sturgeon.
    """
    verdict = engine.evaluate(
        flight_number="LO434",
        flight_date_str="2026-07-10",
        origin_iata="MAD",
        destination_iata="WAW",
        disruption_type="DELAY",
        delay_hours=4.2,
        airline_reason="operational delay",
        weather_plausibility="LOW"
    )
    assert verdict["is_eligible"] is True
    assert verdict["amount"] == 400
    assert verdict["currency"] == "EUR"
    assert "Article 7(1)(b)" in verdict["statutory_citation"]

def test_eu261_band3_long_haul_cancellation(engine):
    """
    Flight CDG (Paris) to JFK (New York), ~5835 km (> 3500 km).
    Cancelled 1 day before departure.
    Expected: Eligible for Band 3 (€600).
    """
    verdict = engine.evaluate(
        flight_number="AF006",
        flight_date_str="2026-08-01",
        origin_iata="CDG",
        destination_iata="JFK",
        disruption_type="CANCELLATION",
        notice_days=1,
        airline_reason="crew shortage",
        weather_plausibility="LOW"
    )
    assert verdict["is_eligible"] is True
    assert verdict["amount"] == 600
    assert verdict["currency"] == "EUR"
    assert "Article 7(1)(c)" in verdict["statutory_citation"]

def test_eu261_exempt_with_14_days_notice(engine):
    """
    Flight FRA to MUC cancelled 18 days in advance.
    Expected: Ineligible for statutory cash compensation under Art 5(1)(c)(i).
    """
    verdict = engine.evaluate(
        flight_number="LH102",
        flight_date_str="2026-09-01",
        origin_iata="FRA",
        destination_iata="MUC",
        disruption_type="CANCELLATION",
        notice_days=18,
        airline_reason="schedule change"
    )
    assert verdict["is_eligible"] is False
    assert verdict["amount"] == 0
    assert verdict["remedy_type"] == "REFUND_OR_REROUTE_ONLY"

# --- DGCA Golden Tests (India) ---

def test_dgca_tier1_short_domestic_cancellation(engine):
    """
    Flight DEL (Delhi) to AMD (Ahmedabad), ~760 km (block time ~1.5h).
    Cancelled with 6 hours notice (< 24 hours).
    Expected: Eligible under DGCA CAR Section 3 Series M Part IV Tier 2 (INR 7,500).
    """
    verdict = engine.evaluate(
        flight_number="6E205",
        flight_date_str="2026-05-12",
        origin_iata="DEL",
        destination_iata="AMD",
        disruption_type="CANCELLATION",
        notice_days=0, # < 24h notice
        airline_reason="aircraft maintenance",
        weather_plausibility="LOW"
    )
    assert verdict["is_eligible"] is True
    assert verdict["regime"] == "DGCA_CAR_M_IV"
    assert verdict["amount"] == 7500
    assert verdict["currency"] == "INR"
    assert "DGCA CAR Section 3, Series M, Part IV" in verdict["statutory_citation"]

def test_dgca_tier3_long_domestic_cancellation(engine):
    """
    Flight DEL (Delhi) to BLR (Bengaluru), ~1740 km (block time > 2 hours).
    Cancelled with 3 hours notice (< 24 hours).
    Expected: Eligible for Tier 3 max cap (INR 10,000).
    """
    verdict = engine.evaluate(
        flight_number="AI803",
        flight_date_str="2026-05-20",
        origin_iata="DEL",
        destination_iata="BLR",
        disruption_type="CANCELLATION",
        notice_days=0,
        airline_reason="crew rostering",
        weather_plausibility="LOW"
    )
    assert verdict["is_eligible"] is True
    assert verdict["amount"] == 10000
    assert verdict["currency"] == "INR"

def test_dgca_cancellation_with_notice_over_24h(engine):
    """
    Flight BOM to DEL cancelled 3 days in advance (between 24h and 2 weeks).
    Expected: Alternate flight or refund, but no statutory cash penalty.
    """
    verdict = engine.evaluate(
        flight_number="UK992",
        flight_date_str="2026-06-01",
        origin_iata="BOM",
        destination_iata="DEL",
        disruption_type="CANCELLATION",
        notice_days=3,
        airline_reason="commercial reason"
    )
    assert verdict["is_eligible"] is False
    assert verdict["amount"] == 0
    assert verdict["remedy_type"] == "REFUND_OR_ALTERNATE_ONLY"
