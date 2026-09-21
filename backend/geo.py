"""Geographic coordinates, fan heatmap data, and tour routing intelligence.

Provides city coordinate mappings for top global streaming hubs and analyzes
geographic market opportunities ("Tour Deserts") by cross-referencing
listening city volumes against scheduled concert dates.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .models import ArtistProfile

# Top global music streaming hubs with verified coordinates
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    # India & South Asia
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "pune": (18.5204, 73.8567),
    "hyderabad": (17.3850, 78.4867),
    "kolkata": (22.5726, 88.3639),
    "chennai": (13.0827, 80.2707),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "chandigarh": (30.7333, 76.7794),
    "dhaka": (23.8103, 90.4125),
    "karachi": (24.8607, 67.0011),
    "lahore": (31.5497, 74.3436),
    "colombo": (6.9271, 79.8612),
    # Southeast Asia
    "jakarta": (-6.2088, 106.8456),
    "manila": (14.5995, 120.9842),
    "quezon city": (14.6760, 121.0437),
    "bangkok": (13.7563, 100.5018),
    "kuala lumpur": (3.1390, 101.6869),
    "singapore": (1.3521, 103.8198),
    "ho chi minh city": (10.8231, 106.6297),
    "hanoi": (21.0285, 105.8542),
    # East Asia
    "tokyo": (35.6762, 139.6503),
    "osaka": (34.6937, 135.5023),
    "seoul": (37.5665, 126.9780),
    "taipei": (25.0330, 121.5654),
    "hong kong": (22.3193, 114.1694),
    # Europe
    "london": (51.5074, -0.1278),
    "manchester": (53.4808, -2.2426),
    "birmingham": (52.4862, -1.8904),
    "glasgow": (55.8642, -4.2518),
    "dublin": (53.3498, -6.2603),
    "paris": (48.8566, 2.3522),
    "berlin": (52.5200, 13.4050),
    "munich": (48.1351, 11.5820),
    "hamburg": (53.5511, 9.9937),
    "amsterdam": (52.3676, 4.9041),
    "rotterdam": (51.9244, 4.4777),
    "brussels": (50.8503, 4.3517),
    "madrid": (40.4168, -3.7038),
    "barcelona": (41.3879, 2.1699),
    "rome": (41.9028, 12.4964),
    "milan": (45.4642, 9.1900),
    "stockholm": (59.3293, 18.0686),
    "oslo": (59.9139, 10.7522),
    "copenhagen": (55.6761, 12.5683),
    "helsinki": (60.1699, 24.9384),
    "vienna": (48.2082, 16.3738),
    "zurich": (47.3769, 8.5417),
    "warsaw": (52.2297, 21.0122),
    "prague": (50.0755, 14.4378),
    "budapest": (47.4979, 19.0402),
    "istanbul": (41.0082, 28.9784),
    "athens": (37.9838, 23.7275),
    # North America
    "new york": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "houston": (29.7604, -95.3698),
    "atlanta": (33.7490, -84.3880),
    "toronto": (43.6532, -79.3832),
    "montreal": (45.5017, -73.5673),
    "vancouver": (49.2827, -123.1207),
    "nashville": (36.1627, -86.7816),
    "austin": (30.2672, -97.7431),
    "seattle": (47.6062, -122.3321),
    "san francisco": (37.7749, -122.4194),
    "miami": (25.7617, -80.1918),
    "boston": (42.3601, -71.0589),
    "philadelphia": (39.9526, -75.1652),
    "denver": (39.7392, -104.9903),
    "dallas": (32.7767, -96.7970),
    "mexico city": (19.4326, -99.1332),
    "guadalajara": (20.6597, -103.3496),
    "monterrey": (25.6866, -100.3161),
    # Latin America
    "sao paulo": (-23.5505, -46.6333),
    "são paulo": (-23.5505, -46.6333),
    "rio de janeiro": (-22.9068, -43.1729),
    "buenos aires": (-34.6037, -58.3816),
    "santiago": (-33.4489, -70.6693),
    "bogota": (4.7110, -74.0721),
    "bogotá": (4.7110, -74.0721),
    "lima": (-12.0464, -77.0428),
    # Oceania
    "sydney": (-33.8688, 151.2093),
    "melbourne": (-37.8136, 144.9631),
    "brisbane": (-27.4698, 153.0251),
    "auckland": (-36.8485, 174.7633),
    # Middle East & Africa
    "dubai": (25.2048, 55.2708),
    "cairo": (30.0444, 31.2357),
    "johannesburg": (-26.2041, 28.0473),
    "cape town": (-33.9249, 18.4241),
    "nairobi": (-1.2921, 36.8219),
    "lagos": (6.5244, 3.3792),
}


def get_city_coordinates(city_name: str) -> Optional[tuple[float, float]]:
    """Return (latitude, longitude) for a city name, or None if unknown."""
    if not city_name:
        return None
    key = city_name.strip().lower()
    # Direct match
    if key in CITY_COORDINATES:
        return CITY_COORDINATES[key]
    # Substring match (e.g. "London, UK" -> "london")
    for known_city, coords in CITY_COORDINATES.items():
        if known_city in key or key in known_city:
            return coords
    return None


def haversine_km(coord1: tuple[float, float], coord2: tuple[float, float]) -> float:
    """Calculate distance in kilometers between two lat/lon coordinates."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    radius = 6371.0  # Earth radius in km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius * c


def analyze_tour_opportunities(profile: ArtistProfile) -> dict[str, Any]:
    """
    Cross-reference top listening cities against scheduled concerts to discover
    high-potential unserved markets ("Tour Deserts") and routing suggestions.
    """
    # 1. Geocode Top Listening Cities
    geocoded_cities = []
    for c in profile.top_cities:
        coords = get_city_coordinates(c.city)
        geocoded_cities.append({
            "city": c.city,
            "country": c.country,
            "region": c.region,
            "listeners": c.listeners or 0,
            "lat": coords[0] if coords else None,
            "lon": coords[1] if coords else None,
        })

    # 2. Geocode Upcoming Concerts
    geocoded_events = []
    for e in profile.events:
        coords = get_city_coordinates(e.city or "")
        geocoded_events.append({
            "title": e.title,
            "city": e.city,
            "start_date": e.start_date,
            "lat": coords[0] if coords else None,
            "lon": coords[1] if coords else None,
        })

    # 3. Identify Tour Opportunities (Cities with high audience but no tour stop within 350km)
    opportunities = []
    event_coords = [
        (e["lat"], e["lon"])
        for e in geocoded_events
        if e["lat"] is not None and e["lon"] is not None
    ]

    for city in geocoded_cities:
        if city["lat"] is None or city["lon"] is None:
            continue

        c_coords = (city["lat"], city["lon"])
        # Check closest scheduled event
        min_dist = float("inf")
        closest_event = None
        for ev in geocoded_events:
            if ev["lat"] is not None and ev["lon"] is not None:
                dist = haversine_km(c_coords, (ev["lat"], ev["lon"]))
                if dist < min_dist:
                    min_dist = dist
                    closest_event = ev

        is_served = min_dist <= 350.0  # within 350km
        opportunity_score = "High" if city["listeners"] >= 100000 else "Medium"
        recommended_venue = (
            "3,000–5,000 capacity arena/hall"
            if city["listeners"] >= 200000
            else "1,000–2,500 capacity theater/club"
            if city["listeners"] >= 50000
            else "500–1,000 capacity boutique venue"
        )

        if not is_served:
            opportunities.append({
                "city": city["city"],
                "country": city["country"],
                "listeners": city["listeners"],
                "lat": city["lat"],
                "lon": city["lon"],
                "opportunity_score": opportunity_score,
                "recommended_capacity": recommended_venue,
                "reason": (
                    f"Strong concentration of {city['listeners']:,} monthly listeners "
                    f"with 0 concerts within 350km."
                ),
            })

    # Summary insight
    if opportunities:
        top_opp = opportunities[0]
        insight_headline = (
            f"Prime Tour Target: {top_opp['city']} ({top_opp['listeners']:,} listeners)"
        )
        insight_detail = (
            f"An untapped audience hub of {top_opp['listeners']:,} monthly listeners "
            f"exists in {top_opp['city']} without scheduled shows. Ideal for a {top_opp['recommended_capacity']}."
        )
    else:
        insight_headline = "Balanced Tour Distribution"
        insight_detail = "Existing tour schedule aligns well with audience geographic concentrations."

    return {
        "artist_name": profile.name,
        "cities": geocoded_cities,
        "events": geocoded_events,
        "opportunities": opportunities,
        "insight_headline": insight_headline,
        "insight_detail": insight_detail,
    }
