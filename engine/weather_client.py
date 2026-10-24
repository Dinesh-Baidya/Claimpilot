"""
Weather Evidence Agent Client
Integrates with Open-Meteo (Non-commercial free tier, CC BY 4.0 attribution).
Analyzes weather conditions around flight departure times to determine
whether an airline's 'severe weather / extraordinary circumstance' defense is plausible.
"""
import datetime
import logging
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)

# WMO Weather interpretation codes (WW)
SEVERE_WEATHER_CODES = {
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm: Slight or moderate",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

class WeatherEvidenceClient:
    """Fetches Open-Meteo archive/forecast data and computes a weather plausibility score."""

    ATTRIBUTION = "Weather data provided by Open-Meteo.com (CC BY 4.0)"

    def __init__(self, timeout_sec: int = 5):
        self.timeout = timeout_sec
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get_weather_assessment(
        self,
        lat: float,
        lon: float,
        date_iso: str,
        departure_hour: int = 12
    ) -> Dict[str, Any]:
        """
        Query Open-Meteo for the flight location and date.
        Returns a standardized dictionary:
        {
            "ok": bool,
            "plausibility": "LOW" | "MEDIUM" | "HIGH",
            "plausibility_label": str,
            "metrics": dict,
            "rebuttal_text": str,
            "attribution": str,
            "source": str,
            "fetched_at": str
        }
        """
        cache_key = f"{round(lat, 2)}_{round(lon, 2)}_{date_iso}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        now = datetime.datetime.utcnow()
        fetched_at = now.isoformat() + "Z"

        # Determine whether to use archive or forecast API based on date age
        try:
            target_date = datetime.date.fromisoformat(date_iso)
            days_ago = (now.date() - target_date).days
        except Exception:
            days_ago = 0

        # Open-Meteo API endpoint
        if days_ago > 5:
            url = "https://archive-api.open-meteo.com/v1/archive"
        else:
            url = "https://api.open-meteo.com/v1/forecast"

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": date_iso,
            "end_date": date_iso,
            "hourly": "wind_speed_10m,wind_gusts_10m,visibility,precipitation,weather_code",
            "timezone": "UTC"
        }

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])

            # Target index around scheduled departure hour (UTC)
            idx = min(max(departure_hour, 0), len(times) - 1) if times else 0

            wind_speed = hourly.get("wind_speed_10m", [0])[idx] if hourly.get("wind_speed_10m") else 0
            wind_gusts = hourly.get("wind_gusts_10m", [0])[idx] if hourly.get("wind_gusts_10m") else 0
            visibility = hourly.get("visibility", [10000])[idx] if hourly.get("visibility") else 10000
            precipitation = hourly.get("precipitation", [0])[idx] if hourly.get("precipitation") else 0
            wmo_code = hourly.get("weather_code", [0])[idx] if hourly.get("weather_code") else 0

            # Score Plausibility of Weather Cancellation
            # HIGH = Severe conditions (gusts > 75 km/h, visibility < 600m, thunderstorm/heavy snow)
            # MEDIUM = Borderline (gusts 50-75 km/h, visibility 600m-2000m, moderate snow)
            # LOW = Benign / routine operational weather (airline's weather excuse is unfounded)
            is_thunderstorm = wmo_code in [95, 96, 99]
            is_heavy_snow = wmo_code in [75, 86]

            if (wind_gusts > 75) or (visibility < 600) or is_thunderstorm or is_heavy_snow:
                plausibility = "HIGH"
                label = "Severe Weather Detected"
                rebuttal = (
                    f"Independent meteorological records indicate adverse conditions (gusts: {wind_gusts} km/h, "
                    f"visibility: {visibility}m, WMO code: {wmo_code}). While severe weather occurred, the carrier "
                    "retains the statutory burden of demonstrating that other flights were grounded and all reasonable "
                    "countermeasures were exhausted."
                )
            elif (wind_gusts > 50) or (visibility < 2000) or (precipitation > 10):
                plausibility = "MEDIUM"
                label = "Moderate Weather Variations"
                rebuttal = (
                    f"Meteorological records indicate manageable conditions (gusts: {wind_gusts} km/h, visibility: "
                    f"{visibility}m). These figures remain within standard Category I/II ILS operating parameters, "
                    "suggesting routine operating conditions rather than extraordinary circumstances."
                )
            else:
                plausibility = "LOW"
                label = "Benign Operational Weather"
                rebuttal = (
                    f"Independent Open-Meteo reanalysis confirms optimal operating conditions at departure "
                    f"(gusts: {wind_gusts} km/h, visibility: {visibility}m, precipitation: {precipitation}mm, WMO code: {wmo_code}). "
                    "No meteorological impediments existed to justify an extraordinary circumstances defense under EU261 / DGCA."
                )

            result = {
                "ok": True,
                "plausibility": plausibility,
                "plausibility_label": label,
                "metrics": {
                    "wind_speed_kmh": wind_speed,
                    "wind_gusts_kmh": wind_gusts,
                    "visibility_meters": visibility,
                    "precipitation_mm": precipitation,
                    "wmo_code": wmo_code,
                    "weather_condition": SEVERE_WEATHER_CODES.get(wmo_code, "Normal / Clear to Overcast")
                },
                "rebuttal_text": rebuttal,
                "source": "Open-Meteo API",
                "attribution": self.ATTRIBUTION,
                "fetched_at": fetched_at,
                "error": None
            }
            self._cache[cache_key] = result
            return result

        except Exception as e:
            logger.warning(f"Weather query failed for {lat},{lon}: {e}. Falling back gracefully.")
            # Graceful degradation: do NOT block workflow if weather API fails
            fallback_result = {
                "ok": False,
                "plausibility": "UNAVAILABLE",
                "plausibility_label": "Weather Data Unavailable",
                "metrics": {},
                "rebuttal_text": "Independent weather verification temporarily unavailable. The carrier remains obligated under statutory provisions to supply certified dispatch logs.",
                "source": "Open-Meteo (Offline Fallback)",
                "attribution": self.ATTRIBUTION,
                "fetched_at": fetched_at,
                "error": str(e)
            }
            return fallback_result
