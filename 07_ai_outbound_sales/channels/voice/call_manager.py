from __future__ import annotations
import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Call, CallStatus, CallOutcome, Lead

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
        redis_url: str = "",
        voice_agent: Any = None,
    ) -> None:
        self._twilio = twilio_client
        self._stt = stt
        self._tts = tts
        self._llm = llm_client
        self._session_factory = session_factory
        self._settings = settings
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._voice_agent = voice_agent
        # Per-call conversation state and history, keyed by stream_sid/call_sid
        self._conversation_states: dict[str, Any] = {}
        self._conversation_histories: dict[str, list[dict[str, Any]]] = {}

    async def _get_redis(self) -> aioredis.Redis | None:
        """Get or create Redis connection."""
        if not self._redis_url:
            return None
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def start_call(
        self,
        lead_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
        campaign_id: str | uuid.UUID | None = None,
        script_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Initiate an outbound call and create the DB record.

        Checks voice addon billing before proceeding. If no active addon
        exists, the call is rejected.
        """
        # Check voice addon billing
        from integrations.voice_usage import (
            NoActiveVoiceAddonError,
            check_and_increment_usage,
        )

        async with self._session_factory() as session:
            try:
                await check_and_increment_usage(session, tenant_id)
                await session.commit()
            except NoActiveVoiceAddonError as e:
                return {
                    "call_id": None,
                    "twilio_sid": None,
                    "status": "rejected",
                    "error": str(e),
                }

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

    async def handle_media_stream(
        self, websocket: Any, call_sid: str, stream_sid: str = ""
    ) -> None:
        """Manage the bidirectional audio stream for a call.

        Receives audio from Twilio WebSocket, sends to STT, gets transcript,
        processes via LLM, and streams TTS audio back.

        Enforces a maximum call duration timeout via voice_max_call_duration.
        """
        timeout = getattr(self._settings, "voice_max_call_duration", 180)
        try:
            await asyncio.wait_for(
                self._media_stream_loop(websocket, call_sid, stream_sid),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Call %s exceeded max duration (%ds), terminating", call_sid, timeout
            )
            try:
                await self._twilio.end_call(call_sid)
            except Exception:
                pass

    async def _media_stream_loop(
        self, websocket: Any, call_sid: str, stream_sid: str = ""
    ) -> None:
        """Internal media stream loop, separated for timeout wrapping."""
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

                    if event == "start":
                        # Capture the stream SID from the start event if not provided
                        if not stream_sid:
                            stream_sid = data.get("start", {}).get("streamSid", "")

                    elif event == "media":
                        payload = data.get("media", {}).get("payload", "")
                        audio_bytes = base64.b64decode(payload)
                        await self._stt.send_audio(audio_bytes)

                        # Check for turn end (silence detection)
                        if self._stt.is_turn_end and transcript_buffer:
                            user_text = " ".join(transcript_buffer)
                            transcript_buffer.clear()
                            await self._process_turn(
                                websocket, stream_sid or call_sid, user_text
                            )

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

        terminal_statuses = (
            CallStatus.completed,
            CallStatus.failed,
            CallStatus.no_answer,
            CallStatus.busy,
        )
        if call_status in terminal_statuses:
            update_data["ended_at"] = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            stmt = (
                update(Call)
                .where(Call.twilio_sid == call_sid)
                .values(**update_data)
            )
            await session.execute(stmt)
            await session.commit()

            # Remove from active set on terminal statuses
            if call_status in terminal_statuses:
                # Look up the call to get tenant_id and call_id
                result = await session.execute(
                    select(Call).where(Call.twilio_sid == call_sid)
                )
                call = result.scalar_one_or_none()
                if call:
                    redis = await self._get_redis()
                    if redis:
                        active_key = f"voice:active:{call.tenant_id}"
                        await redis.srem(active_key, str(call.id))

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
        to_number = ""
        async with self._session_factory() as session:
            # Fetch the lead's phone number from enrichment_data
            lead_uuid = uuid.UUID(str(lead_id))
            stmt = select(Lead).where(Lead.id == lead_uuid)
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()
            if lead and lead.enrichment_data:
                to_number = lead.enrichment_data.get("phone", "")

            call = Call(
                id=call_id,
                tenant_id=uuid.UUID(str(tenant_id)),
                lead_id=lead_uuid,
                campaign_id=uuid.UUID(str(campaign_id)) if campaign_id else None,
                script_id=uuid.UUID(str(script_id)) if script_id else None,
                status=CallStatus.initiated,
            )
            session.add(call)
            await session.commit()

        return {"id": str(call_id), "to_number": to_number}

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
        self, websocket: Any, stream_sid: str, user_text: str
    ) -> None:
        """Process a conversation turn: send to VoiceConversationAgent and stream TTS response."""
        try:
            if self._voice_agent:
                from agents.voice_conversation import ConversationState

                # Get or initialize conversation state for this stream
                if stream_sid not in self._conversation_states:
                    self._conversation_states[stream_sid] = ConversationState.greeting
                if stream_sid not in self._conversation_histories:
                    self._conversation_histories[stream_sid] = []

                current_state = self._conversation_states[stream_sid]
                history = self._conversation_histories[stream_sid]

                # Build minimal lead_data (empty dict if not available)
                lead_data: dict[str, Any] = {}

                result = await self._voice_agent.process_transcript(
                    transcript=user_text,
                    state=current_state,
                    lead_data=lead_data,
                    conversation_history=history,
                )

                response_text = result.get("response_text", "")
                new_state = result.get("new_state", current_state)

                # Update tracked state and history
                self._conversation_states[stream_sid] = new_state
                history.append({"role": "user", "content": user_text})
                history.append({"role": "assistant", "content": response_text})
            else:
                # Fallback: direct LLM call if no voice agent configured
                response_text = await self._llm.generate(user_text)

            async for audio_chunk in self._tts.synthesize(response_text):
                payload = base64.b64encode(audio_chunk).decode("utf-8")
                media_message = json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload},
                })
                await websocket.send(media_message)
        except Exception as e:
            logger.error("Error processing turn for stream %s: %s", stream_sid, e)
