"""Calendar Integration - supports Cal.com and Google Calendar for booking meetings."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


class CalendarIntegration:
    """Async calendar integration supporting Cal.com and Google Calendar providers."""

    def __init__(
        self,
        provider: str,
        api_key: str,
        base_url: str = "https://api.cal.com/v1",
    ) -> None:
        self._provider = provider.lower()
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def generate_booking_link(
        self,
        lead_data: dict[str, Any],
        meeting_duration: int = 30,
    ) -> str:
        """Generate a booking link for a lead.

        Args:
            lead_data: Dict with lead info (name, email, etc.)
            meeting_duration: Duration in minutes (default 30).

        Returns:
            A booking URL string.
        """
        if not self._api_key:
            logger.warning("Calendar API key not configured, returning empty link")
            return ""

        if self._provider == "calcom":
            params = {
                "name": f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip(),
                "email": lead_data.get("email", ""),
                "duration": str(meeting_duration),
            }
            query = urlencode(params)
            return f"{self._base_url}/booking?{query}"

        elif self._provider == "google":
            # Google Calendar API requires OAuth - return placeholder
            logger.info("Google Calendar booking link generation is a placeholder")
            return "https://calendar.google.com/calendar/appointments/schedules"

        logger.warning("Unknown calendar provider: %s", self._provider)
        return ""

    async def check_availability(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, str]]:
        """Check availability for a date range.

        Args:
            start_date: ISO format start date string.
            end_date: ISO format end date string.

        Returns:
            List of dicts with 'start' and 'end' time slots.
        """
        if not self._api_key:
            logger.warning("Calendar API key not configured, returning empty availability")
            return []

        if self._provider == "calcom":
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self._base_url}/availability",
                        params={
                            "apiKey": self._api_key,
                            "dateFrom": start_date,
                            "dateTo": end_date,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    slots = data.get("slots", data.get("availability", []))
                    return [
                        {"start": slot.get("start", ""), "end": slot.get("end", "")}
                        for slot in slots
                        if isinstance(slot, dict)
                    ]
            except httpx.HTTPError as exc:
                logger.error("Cal.com availability check failed: %s", exc)
                return []
            except Exception as exc:
                logger.error("Unexpected error checking availability: %s", exc)
                return []

        elif self._provider == "google":
            logger.info("Google Calendar availability check is a placeholder")
            return []

        return []

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        attendees: list[str],
    ) -> dict[str, Any]:
        """Create a calendar event/booking.

        Args:
            title: Event title.
            start_time: ISO format start time.
            end_time: ISO format end time.
            attendees: List of attendee email addresses.

        Returns:
            Created event/booking response dict.
        """
        if not self._api_key:
            logger.warning("Calendar API key not configured, cannot create event")
            return {}

        if self._provider == "calcom":
            try:
                payload = {
                    "title": title,
                    "startTime": start_time,
                    "endTime": end_time,
                    "attendees": [{"email": email} for email in attendees],
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self._base_url}/bookings",
                        params={"apiKey": self._api_key},
                        json=payload,
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPError as exc:
                logger.error("Cal.com event creation failed: %s", exc)
                return {}
            except Exception as exc:
                logger.error("Unexpected error creating event: %s", exc)
                return {}

        elif self._provider == "google":
            logger.info("Google Calendar event creation is a placeholder")
            return {}

        return {}
