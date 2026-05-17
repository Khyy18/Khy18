"""Calendar Integration - supports Cal.com, Google Calendar, and Calendly for booking meetings."""

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


class GoogleCalendarClient:
    """Google Calendar API client with OAuth2 support."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    SCOPES = "https://www.googleapis.com/auth/calendar"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:8000/api/integrations/calendar/callback",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    def get_oauth_url(self, state: str = "") -> str:
        """Generate the Google OAuth2 authorization URL.

        Args:
            state: Optional state parameter for CSRF protection.

        Returns:
            The OAuth2 authorization URL.
        """
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for access and refresh tokens.

        Args:
            code: The authorization code from the OAuth callback.

        Returns:
            Token response dict with access_token, refresh_token, etc.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "redirect_uri": self._redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                data = response.json()
                self._access_token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")
                return data
        except httpx.HTTPError as exc:
            logger.error("Google OAuth token exchange failed: %s", exc)
            return {"error": str(exc)}

    async def refresh_access_token(self) -> dict[str, Any]:
        """Refresh the access token using the stored refresh token.

        Returns:
            Token response dict with new access_token.
        """
        if not self._refresh_token:
            return {"error": "No refresh token available"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "refresh_token": self._refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                response.raise_for_status()
                data = response.json()
                self._access_token = data.get("access_token")
                return data
        except httpx.HTTPError as exc:
            logger.error("Google token refresh failed: %s", exc)
            return {"error": str(exc)}

    def set_tokens(self, access_token: str, refresh_token: str | None = None) -> None:
        """Set tokens directly (e.g. loaded from database).

        Args:
            access_token: The OAuth2 access token.
            refresh_token: The OAuth2 refresh token (optional).
        """
        self._access_token = access_token
        if refresh_token:
            self._refresh_token = refresh_token

    async def check_availability(
        self,
        start_date: str,
        end_date: str,
        calendar_id: str = "primary",
    ) -> list[dict[str, str]]:
        """Check free/busy status for a date range.

        Args:
            start_date: ISO format start datetime.
            end_date: ISO format end datetime.
            calendar_id: Calendar ID (default: primary).

        Returns:
            List of busy time slots with 'start' and 'end'.
        """
        if not self._access_token:
            logger.warning("Google Calendar access token not set")
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.CALENDAR_API_BASE}/freeBusy",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    json={
                        "timeMin": start_date,
                        "timeMax": end_date,
                        "items": [{"id": calendar_id}],
                    },
                )
                response.raise_for_status()
                data = response.json()
                busy_slots = (
                    data.get("calendars", {})
                    .get(calendar_id, {})
                    .get("busy", [])
                )
                return [
                    {"start": slot.get("start", ""), "end": slot.get("end", "")}
                    for slot in busy_slots
                ]
        except httpx.HTTPError as exc:
            logger.error("Google Calendar availability check failed: %s", exc)
            return []

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        attendees: list[str],
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Create a Google Calendar event.

        Args:
            title: Event summary/title.
            start_time: ISO format start time.
            end_time: ISO format end time.
            attendees: List of attendee email addresses.
            calendar_id: Calendar ID (default: primary).

        Returns:
            Created event response dict.
        """
        if not self._access_token:
            logger.warning("Google Calendar access token not set")
            return {"error": "Access token not set"}

        try:
            event_body = {
                "summary": title,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
                "attendees": [{"email": email} for email in attendees],
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.CALENDAR_API_BASE}/calendars/{calendar_id}/events",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    json=event_body,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("Google Calendar event creation failed: %s", exc)
            return {"error": str(exc)}


class CalendarManager:
    """Facade that routes calendar operations to the correct provider based on config.

    Supports 'calcom', 'google', and 'calendly' providers.
    """

    def __init__(
        self,
        provider: str,
        calcom_api_key: str = "",
        calcom_base_url: str = "https://api.cal.com/v1",
        google_client_id: str = "",
        google_client_secret: str = "",
        calendly_api_key: str = "",
        calendly_event_type: str = "",
    ) -> None:
        self._provider = provider.lower()
        self._calcom_api_key = calcom_api_key
        self._calcom_base_url = calcom_base_url
        self._google_client_id = google_client_id
        self._google_client_secret = google_client_secret
        self._calendly_api_key = calendly_api_key
        self._calendly_event_type = calendly_event_type

        # Initialize provider clients
        self._calcom: CalendarIntegration | None = None
        self._google: GoogleCalendarClient | None = None
        self._calendly: Any = None

        if self._provider == "calcom":
            self._calcom = CalendarIntegration(
                provider="calcom",
                api_key=calcom_api_key,
                base_url=calcom_base_url,
            )
        elif self._provider == "google":
            self._google = GoogleCalendarClient(
                client_id=google_client_id,
                client_secret=google_client_secret,
            )
        elif self._provider == "calendly":
            from integrations.calendly import CalendlyClient

            self._calendly = CalendlyClient(api_key=calendly_api_key)

    @property
    def provider(self) -> str:
        return self._provider

    def set_google_tokens(
        self, access_token: str, refresh_token: str | None = None
    ) -> None:
        """Set OAuth tokens on the underlying Google Calendar client.

        Args:
            access_token: The OAuth2 access token.
            refresh_token: The OAuth2 refresh token (optional).
        """
        if self._google:
            self._google.set_tokens(access_token, refresh_token)

    def get_oauth_url(self, state: str = "") -> str | None:
        """Get OAuth URL for Google Calendar. Returns None for other providers."""
        if self._provider == "google" and self._google:
            return self._google.get_oauth_url(state=state)
        return None

    async def check_availability(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, str]]:
        """Check availability using the configured provider.

        Args:
            start_date: ISO format start date.
            end_date: ISO format end date.

        Returns:
            List of time slot dicts.
        """
        if self._provider == "calcom" and self._calcom:
            return await self._calcom.check_availability(start_date, end_date)
        elif self._provider == "google" and self._google:
            return await self._google.check_availability(start_date, end_date)
        elif self._provider == "calendly" and self._calendly:
            event_type = self._calendly_event_type
            slots = await self._calendly.get_available_slots(
                event_type_uri=event_type,
                start_date=start_date,
                end_date=end_date,
            )
            return [
                {"start": s.get("start_time", ""), "end": ""}
                for s in slots
            ]
        return []

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        attendees: list[str],
    ) -> dict[str, Any]:
        """Create a calendar event using the configured provider.

        Args:
            title: Event title.
            start_time: ISO format start time.
            end_time: ISO format end time.
            attendees: List of attendee emails.

        Returns:
            Event creation result dict.
        """
        if self._provider == "calcom" and self._calcom:
            return await self._calcom.create_event(title, start_time, end_time, attendees)
        elif self._provider == "google" and self._google:
            return await self._google.create_event(title, start_time, end_time, attendees)
        elif self._provider == "calendly" and self._calendly:
            invitee_email = attendees[0] if attendees else ""
            return await self._calendly.create_booking(
                event_type_uri=self._calendly_event_type,
                invitee_email=invitee_email,
                invitee_name="",
                start_time=start_time,
            )
        return {}

    def validate_api_key(self) -> bool:
        """Validate that the provider's API key is configured.

        Returns:
            True if the required credentials are present.
        """
        if self._provider == "calcom":
            return bool(self._calcom_api_key)
        elif self._provider == "google":
            return bool(self._google_client_id and self._google_client_secret)
        elif self._provider == "calendly":
            return bool(self._calendly_api_key)
        return False
