"""Integration tests for WebSocket media stream, scheduler tick, and signature validation."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.voice.call_manager import CallManager
from core.models import Call, CallStatus, Lead
from dashboard.routes.voice_webhooks import _validate_twilio_signature
from scheduler.voice_scheduler import VoiceScheduler
from tests.conftest import make_call, make_lead, make_tenant, make_voice_addon


class _AsyncWSIter:
    """Helper class to simulate an async iterable WebSocket for testing."""

    def __init__(self, items):
        self._items = iter(items)
        self.send = AsyncMock()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


# ---------- Signature Validation Tests ----------


def test_validate_twilio_signature_valid():
    """Test _validate_twilio_signature returns True for a correct signature."""
    auth_token = "my_secret_token"
    url = "https://example.com/api/voice/twilio/status"
    params = {"CallSid": "CA123", "CallStatus": "completed"}

    # Reproduce the expected signature
    sorted_params = sorted(params.items())
    data = url + "".join(f"{k}{v}" for k, v in sorted_params)
    computed = hmac.HMAC(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    signature = base64.b64encode(computed).decode("utf-8")

    result = _validate_twilio_signature(url, params, signature, auth_token)
    assert result is True


def test_validate_twilio_signature_invalid():
    """Test _validate_twilio_signature returns False for an incorrect signature."""
    auth_token = "my_secret_token"
    url = "https://example.com/api/voice/twilio/status"
    params = {"CallSid": "CA123", "CallStatus": "completed"}

    result = _validate_twilio_signature(url, params, "bad-signature", auth_token)
    assert result is False


def test_validate_twilio_signature_missing_token():
    """Test _validate_twilio_signature returns False when auth_token is empty."""
    result = _validate_twilio_signature(
        "https://example.com", {"CallSid": "CA123"}, "sig", ""
    )
    assert result is False


def test_validate_twilio_signature_missing_signature():
    """Test _validate_twilio_signature returns False when signature is empty."""
    result = _validate_twilio_signature(
        "https://example.com", {"CallSid": "CA123"}, "", "token123"
    )
    assert result is False


# ---------- WebSocket Media Stream Tests ----------


async def test_handle_media_stream_processes_audio(session_factory, async_session):
    """Test handle_media_stream processes audio and calls STT/TTS."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    tenant = make_tenant(id=tenant_id)
    lead = make_lead(id=lead_id, tenant_id=tenant_id)
    async_session.add_all([tenant, lead])
    await async_session.commit()

    call = make_call(tenant_id=tenant_id, lead_id=lead_id, twilio_sid="CA_ws_test")
    async_session.add(call)
    await async_session.commit()

    # Mock STT that reports turn end
    mock_stt = AsyncMock()
    mock_stt.is_turn_end = False
    mock_stt.start_stream = AsyncMock()
    mock_stt.send_audio = AsyncMock()
    mock_stt.stop_stream = AsyncMock()

    # Mock TTS
    mock_tts = AsyncMock()

    async def mock_synthesize(text):
        yield b"audio_response"

    mock_tts.synthesize = mock_synthesize

    # Mock LLM
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Hello, how can I help?")

    mock_settings = MagicMock()
    mock_settings.voice_max_call_duration = 30
    mock_settings.voice_amd_enabled = True
    mock_settings.tracking_base_url = "http://localhost:8000"

    mock_twilio = AsyncMock()
    mock_twilio.end_call = AsyncMock(return_value=True)

    call_manager = CallManager(
        twilio_client=mock_twilio,
        stt=mock_stt,
        tts=mock_tts,
        llm_client=mock_llm,
        session_factory=session_factory,
        settings=mock_settings,
    )

    # Simulate websocket messages
    audio_payload = base64.b64encode(b"\x00\x01\x02").decode("utf-8")
    messages = [
        json.dumps({"event": "media", "media": {"payload": audio_payload}}),
        json.dumps({"event": "stop"}),
    ]

    mock_ws = _AsyncWSIter(messages)

    await call_manager.handle_media_stream(mock_ws, "CA_ws_test", stream_sid="ST_123")

    # Verify STT was started and stopped
    mock_stt.start_stream.assert_called_once()
    mock_stt.stop_stream.assert_called_once()
    # Verify audio was sent to STT
    mock_stt.send_audio.assert_called_once()


async def test_handle_media_stream_timeout(session_factory, async_session):
    """Test handle_media_stream terminates after max duration timeout."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    tenant = make_tenant(id=tenant_id)
    lead = make_lead(id=lead_id, tenant_id=tenant_id)
    async_session.add_all([tenant, lead])
    await async_session.commit()

    mock_stt = AsyncMock()
    mock_stt.is_turn_end = False
    mock_stt.start_stream = AsyncMock()
    mock_stt.send_audio = AsyncMock()
    mock_stt.stop_stream = AsyncMock()

    mock_settings = MagicMock()
    mock_settings.voice_max_call_duration = 1  # 1 second timeout

    mock_twilio = AsyncMock()
    mock_twilio.end_call = AsyncMock(return_value=True)

    call_manager = CallManager(
        twilio_client=mock_twilio,
        stt=mock_stt,
        tts=AsyncMock(),
        llm_client=AsyncMock(),
        session_factory=session_factory,
        settings=mock_settings,
    )

    # Websocket that never sends stop (hangs)
    class _SlowAsyncWSIter:
        def __init__(self):
            self.send = AsyncMock()

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(10)
            raise StopAsyncIteration

    mock_ws = _SlowAsyncWSIter()

    # Should complete quickly due to timeout (not hang for 10 seconds)
    await call_manager.handle_media_stream(mock_ws, "CA_timeout_test", stream_sid="ST_t")

    # Verify the call was ended due to timeout
    mock_twilio.end_call.assert_called_once_with("CA_timeout_test")


async def test_handle_media_stream_captures_stream_sid(session_factory, async_session):
    """Test that handle_media_stream uses stream SID from start event for audio."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    tenant = make_tenant(id=tenant_id)
    lead = make_lead(id=lead_id, tenant_id=tenant_id)
    async_session.add_all([tenant, lead])
    await async_session.commit()

    mock_stt = AsyncMock()
    mock_stt.is_turn_end = True  # Immediately trigger turn processing
    mock_stt.start_stream = AsyncMock()
    mock_stt.stop_stream = AsyncMock()

    # Capture the on_transcript callback and trigger it during send_audio
    on_transcript_cb = None

    async def capture_start_stream(language="en", on_transcript=None):
        nonlocal on_transcript_cb
        on_transcript_cb = on_transcript

    async def trigger_transcript(audio_bytes):
        if on_transcript_cb:
            on_transcript_cb({"text": "Hello there", "is_final": True, "confidence": 0.99})

    mock_stt.start_stream = AsyncMock(side_effect=capture_start_stream)
    mock_stt.send_audio = AsyncMock(side_effect=trigger_transcript)

    mock_tts = AsyncMock()

    async def mock_synthesize(text):
        yield b"audio_chunk"

    mock_tts.synthesize = mock_synthesize

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Response text")

    mock_settings = MagicMock()
    mock_settings.voice_max_call_duration = 30

    mock_twilio = AsyncMock()

    call_manager = CallManager(
        twilio_client=mock_twilio,
        stt=mock_stt,
        tts=mock_tts,
        llm_client=mock_llm,
        session_factory=session_factory,
        settings=mock_settings,
    )

    audio_payload = base64.b64encode(b"\x00\x01").decode("utf-8")
    messages = [
        json.dumps({
            "event": "start",
            "start": {"streamSid": "MZ_stream_abc", "callSid": "CA_call_123"},
        }),
        json.dumps({"event": "media", "media": {"payload": audio_payload}}),
        json.dumps({"event": "stop"}),
    ]

    mock_ws = _AsyncWSIter(messages)

    # Don't pass stream_sid to test that it's captured from the start event
    await call_manager.handle_media_stream(mock_ws, "CA_call_123")

    # Check that the sent media message uses the stream SID, not call SID
    mock_ws.send.assert_called()
    sent_msg = json.loads(mock_ws.send.call_args[0][0])
    assert sent_msg["streamSid"] == "MZ_stream_abc"
    assert sent_msg["event"] == "media"


# ---------- Scheduler Integration Tests ----------


async def test_scheduler_schedule_and_get_next_calls(session_factory):
    """Test that schedule_call stores entries and _get_next_calls retrieves them."""
    mock_settings = MagicMock()
    mock_settings.voice_calling_hours_start = 0
    mock_settings.voice_calling_hours_end = 23
    mock_settings.voice_concurrent_calls_limit = 5

    # Use a dict-based mock Redis
    store: dict[str, str] = {}
    sorted_sets: dict[str, dict[str, float]] = {}

    mock_redis = AsyncMock()

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, value, **kwargs):
        store[key] = value
        return True

    async def mock_zadd(key, mapping):
        if key not in sorted_sets:
            sorted_sets[key] = {}
        sorted_sets[key].update(mapping)

    async def mock_zrevrange(key, start, stop):
        if key not in sorted_sets:
            return []
        items = sorted(sorted_sets[key].items(), key=lambda x: x[1], reverse=True)
        return [item[0] for item in items[start : stop + 1]]

    mock_redis.get = AsyncMock(side_effect=mock_get)
    mock_redis.set = AsyncMock(side_effect=mock_set)
    mock_redis.zadd = AsyncMock(side_effect=mock_zadd)
    mock_redis.zrevrange = AsyncMock(side_effect=mock_zrevrange)

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=AsyncMock(),
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )
    scheduler._redis = mock_redis

    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    entry_id = await scheduler.schedule_call(
        lead_id=lead_id,
        tenant_id=tenant_id,
        campaign_id=None,
        priority=10,
    )

    assert entry_id is not None
    assert len(entry_id) == 36  # UUID format

    # Verify the entry was stored as JSON
    raw = store.get(f"voice:entry:{entry_id}")
    assert raw is not None
    parsed = json.loads(raw)
    assert parsed["lead_id"] == str(lead_id)
    assert parsed["tenant_id"] == str(tenant_id)
    assert parsed["attempts"] == 0

    # Verify _get_next_calls retrieves it
    next_calls = await scheduler._get_next_calls(str(tenant_id), limit=5)
    assert len(next_calls) == 1
    assert next_calls[0]["lead_id"] == str(lead_id)


async def test_scheduler_run_voice_tick_dispatches_calls(session_factory):
    """Test that run_voice_tick dispatches queued calls when within calling hours."""
    mock_settings = MagicMock()
    mock_settings.voice_calling_hours_start = 0
    mock_settings.voice_calling_hours_end = 23
    mock_settings.voice_concurrent_calls_limit = 5

    tenant_id = str(uuid.uuid4())
    lead_id = str(uuid.uuid4())

    # Prepare Redis state
    store: dict[str, str] = {}
    sorted_sets: dict[str, dict[str, float]] = {}
    active_sets: dict[str, set] = {}

    entry_id = str(uuid.uuid4())
    queue_key = f"voice:queue:{tenant_id}"
    entry_data = {
        "entry_id": entry_id,
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "campaign_id": "",
        "script_id": "",
        "attempts": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store[f"voice:entry:{entry_id}"] = json.dumps(entry_data)
    sorted_sets[queue_key] = {entry_id: 10.0}

    mock_redis = AsyncMock()

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, value, **kwargs):
        store[key] = value
        return True

    async def mock_zadd(key, mapping):
        if key not in sorted_sets:
            sorted_sets[key] = {}
        sorted_sets[key].update(mapping)

    async def mock_zrevrange(key, start, stop):
        if key not in sorted_sets:
            return []
        items = sorted(sorted_sets[key].items(), key=lambda x: x[1], reverse=True)
        return [item[0] for item in items[start : stop + 1]]

    async def mock_zrem(key, member):
        if key in sorted_sets:
            sorted_sets[key].pop(member, None)

    async def mock_scan(cursor=0, match="", count=100):
        keys = [k for k in sorted_sets.keys() if k.startswith("voice:queue:")]
        return (0, keys)

    async def mock_scard(key):
        return len(active_sets.get(key, set()))

    async def mock_sadd(key, member):
        if key not in active_sets:
            active_sets[key] = set()
        active_sets[key].add(member)

    mock_redis.get = AsyncMock(side_effect=mock_get)
    mock_redis.set = AsyncMock(side_effect=mock_set)
    mock_redis.zadd = AsyncMock(side_effect=mock_zadd)
    mock_redis.zrevrange = AsyncMock(side_effect=mock_zrevrange)
    mock_redis.zrem = AsyncMock(side_effect=mock_zrem)
    mock_redis.scan = AsyncMock(side_effect=mock_scan)
    mock_redis.scard = AsyncMock(side_effect=mock_scard)
    mock_redis.sadd = AsyncMock(side_effect=mock_sadd)
    mock_redis.expire = AsyncMock(return_value=True)

    mock_call_manager = AsyncMock()
    mock_call_manager.start_call = AsyncMock(return_value={"call_id": "call_123"})

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=mock_call_manager,
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )
    scheduler._redis = mock_redis

    await scheduler.run_voice_tick()

    # Verify the call was dispatched
    mock_call_manager.start_call.assert_called_once_with(
        lead_id=lead_id,
        tenant_id=tenant_id,
        campaign_id=None,
        script_id=None,
    )

    # Verify entry was removed from queue
    assert entry_id not in sorted_sets.get(queue_key, {})


async def test_scheduler_respects_concurrent_limit(session_factory):
    """Test that run_voice_tick respects the concurrent calls limit."""
    mock_settings = MagicMock()
    mock_settings.voice_calling_hours_start = 0
    mock_settings.voice_calling_hours_end = 23
    mock_settings.voice_concurrent_calls_limit = 1  # Only 1 concurrent call

    tenant_id = str(uuid.uuid4())

    sorted_sets: dict[str, dict[str, float]] = {}
    queue_key = f"voice:queue:{tenant_id}"
    sorted_sets[queue_key] = {"entry1": 10.0}

    mock_redis = AsyncMock()

    async def mock_scan(cursor=0, match="", count=100):
        keys = [k for k in sorted_sets.keys() if k.startswith("voice:queue:")]
        return (0, keys)

    # Already at the limit (1 active call)
    async def mock_scard(key):
        return 1

    mock_redis.scan = AsyncMock(side_effect=mock_scan)
    mock_redis.scard = AsyncMock(side_effect=mock_scard)

    mock_call_manager = AsyncMock()
    mock_call_manager.start_call = AsyncMock()

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=mock_call_manager,
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )
    scheduler._redis = mock_redis

    await scheduler.run_voice_tick()

    # No calls should be dispatched since we are at limit
    mock_call_manager.start_call.assert_not_called()


async def test_scheduler_retry_increments_attempts(session_factory):
    """Test that a failed dispatch increments the attempt counter and re-stores as JSON."""
    mock_settings = MagicMock()
    mock_settings.voice_calling_hours_start = 0
    mock_settings.voice_calling_hours_end = 23
    mock_settings.voice_concurrent_calls_limit = 5

    tenant_id = str(uuid.uuid4())
    lead_id = str(uuid.uuid4())

    store: dict[str, str] = {}
    sorted_sets: dict[str, dict[str, float]] = {}
    active_sets: dict[str, set] = {}

    entry_id = str(uuid.uuid4())
    queue_key = f"voice:queue:{tenant_id}"
    entry_data = {
        "entry_id": entry_id,
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "campaign_id": "",
        "script_id": "",
        "attempts": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store[f"voice:entry:{entry_id}"] = json.dumps(entry_data)
    sorted_sets[queue_key] = {entry_id: 5.0}

    mock_redis = AsyncMock()

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, value, **kwargs):
        store[key] = value
        return True

    async def mock_zrevrange(key, start, stop):
        if key not in sorted_sets:
            return []
        items = sorted(sorted_sets[key].items(), key=lambda x: x[1], reverse=True)
        return [item[0] for item in items[start : stop + 1]]

    async def mock_zrem(key, member):
        if key in sorted_sets:
            sorted_sets[key].pop(member, None)

    async def mock_scan(cursor=0, match="", count=100):
        keys = [k for k in sorted_sets.keys() if k.startswith("voice:queue:")]
        return (0, keys)

    async def mock_scard(key):
        return 0

    async def mock_sadd(key, member):
        if key not in active_sets:
            active_sets[key] = set()
        active_sets[key].add(member)

    mock_redis.get = AsyncMock(side_effect=mock_get)
    mock_redis.set = AsyncMock(side_effect=mock_set)
    mock_redis.zrevrange = AsyncMock(side_effect=mock_zrevrange)
    mock_redis.zrem = AsyncMock(side_effect=mock_zrem)
    mock_redis.scan = AsyncMock(side_effect=mock_scan)
    mock_redis.scard = AsyncMock(side_effect=mock_scard)
    mock_redis.sadd = AsyncMock(side_effect=mock_sadd)
    mock_redis.expire = AsyncMock(return_value=True)

    # Call manager that fails
    mock_call_manager = AsyncMock()
    mock_call_manager.start_call = AsyncMock(side_effect=RuntimeError("Twilio down"))

    scheduler = VoiceScheduler(
        session_factory=session_factory,
        call_manager=mock_call_manager,
        settings=mock_settings,
        redis_url="redis://localhost:6379/0",
    )
    scheduler._redis = mock_redis

    await scheduler.run_voice_tick()

    # Verify the entry was updated with incremented attempts as JSON
    raw = store[f"voice:entry:{entry_id}"]
    updated = json.loads(raw)
    assert updated["attempts"] == 1


# ---------- Phone Number Population Test ----------


async def test_call_manager_start_call_fetches_phone_number(
    session_factory, async_session
):
    """Test that start_call fetches the lead's phone from enrichment_data."""
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    tenant = make_tenant(id=tenant_id)
    lead = make_lead(
        id=lead_id,
        tenant_id=tenant_id,
        enrichment_data={"phone": "+15559876543", "company_size": 50},
    )
    addon = make_voice_addon(tenant_id=tenant_id)
    async_session.add_all([tenant, lead, addon])
    await async_session.commit()

    mock_twilio = AsyncMock()
    mock_twilio.initiate_call = AsyncMock(
        return_value={"call_sid": "CA_phone_test", "status": "initiated"}
    )

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

    result = await call_manager.start_call(lead_id=lead_id, tenant_id=tenant_id)

    assert result["call_id"] is not None
    # Verify the phone number was passed to initiate_call
    mock_twilio.initiate_call.assert_called_once()
    call_kwargs = mock_twilio.initiate_call.call_args
    assert call_kwargs.kwargs.get("to_number") == "+15559876543" or (
        call_kwargs[1].get("to_number") == "+15559876543"
        if len(call_kwargs) > 1
        else call_kwargs[0][0] == "+15559876543"
    )
