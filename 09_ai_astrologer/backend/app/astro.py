"""Natal chart calculation using pyswisseph (Swiss Ephemeris)."""

import math
from datetime import datetime

import swisseph as swe

from app.models import BirthData, NatalChart

PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Uranus": swe.URANUS,
    "Neptune": swe.NEPTUNE,
    "Pluto": swe.PLUTO,
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

ASPECT_TYPES = {
    "Conjunction": 0.0,
    "Opposition": 180.0,
    "Trine": 120.0,
    "Square": 90.0,
    "Sextile": 60.0,
}

ASPECT_ORBS = {
    "Conjunction": 8.0,
    "Opposition": 8.0,
    "Trine": 6.0,
    "Square": 6.0,
    "Sextile": 4.0,
}


def _degree_to_sign(degree: float) -> str:
    """Convert ecliptic degree to zodiac sign."""
    sign_index = int(degree / 30) % 12
    return SIGNS[sign_index]


def _degree_in_sign(degree: float) -> float:
    """Get the degree position within the sign (0-30)."""
    return degree % 30


def _get_house_number(degree: float, cusps: list[float]) -> int:
    """Determine which house a planet is in based on house cusps."""
    for i in range(12):
        cusp_start = cusps[i]
        cusp_end = cusps[(i + 1) % 12]
        if cusp_start <= cusp_end:
            if cusp_start <= degree < cusp_end:
                return i + 1
        else:
            if degree >= cusp_start or degree < cusp_end:
                return i + 1
    return 1


def _calculate_aspect(
    deg1: float, deg2: float
) -> tuple[str, float] | None:
    """Check if two planet positions form an aspect."""
    diff = abs(deg1 - deg2)
    if diff > 180:
        diff = 360 - diff

    for aspect_name, aspect_angle in ASPECT_TYPES.items():
        orb = abs(diff - aspect_angle)
        if orb <= ASPECT_ORBS[aspect_name]:
            return aspect_name, round(orb, 2)
    return None


def _datetime_to_jd(date_str: str, time_str: str) -> float:
    """Convert date and time strings to Julian Day Number."""
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    jd = swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0)
    return jd


def calculate_natal_chart(birth_data: BirthData) -> NatalChart:
    """Calculate a complete natal chart for given birth data.

    Uses Swiss Ephemeris to compute planet positions, house cusps,
    and aspects between planets.
    """
    swe.set_ephe_path(None)

    jd = _datetime_to_jd(birth_data.date, birth_data.time)

    cusps, ascmc = swe.houses(jd, birth_data.lat, birth_data.lon, b"P")
    cusps_list = list(cusps)

    ascendant_degree = ascmc[0]
    mc_degree = ascmc[1]
    ascendant_sign = _degree_to_sign(ascendant_degree)
    mc_sign = _degree_to_sign(mc_degree)

    planets = {}
    planet_degrees = {}

    for planet_name, planet_id in PLANETS.items():
        result, _ = swe.calc_ut(jd, planet_id)
        longitude = result[0]
        planet_degrees[planet_name] = longitude

        sign = _degree_to_sign(longitude)
        degree_in_sign = round(_degree_in_sign(longitude), 2)
        house = _get_house_number(longitude, cusps_list)

        planets[planet_name] = {
            "sign": sign,
            "degree": f"{degree_in_sign:.2f}",
            "house": str(house),
        }

    houses = {}
    for i, cusp in enumerate(cusps_list):
        houses[str(i + 1)] = _degree_to_sign(cusp)

    aspects = []
    planet_names = list(PLANETS.keys())
    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            p1 = planet_names[i]
            p2 = planet_names[j]
            result = _calculate_aspect(planet_degrees[p1], planet_degrees[p2])
            if result:
                aspect_type, orb = result
                aspects.append({
                    "planet1": p1,
                    "planet2": p2,
                    "aspect_type": aspect_type,
                    "orb": str(orb),
                })

    swe.close()

    return NatalChart(
        planets=planets,
        houses=houses,
        ascendant=ascendant_sign,
        mc=mc_sign,
        aspects=aspects,
    )
