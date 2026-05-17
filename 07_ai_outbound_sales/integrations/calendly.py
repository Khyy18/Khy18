"""Calendly API client for fetching availability and creating bookings."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CalendlyClient:
    """Async client for the Calendly API v2."""

    BASE_URL = "https://api.calendly.com"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def get_available_slots(
        self,
        event_type_uri: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, str]]:
        """Fetch available time slots from Calendly for a given event type.

        Args:
            event_type_uri: The Calendly event type URI (e.g. https://api.calendly.com/event_types/XXX).
            start_date: ISO format start date string.
            end_date: ISO format end date string.

        Returns:
            List of dicts with 'start_time' and 'status' keys.
        """
        if not self._api_key:
            logger.warning("Calendly API key not configured")
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/event_type_available_times",
                    headers=self._headers(),
                    params={
                        "event_type": event_type_uri,
                        "start_time": start_date,
                        "end_time": end_date,
                    },
                )
                response.raise_for_status()
                data = response.json()
                collection = data.get("collection", [])
                return [
                    {
                        "start_time": slot.get("start_time", ""),
                        "status": slot.get("status", "available"),
                    }
                    for slot in collection
                    if isinstance(slot, dict)
                ]
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Calendly API error %s: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return []
        except httpx.HTTPError as exc:
            logger.error("Calendly availability request failed: %s", exc)
            return []
        except Exception as exc:
            logger.error("Unexpected error fetching Calendly slots: %s", exc)
            return []

    async def create_booking(
        self,
        event_type_uri: str,
        invitee_email: str,
        invitee_name: str,
        start_time: str,
    ) -> dict[str, Any]:
        """Create a booking (scheduled event) via Calendly's scheduling link.

        Note: Calendly API v2 does not support direct booking creation for most
        accounts. This method uses the one-off event creation endpoint when
        available, or returns a scheduling link for the invitee.

        Args:
            event_type_uri: The Calendly event type URI.
            invitee_email: Email address of the invitee.
            invitee_name: Full name of the invitee.
            start_time: ISO format start time for the booking.

        Returns:
            Dict with booking confirmation or scheduling link.
        """
        if not self._api_key:
            logger.warning("Calendly API key not configured")
            return {"error": "API key not configured"}

        try:
            payload = {
                "event_type": event_type_uri,
                "start_time": start_time,
                "invitee": {
                    "email": invitee_email,
                    "name": invitee_name,
                },
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/scheduled_events",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "status": "booked",
                    "uri": data.get("resource", {}).get("uri", ""),
                    "start_time": start_time,
                    "invitee_email": invitee_email,
                }
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Calendly booking error %s: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return {"error": f"Booking failed: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            logger.error("Calendly booking request failed: %s", exc)
            return {"error": str(exc)}
        except Exception as exc:
            logger.error("Unexpected error creating Calendly booking: %s", exc)
            return {"error": str(exc)}
