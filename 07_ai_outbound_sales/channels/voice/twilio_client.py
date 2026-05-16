import asyncio
import logging
from typing import Any

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect

logger = logging.getLogger(__name__)


class TwilioClient:
    """Async wrapper around the Twilio REST API for outbound voice calls."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._client = Client(account_sid, auth_token)

    async def initiate_call(
        self,
        to_number: str,
        webhook_url: str,
        status_callback_url: str,
        amd_enabled: bool = True,
    ) -> dict[str, Any]:
        """Initiate an outbound call via Twilio."""
        try:
            kwargs: dict[str, Any] = {
                "to": to_number,
                "from_": self._from_number,
                "url": webhook_url,
                "status_callback": status_callback_url,
                "status_callback_event": ["initiated", "ringing", "answered", "completed"],
            }
            if amd_enabled:
                kwargs["machine_detection"] = "DetectMessageEnd"
                kwargs["async_amd"] = "true"

            call = await asyncio.to_thread(
                self._client.calls.create, **kwargs
            )
            return {"call_sid": call.sid, "status": call.status}
        except Exception as e:
            logger.error("Twilio initiate_call failed: %s", e)
            return {"error": str(e)}

    async def get_call_status(self, call_sid: str) -> dict[str, Any]:
        """Fetch the current status of a call."""
        try:
            call = await asyncio.to_thread(
                self._client.calls(call_sid).fetch
            )
            return {
                "call_sid": call.sid,
                "status": call.status,
                "duration": call.duration,
                "direction": call.direction,
            }
        except Exception as e:
            logger.error("Twilio get_call_status failed: %s", e)
            return {"error": str(e)}

    async def end_call(self, call_sid: str) -> bool:
        """End an active call."""
        try:
            await asyncio.to_thread(
                self._client.calls(call_sid).update, status="completed"
            )
            return True
        except Exception as e:
            logger.error("Twilio end_call failed: %s", e)
            return False

    def generate_twiml_stream(self, stream_url: str) -> str:
        """Generate TwiML XML for connecting to a media stream."""
        response = VoiceResponse()
        connect = Connect()
        connect.stream(url=stream_url)
        response.append(connect)
        return str(response)
