import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Call, CallStatus, CallOutcome

logger = logging.getLogger(__name__)


class CallManager:
    """Orchestrates the full voice call lifecycle."""

    def __init__(
        self,
        twilio_client: Any,
        stt: Any,
        tts: Any,
        llm_client: Any,
        session_factory: Any,
        settings: Any,
    ) -> None:
        self._twilio = twilio_client
        self._stt = stt
        self._tts = tts
        self._llm = llm_client
        self._session_factory = session_factory
        self._settings = settings

    async def start_call(
        self,
        lead_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
        campaign_id: str | uuid.UUID | None = None,
        script_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Initiate an outbound call and create the DB record."""
        call_record = await self._create_call_record(
            lead_id=lead_id,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            script_id=script_id,
        )

        webhook_url = f"{self._settings.tracking_base_url}/api/voice/twiml/{call_record['id']}"
        status_url = f"{self._settings.tracking_base_url}/api/voice/status/{call_record['id']}"

        result = await self._twilio.initiate_call(
            to_number=call_record.get("to_number", ""),
            webhook_url=webhook_url,
            status_callback_url=status_url,
            amd_enabled=self._settings.voice_amd_enabled,
        )

        if "error" not in result:
            await self._update_call_record(
                call_id=call_record["id"],
                twilio_sid=result["call_sid"],
                status=CallStatus.initiated,
            )

        return {
            "call_id": call_record["id"],
            "twilio_sid": result.get("call_sid"),
            "status": result.get("status", "error"),
            "error": result.get("error"),
        }

    async def handle_media_stream(self, websocket: Any, call_sid: str) -> None:
        """Manage the bidirectional audio stream for a call.

        Receives audio from Twilio WebSocket, sends to STT, gets transcript,
        processes via LLM, and streams TTS audio back.
        """
        transcript_buffer: list[str] = []

        def on_transcript(result: dict[str, Any]) -> None:
            if result.get("is_final") and result.get("text"):
                transcript_buffer.append(result["text"])

        await self._stt.start_stream(language="en", on_transcript=on_transcript)

        try:
            async for message in websocket:
                if isinstance(message, str):
                    data = json.loads(message)
                    event = data.get("event")

                    if event == "media":
                        payload = data.get("media", {}).get("payload", "")
                        audio_bytes = base64.b64decode(payload)
                        await self._stt.send_audio(audio_bytes)

                        # Check for turn end (silence detection)
                        if self._stt.is_turn_end and transcript_buffer:
                            user_text = " ".join(transcript_buffer)
                            transcript_buffer.clear()
                            await self._process_turn(websocket, call_sid, user_text)

                    elif event == "stop":
                        break
        except Exception as e:
            logger.error("Media stream error for call %s: %s", call_sid, e)
        finally:
            await self._stt.stop_stream()

    async def handle_status_update(
        self, call_sid: str, status: str, duration: int | None = None
    ) -> None:
        """Handle a call status webhook from Twilio."""
        status_map = {
            "initiated": CallStatus.initiated,
            "ringing": CallStatus.ringing,
            "in-progress": CallStatus.in_progress,
            "completed": CallStatus.completed,
            "failed": CallStatus.failed,
            "no-answer": CallStatus.no_answer,
            "busy": CallStatus.busy,
        }
        call_status = status_map.get(status, CallStatus.failed)

        update_data: dict[str, Any] = {"status": call_status}
        if duration is not None:
            update_data["duration_seconds"] = duration
        if call_status in (CallStatus.completed, CallStatus.failed, CallStatus.no_answer, CallStatus.busy):
            update_data["ended_at"] = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            stmt = (
                update(Call)
                .where(Call.twilio_sid == call_sid)
                .values(**update_data)
            )
            await session.execute(stmt)
            await session.commit()

    async def handle_amd_result(self, call_sid: str, answered_by: str) -> None:
        """Handle answering machine detection result."""
        if answered_by in ("machine_start", "machine_end_beep", "machine_end_silence"):
            # Machine detected - update outcome and end the call
            async with self._session_factory() as session:
                stmt = (
                    update(Call)
                    .where(Call.twilio_sid == call_sid)
                    .values(outcome=CallOutcome.voicemail)
                )
                await session.execute(stmt)
                await session.commit()
            await self._twilio.end_call(call_sid)
        # If human detected, let the call continue normally

    async def _create_call_record(
        self,
        lead_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
        campaign_id: str | uuid.UUID | None = None,
        script_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Create a new Call record in the database."""
        call_id = uuid.uuid4()
        async with self._session_factory() as session:
            call = Call(
                id=call_id,
                tenant_id=uuid.UUID(str(tenant_id)),
                lead_id=uuid.UUID(str(lead_id)),
                campaign_id=uuid.UUID(str(campaign_id)) if campaign_id else None,
                script_id=uuid.UUID(str(script_id)) if script_id else None,
                status=CallStatus.initiated,
            )
            session.add(call)
            await session.commit()

        return {"id": str(call_id)}

    async def _update_call_record(
        self,
        call_id: str,
        **kwargs: Any,
    ) -> None:
        """Update an existing Call record."""
        async with self._session_factory() as session:
            stmt = (
                update(Call)
                .where(Call.id == uuid.UUID(call_id))
                .values(**kwargs)
            )
            await session.execute(stmt)
            await session.commit()

    async def _process_turn(
        self, websocket: Any, call_sid: str, user_text: str
    ) -> None:
        """Process a conversation turn: send to LLM and stream TTS response."""
        try:
            response_text = await self._llm.generate(user_text)
            async for audio_chunk in self._tts.synthesize(response_text):
                payload = base64.b64encode(audio_chunk).decode("utf-8")
                media_message = json.dumps({
                    "event": "media",
                    "streamSid": call_sid,
                    "media": {"payload": payload},
                })
                await websocket.send(media_message)
        except Exception as e:
            logger.error("Error processing turn for call %s: %s", call_sid, e)
