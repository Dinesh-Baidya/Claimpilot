"""
Configuration and Environment Settings for ClaimPilot.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# Agentverse & Network Config
AGENT_NAME = os.getenv("AGENT_NAME", "claimpilot_concierge")
AGENT_SEED = os.getenv("AGENT_SEED", "claimpilot_secret_seed_flight_sentinel_2026")
AGENTVERSE_MAILBOX_KEY = os.getenv("AGENTVERSE_MAILBOX_KEY", "")

# LLM Keys (Gemini or ASI1 API)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ASI1_API_KEY = os.getenv("ASI1_API_KEY", "")

# Operational Flags
DEMO_MODE = os.getenv("DEMO_MODE", "True").lower() in ("true", "1", "yes")
ACCELERATED_CLOCK_SECONDS = int(os.getenv("ACCELERATED_CLOCK_SECONDS", "30")) # 30s instead of 14 days
DRY_RUN_EMAIL = os.getenv("DRY_RUN_EMAIL", "passenger.claimpilot@gmail.com")

# Mock Carrier Registry for Multi-Leg Disambiguation Carousel
CARRIER_FLIGHTS = {
    "AF1680": {"carrier": "Air France", "origin": "CDG", "destination": "LHR", "sched_dep": "10:30 UTC", "distance_km": 348, "status": "CANCELLED"},
    "6E205":  {"carrier": "IndiGo", "origin": "DEL", "destination": "AMD", "sched_dep": "07:15 IST", "distance_km": 760, "status": "CANCELLED"},
    "AI803":  {"carrier": "Air India", "origin": "DEL", "destination": "BLR", "sched_dep": "06:00 IST", "distance_km": 1740, "status": "CANCELLED"},
    "IB3140": {"carrier": "Iberia", "origin": "MAD", "destination": "WAW", "sched_dep": "14:00 CET", "distance_km": 2270, "status": "DELAYED (4.2h)"},
    "LH102":  {"carrier": "Lufthansa", "origin": "FRA", "destination": "MUC", "sched_dep": "16:45 CET", "distance_km": 300, "status": "CANCELLED"}
}
