"""Geocoding endpoint using Nominatim (OpenStreetMap) and timezonefinder."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from timezonefinder import TimezoneFinder

from app.http_client import get_http_client
from app.rate_limiter import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["geocoding"])

# Singleton TimezoneFinder (initialized on first use)
_tf: Optional[TimezoneFinder] = None


def _get_timezone_finder() -> TimezoneFinder:
    """Get or create the TimezoneFinder instance."""
    global _tf
    if _tf is None:
        _tf = TimezoneFinder()
    return _tf


class GeocodeSuggestion(BaseModel):
    """A geocoding suggestion with location and timezone info."""

    display_name: str
    lat: float
    lon: float
    timezone: str


class GeocodeResponse(BaseModel):
    """Response for geocode endpoint."""

    suggestions: list[GeocodeSuggestion]


@router.get("/geocode", response_model=GeocodeResponse)
async def geocode_city(
    city: str = Query(..., min_length=2, description="City name to search for"),
    _rate_check=Depends(rate_limit("geocode", 10, 60)),
):
    """Search for a city and return lat/lon/timezone suggestions.

    Uses Nominatim (OpenStreetMap) for geocoding and timezonefinder
    for timezone lookup.
    """
    client = get_http_client()

    try:
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": city,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
            },
            headers={
                "User-Agent": "AIAstrologer/1.0 (contact@example.com)",
            },
        )
        response.raise_for_status()
        results = response.json()
    except Exception as e:
        logger.error(f"Nominatim request failed: {e}")
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    tf = _get_timezone_finder()
    suggestions = []

    for item in results:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
            timezone = tf.timezone_at(lat=lat, lng=lon) or "UTC"
            display_name = item.get("display_name", city)

            suggestions.append(
                GeocodeSuggestion(
                    display_name=display_name,
                    lat=lat,
                    lon=lon,
                    timezone=timezone,
                )
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Skipping invalid geocoding result: {e}")
            continue

    return GeocodeResponse(suggestions=suggestions)
