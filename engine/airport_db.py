"""
Airport Database and Great-Circle Distance Calculator using the Haversine formula.
Coordinates derived from OurAirports public datasets.
"""
import math
from typing import Dict, Optional, Tuple

AIRPORT_DATABASE: Dict[str, Dict] = {
    # Europe (EU / EEA / UK)
    "LHR": {"name": "London Heathrow", "city": "London", "country": "GB", "lat": 51.4700, "lon": -0.4543, "is_eu": False},
    "LGW": {"name": "London Gatwick", "city": "London", "country": "GB", "lat": 51.1537, "lon": -0.1821, "is_eu": False},
    "CDG": {"name": "Paris Charles de Gaulle", "city": "Paris", "country": "FR", "lat": 49.0097, "lon": 2.5479, "is_eu": True},
    "ORY": {"name": "Paris Orly", "city": "Paris", "country": "FR", "lat": 48.7262, "lon": 2.3652, "is_eu": True},
    "FRA": {"name": "Frankfurt Airport", "city": "Frankfurt", "country": "DE", "lat": 50.0379, "lon": 8.5622, "is_eu": True},
    "MUC": {"name": "Munich Airport", "city": "Munich", "country": "DE", "lat": 48.3537, "lon": 11.7860, "is_eu": True},
    "AMS": {"name": "Amsterdam Schiphol", "city": "Amsterdam", "country": "NL", "lat": 52.3105, "lon": 4.7683, "is_eu": True},
    "MAD": {"name": "Adolfo Suárez Madrid–Barajas", "city": "Madrid", "country": "ES", "lat": 40.4839, "lon": -3.5680, "is_eu": True},
    "BCN": {"name": "Barcelona–El Prat", "city": "Barcelona", "country": "ES", "lat": 41.2974, "lon": 2.0833, "is_eu": True},
    "FCO": {"name": "Rome Fiumicino", "city": "Rome", "country": "IT", "lat": 41.8003, "lon": 12.2389, "is_eu": True},
    "DUB": {"name": "Dublin Airport", "city": "Dublin", "country": "IE", "lat": 53.4264, "lon": -6.2499, "is_eu": True},
    "VIE": {"name": "Vienna International", "city": "Vienna", "country": "AT", "lat": 48.1103, "lon": 16.5697, "is_eu": True},
    "ZRH": {"name": "Zurich Airport", "city": "Zurich", "country": "CH", "lat": 47.4582, "lon": 8.5555, "is_eu": True}, # EEA associated
    "BRU": {"name": "Brussels Airport", "city": "Brussels", "country": "BE", "lat": 50.9014, "lon": 4.4844, "is_eu": True},
    "CPH": {"name": "Copenhagen Airport", "city": "Copenhagen", "country": "DK", "lat": 55.6180, "lon": 12.6508, "is_eu": True},
    "LIS": {"name": "Lisbon Portela", "city": "Lisbon", "country": "PT", "lat": 38.7756, "lon": -9.1354, "is_eu": True},
    "ATH": {"name": "Athens International", "city": "Athens", "country": "GR", "lat": 37.9364, "lon": 23.9445, "is_eu": True},
    "WAW": {"name": "Warsaw Chopin", "city": "Warsaw", "country": "PL", "lat": 52.1672, "lon": 20.9679, "is_eu": True},
    "HEL": {"name": "Helsinki Vantaa", "city": "Helsinki", "country": "FI", "lat": 60.3172, "lon": 24.9633, "is_eu": True},

    # India (DGCA Jurisdiction)
    "DEL": {"name": "Indira Gandhi International", "city": "Delhi", "country": "IN", "lat": 28.5562, "lon": 77.1000, "is_eu": False},
    "BOM": {"name": "Chhatrapati Shivaji Maharaj International", "city": "Mumbai", "country": "IN", "lat": 19.0896, "lon": 72.8656, "is_eu": False},
    "BLR": {"name": "Kempegowda International", "city": "Bengaluru", "country": "IN", "lat": 13.1986, "lon": 77.7066, "is_eu": False},
    "MAA": {"name": "Chennai International", "city": "Chennai", "country": "IN", "lat": 12.9941, "lon": 80.1709, "is_eu": False},
    "HYD": {"name": "Rajiv Gandhi International", "city": "Hyderabad", "country": "IN", "lat": 17.2403, "lon": 78.4294, "is_eu": False},
    "CCU": {"name": "Netaji Subhash Chandra Bose International", "city": "Kolkata", "country": "IN", "lat": 22.6547, "lon": 88.4467, "is_eu": False},
    "COK": {"name": "Cochin International", "city": "Kochi", "country": "IN", "lat": 10.1520, "lon": 76.3920, "is_eu": False},
    "GOI": {"name": "Dabolim Airport", "city": "Goa", "country": "IN", "lat": 15.3808, "lon": 73.8314, "is_eu": False},
    "GOX": {"name": "Manohar International (Mopa)", "city": "Goa", "country": "IN", "lat": 15.7667, "lon": 73.8667, "is_eu": False},
    "AMD": {"name": "Sardar Vallabhbhai Patel International", "city": "Ahmedabad", "country": "IN", "lat": 23.0772, "lon": 72.6347, "is_eu": False},
    "PNQ": {"name": "Pune Airport", "city": "Pune", "country": "IN", "lat": 18.5821, "lon": 73.9197, "is_eu": False},
    "GAU": {"name": "Lokpriya Gopinath Bordoloi International", "city": "Guwahati", "country": "IN", "lat": 26.1061, "lon": 91.5859, "is_eu": False},

    # International / Transatlantic
    "JFK": {"name": "John F. Kennedy International", "city": "New York", "country": "US", "lat": 40.6413, "lon": -73.7781, "is_eu": False},
    "EWR": {"name": "Newark Liberty International", "city": "Newark", "country": "US", "lat": 40.6895, "lon": -74.1745, "is_eu": False},
    "DXB": {"name": "Dubai International", "city": "Dubai", "country": "AE", "lat": 25.2532, "lon": 55.3657, "is_eu": False},
    "SIN": {"name": "Singapore Changi", "city": "Singapore", "country": "SG", "lat": 1.3644, "lon": 103.9915, "is_eu": False},
}

def get_airport(iata: str) -> Optional[Dict]:
    """Retrieve airport metadata by 3-letter IATA code."""
    return AIRPORT_DATABASE.get(iata.upper().strip())

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Great-Circle distance between two coordinates in kilometers."""
    R = 6371.0 # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)

def calculate_flight_distance(origin_iata: str, dest_iata: str) -> Tuple[Optional[float], Optional[str]]:
    """Return distance in km and error message if code unknown."""
    orig = get_airport(origin_iata)
    dest = get_airport(dest_iata)
    if not orig:
        return None, f"Unknown origin airport IATA code: '{origin_iata}'"
    if not dest:
        return None, f"Unknown destination airport IATA code: '{dest_iata}'"
    dist = haversine_distance_km(orig["lat"], orig["lon"], dest["lat"], dest["lon"])
    return dist, None
