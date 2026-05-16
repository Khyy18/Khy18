"""Comprehensive tests for the voice channel components."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from core.models import Call, CallOutcome, CallScript, CallStatus
from agents.voice_conversation import ConversationState, VoiceConversationAgent
from channels.voice.call_manager import CallManager
from channels.voice.stt import DeepgramSTT
from channels.voice.tts import ElevenLabsTTS
from channels.voice.twilio_client import TwilioClient
from scheduler.voice_scheduler import VoiceScheduler
from tests.conftest import make_call, make_tenant, make_lead, make_voice_addon


# ---------- TwilioClient Tests ----------


async def test_twilio_initiate_call_success():
    """Test that initiate_call returns a dict with call_sid on success."""
    mock_client = MagicMock()
    mock_call = MagicMock()
    mock_call.sid = "CAxxx123"
    mock_call.status = "initiated"
    mock_client.calls.create.return_value = mock_call

    with patch("channels.voice.twilio_client.Client", return_value=mock_client):
        twilio = TwilioClient(
            account_sid="ACtest",
            auth_token="token123",
            from_number="+15551234567",
        )
        twilio._client = mock_client

    result = await twilio.initiate_call(
        to_number="+15559876543",
        webhook_url="http://example.com/twiml",
        status_callback_url="http://example.com/status",
        amd_enabled=True,
    )

    assert "call_sid" in result
    assert result["call_sid"] == "CAxxx123"
    assert result["status"] == "initiated"


async def test_twilio_get_call_status():
    """Test get_call_status returns a status dict."""
    mock_client = MagicMock()
    mock_call_instance = MagicMock()
    mock_call_instance.sid = "CAxxx123"
    mock_call_instance.status = "in-progress"
    mock_call_instance.duration = "42"
    mock_call_instance.direction = "outbound-api"
    mock_client.calls.return_value.fetch.return_value = mock_call_instance

    with patch("channels.voice.twilio_client.Client", return_value=mock_client):
        twilio = TwilioClient(
            account_sid="ACtest",
            auth_token="token123",
            from_number="+15551234567",
        )
        twilio._client = mock_client

    result = await twilio.get_call_status("CAxxx123")

    assert result["call_sid"] == "CAxxx123"
    assert result["status"] == "in-progress"
    assert result["duration"] == "42"
    assert result["direction"] == "outbound-api"


async def test_twilio_end_call():
    """Test end_call returns True on success."""
    mock_client = MagicMock()
    mock_client.calls.return_value.update.return_value = MagicMock()

    with patch("channels.voice.twilio_client.Client", return_value=mock_client):
        twilio = TwilioClient(
            account_sid="ACtest",
            auth_token="token123",
            from_number="+15551234567",
        )
        twilio._client = mock_client

    result = await twilio.end_call("CAxxx123")
    assert result is True


async def test_twilio_generate_twiml_stream():
    """Test generate_twiml_stream returns valid XML containing the Stream url."""
    with patch("channels.voice.twilio_client.Client"):
        twilio = TwilioClient(
            account_sid="ACtest",
            auth_token="token123",
            from_number="+15551234567",
        )

    twiml_xml = twilio.generate_twiml_stream("wss://example.com/stream")

    assert "<?xml" in twiml_xml or "<Response>" in twiml_xml
    assert "<Stream" in twiml_xml
    assert "wss://example.com/stream" in twiml_xml


# ---------- DeepgramSTT Tests ----------


async def test_stt_start_stream_initializes_state():
    """Test that start_stream sets is_streaming to True."""
    stt = DeepgramSTT(api_key="test-key")

    mock_ws = AsyncMock()
    mock_ws.__aiter__ = AsyncMock(return_value=iter([]))

    with patch("channels.voice.stt.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws
        await stt.start_stream(language="en")

    assert stt.is_streaming is True

    # Clean up
    await stt.stop_stream()


async def test_stt_send_audio_raises_if_not_started():
    """Test that send_audio does nothing if stream not started (ws is None)."""
    stt = DeepgramSTT(api_key="test-key")

    # Should not raise but also should not send (ws is None)
    await stt.send_audio(b"\x00\x01\x02")
    # No exception means it handled the None ws gracefully


async def test_stt_stop_stream():
    """Test that stop_stream sets is_streaming to False and cleans up."""
    stt = DeepgramSTT(api_key="test-key")

    mock_ws = AsyncMock()
    mock_ws.__aiter__ = AsyncMock(return_value=iter([]))

    with patch("channels.voice.stt.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws
        await stt.start_stream(language="en")

    assert stt.is_streaming is True

    await stt.stop_stream()

    assert stt.is_streaming is False
    assert stt._ws is None


# ---------- ElevenLabsTTS Tests ----------


async def test_tts_synthesize_yields_chunks():
    """Test that synthesize yields bytes chunks from a mocked streaming response."""
    tts = ElevenLabsTTS(api_key="test-key", voice_id="voice123")

    chunks = [b"chunk1", b"chunk2", b"chunk3"]

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_bytes(chunk_size=1024):
        for chunk in chunks:
            yield chunk

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client_instance = AsyncMock()
    mock_client_instance.stream = MagicMock()

    # Create a proper async context manager for stream
    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    mock_client_instance.stream.return_value = MockStreamContext()

    class MockClientContext:
        async def __aenter__(self):
            return mock_client_instance

        async def __aexit__(self, *args):
            pass

    with patch("channels.voice.tts.httpx.AsyncClient", return_value=MockClientContext()):
        received_chunks = []
        async for chunk in tts.synthesize("Hello world"):
            received_chunks.append(chunk)

    assert received_chunks == chunks


async def test_tts_convert_to_mulaw():
    """Test convert_to_mulaw converts PCM bytes correctly."""
    # 16-bit PCM sample (2 bytes per sample)
    pcm_bytes = b"\x00\x10" * 10  # 10 samples of 16-bit PCM

    result = ElevenLabsTTS.convert_to_mulaw(pcm_bytes)

    assert isinstance(result, bytes)
    assert len(result) == 10  # mu-law produces 1 byte per sample


# ---------- CallManager Tests ----------


async def test_call_manager_start_call_creates_record(session_factory, async_session):
    """Test that start_call creates a Call record in the database."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    # Seed required records
    tenant = make_tenant(id=tenant_id)
    lead = make_lead(id=lead_id, tenant_id=tenant_id)
    addon = make_voice_addon(tenant_id=tenant_id)
    async_session.add(tenant)
    async_session.add(lead)
    async_session.add(addon)
    await async_session.commit()

    mock_twilio = AsyncMock()
    mock_twilio.initiate_call = AsyncMock(return_value={"call_sid": "CA_test_123", "status": "initiated"})

    mock_settings = MagicMock()
    mock_settings.tracking_base_url = "http://localhost:8000"
    mock_settings.voice_amd_enabled = True

    call_manager = CallManager(
        twilio_client=mock_twilio,
        stt=AsyncMock(),
        tts=AsyncMock(),
        llm_client=AsyncMock(),
        session_factory=session_factory,
        settings=mock_settings,
    )

    result = await call_manager.start_call(
        lead_id=lead_id,
        tenant_id=tenant_id,
    )

    assert result["call_id"] is not None
    assert result["twilio_sid"] == "CA_test_123"

    # Verify DB record exists
    stmt = select(Call).where(Call.tenant_id == tenant_id)
    db_result = await async_session.execute(stmt)
    call = db_result.scalar_one_or_none()
    assert call is not None
    assert call.status == CallStatus.initiated


async def test_call_manager_handle_status_update_completed(session_factory, async_session):
    """Test that handle_status_update correctly marks call as completed with duration."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    tenant = make_tenant(id=tenant_id)
    lead = make_lead(id=lead_id, tenant_id=tenant_id)
    async_session.add_all([tenant, lead])
    await async_session.commit()

    call = make_call(tenant_id=tenant_id, lead_id=lead_id, twilio_sid="CA_completed_123")
    async_session.add(call)
    await async_session.commit()

    call_manager = CallManager(
        twilio_client=AsyncMock(),
        stt=AsyncMock(),
        tts=AsyncMock(),
        llm_client=AsyncMock(),
        session_factory=session_factory,
        settings=MagicMock(),
    )

    await call_manager.handle_status_update(
        call_sid="CA_completed_123",
        status="completed",
        duration=120,
    )

    await async_session.refresh(call)
    assert call.status == CallStatus.completed
    assert call.duration_seconds == 120
    assert call.ended_at is not None


async def test_call_manager_handle_status_update_failed(session_factory, async_session):
    """Test that handle_status_update correctly records failed status."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    tenant = make_tenant(id=tenant_id)
    lead = make_lead(id=lead_id, tenant_id=tenant_id)
    async_session.add_all([tenant, lead])
    await async_session.commit()

    call = make_call(tenant_id=tenant_id, lead_id=lead_id, twilio_sid="CA_failed_456")
    async_session.add(call)
    await async_session.commit()

    call_manager = CallManager(
        twilio_client=AsyncMock(),
        stt=AsyncMock(),
        tts=AsyncMock(),
        llm_client=AsyncMock(),
        session_factory=session_factory,
        settings=MagicMock(),
    )

    await call_manager.handle_status_update(
        call_sid="CA_failed_456",
        status="failed",
        duration=None,
    )

    await async_session.refresh(call)
    assert call.status == CallStatus.failed
    assert call.ended_at is not None


async def test_call_manager_handle_amd_machine(session_factory, async_session):
    """Test that handle_amd_result sets voicemail outcome when machine detected."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    tenant = make_tenant(id=tenant_id)
    lead = make_lead(id=lead_id, tenant_id=tenant_id)
    async_session.add_all([tenant, lead])
    await async_session.commit()

    call = make_call(tenant_id=tenant_id, lead_id=lead_id, twilio_sid="CA_amd_789")
    async_session.add(call)
    await async_session.commit()

    mock_twilio = AsyncMock()
    mock_twilio.end_call = AsyncMock(return_value=True)

    call_manager = CallManager(
        twilio_client=mock_twilio,
        stt=AsyncMock(),
        tts=AsyncMock(),
        llm_client=AsyncMock(),
        session_factory=session_factory,
        settings=MagicMock(),
    )

    await call_manager.handle_amd_result(
        call_sid="CA_amd_789",
        answered_by="machine_start",
    )

    await async_session.refresh(call)
    assert call.outcome == CallOutcome.voicemail
    mock_twilio.end_call.assert_called_once_with("CA_amd_789")


# ---------- VoiceConversationAgent Tests ----------


async def test_generate_greeting(session_factory, mock_llm_client, mock_settings):
    """Test generate_greeting returns a non-empty greeting string."""
    mock_llm_client.generate = AsyncMock(return_value="Hi John, this is Sarah from Acme Corp. Do you have a moment?")

    agent = VoiceConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        session_factory=session_factory,
    )

    lead_data = {"first_name": "John", "last_name": "Doe", "company": "TestCo", "title": "CTO"}
    result = await agent.generate_greeting(lead_data)

    assert isinstance(result, str)
    assert len(result) > 0
    mock_llm_client.generate.assert_called_once()


async def test_process_transcript_returns_response(session_factory, mock_llm_client, mock_settings):
    """Test process_transcript returns a dict with response_text and new_state."""
    mock_llm_client.generate = AsyncMock(
        return_value='{"response_text": "That sounds great!", "new_state": "qualification"}'
    )

    agent = VoiceConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        session_factory=session_factory,
    )

    lead_data = {"first_name": "John", "last_name": "Doe", "company": "TestCo", "title": "CTO"}
    result = await agent.process_transcript(
        transcript="I am interested in hearing more.",
        state=ConversationState.greeting,
        lead_data=lead_data,
        conversation_history=[],
    )

    assert "response_text" in result
    assert "new_state" in result
    assert result["response_text"] == "That sounds great!"
    assert result["new_state"] == ConversationState.qualification


async def test_should_end_call_max_duration(session_factory, mock_llm_client, mock_settings):
    """Test should_end_call returns True when duration exceeds max."""
    agent = VoiceConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        session_factory=session_factory,
    )

    result = await agent.should_end_call(
        state=ConversationState.qualification,
        duration_seconds=200,
        max_duration=180,
    )

    assert result is True


async def test_should_end_call_not_exceeded(session_factory, mock_llm_client, mock_settings):
    """Test should_end_call returns False when duration is under max."""
    agent = VoiceConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        session_factory=session_factory,
    )

    result = await agent.should_end_call(
        state=ConversationState.qualification,
        duration_seconds=60,
        max_duration=180,
    )

    assert result is False


async def test_process_transcript_state_transition(session_factory, mock_llm_client, mock_settings):
    """Test process_transcript transitions state from greeting to offer."""
    mock_llm_client.generate = AsyncMock(
        return_value='{"response_text": "Let me tell you about our product.", "new_state": "offer"}'
    )

    agent = VoiceConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        session_factory=session_factory,
    )

    lead_data = {"first_name": "Jane", "last_name": "Smith", "company": "BigCorp", "title": "VP Sales"}
    result = await agent.process_transcript(
        transcript="Tell me what you offer.",
        state=ConversationState.greeting,
        lead_data=lead_data,
        conversation_history=[],
    )

    assert result["new_state"] == ConversationState.offer


# ---------- VoiceScheduler Tests ----------


async def test_is_within_calling_hours_true(session_factory):
    """Test _is_within_calling_hours returns True when within range."""
    mock_settings = MagicMock()
    mock_settings.voice_calling_hours_start = 0
    mock_settings.voice_calling_hours_end = 23

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=AsyncMock(),
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )

    result = await scheduler._is_within_calling_hours()
    assert result is True


async def test_is_within_calling_hours_false(session_factory):
    """Test _is_within_calling_hours returns False when outside range."""
    # Set an impossible range so the check always fails
    mock_settings = MagicMock()
    now_hour = datetime.now(timezone.utc).hour
    # Set start and end so current hour is excluded
    mock_settings.voice_calling_hours_start = (now_hour + 2) % 24
    mock_settings.voice_calling_hours_end = (now_hour + 3) % 24

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=AsyncMock(),
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )

    result = await scheduler._is_within_calling_hours()
    assert result is False


async def test_should_retry_under_max(session_factory):
    """Test _should_retry returns True for attempts under the maximum."""
    mock_settings = MagicMock()

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=AsyncMock(),
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )

    result = await scheduler._should_retry({"attempts": 1})
    assert result is True


async def test_should_retry_max_exceeded(session_factory):
    """Test _should_retry returns False when max attempts reached."""
    mock_settings = MagicMock()

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=AsyncMock(),
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )

    result = await scheduler._should_retry({"attempts": 3})
    assert result is False
