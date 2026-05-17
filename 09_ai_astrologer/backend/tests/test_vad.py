"""Tests for Voice Activity Detection (VAD)."""

import struct
import math

import pytest

from app.vad import VADProcessor, calculate_rms, VAD_ENERGY_THRESHOLD


class TestRMSCalculation:
    """Tests for RMS energy calculation."""

    def test_silence_has_zero_energy(self):
        """Test that a silent frame has zero RMS energy."""
        # 100 samples of silence (16-bit zeros)
        silent_frame = struct.pack("<100h", *([0] * 100))
        energy = calculate_rms(silent_frame)
        assert energy == 0.0

    def test_full_volume_has_max_energy(self):
        """Test that max amplitude gives high RMS energy."""
        # 100 samples at max amplitude
        max_frame = struct.pack("<100h", *([32767] * 100))
        energy = calculate_rms(max_frame)
        assert energy > 0.9  # Close to 1.0

    def test_moderate_signal(self):
        """Test that a moderate signal gives moderate energy."""
        # 100 samples at half amplitude
        half_frame = struct.pack("<100h", *([16384] * 100))
        energy = calculate_rms(half_frame)
        assert 0.3 < energy < 0.7

    def test_empty_frame_returns_zero(self):
        """Test that an empty frame returns zero energy."""
        assert calculate_rms(b"") == 0.0
        assert calculate_rms(b"\x00") == 0.0

    def test_alternating_signal(self):
        """Test RMS of alternating positive/negative signal."""
        # Alternating +16384 / -16384
        samples = [16384, -16384] * 50
        frame = struct.pack("<100h", *samples)
        energy = calculate_rms(frame)
        assert energy > 0.3


class TestVADProcessor:
    """Tests for the VAD processor."""

    def _make_speech_frame(self, amplitude=5000, num_samples=320):
        """Create a frame that registers as speech."""
        samples = [amplitude] * num_samples
        return struct.pack(f"<{num_samples}h", *samples)

    def _make_silence_frame(self, num_samples=320):
        """Create a frame that registers as silence."""
        return struct.pack(f"<{num_samples}h", *([0] * num_samples))

    def test_initial_state(self):
        """Test that VAD starts with no buffered audio."""
        vad = VADProcessor()
        assert vad.get_buffered_audio() is None

    def test_silence_before_speech_ignored(self):
        """Test that silence before speech is ignored."""
        vad = VADProcessor()
        silence = self._make_silence_frame()
        result = vad.feed(silence)
        assert result is None
        assert vad.get_buffered_audio() is None

    def test_speech_starts_buffering(self):
        """Test that speech starts buffering audio."""
        vad = VADProcessor(energy_threshold=0.01)
        speech = self._make_speech_frame()
        result = vad.feed(speech)
        assert result is None  # Not enough silence to end utterance
        # But there should be buffered audio
        buffered = vad.get_buffered_audio()
        assert buffered is not None
        assert len(buffered) > 0

    def test_utterance_detected_after_silence(self):
        """Test that utterance is returned after sufficient silence."""
        vad = VADProcessor(
            energy_threshold=0.01,
            silence_duration_ms=60,  # Short for testing
        )
        # Recalculate frames per silence for the shorter duration
        vad._frames_per_silence = 3

        speech = self._make_speech_frame()
        silence = self._make_silence_frame()

        # Feed some speech
        for _ in range(5):
            result = vad.feed(speech)
            assert result is None

        # Feed silence frames to trigger utterance detection
        for i in range(2):
            result = vad.feed(silence)
            assert result is None

        # The third silence frame should trigger detection
        result = vad.feed(silence)
        assert result is not None
        assert len(result) > 0

    def test_reset_clears_state(self):
        """Test that reset clears all internal state."""
        vad = VADProcessor(energy_threshold=0.01)
        speech = self._make_speech_frame()
        vad.feed(speech)
        assert vad.get_buffered_audio() is not None

        # Create new instance to test reset on fresh one
        vad2 = VADProcessor(energy_threshold=0.01)
        vad2.feed(speech)
        vad2.reset()
        assert vad2.get_buffered_audio() is None

    def test_multiple_utterances(self):
        """Test detection of multiple consecutive utterances."""
        vad = VADProcessor(energy_threshold=0.01, silence_duration_ms=60)
        vad._frames_per_silence = 2

        speech = self._make_speech_frame()
        silence = self._make_silence_frame()

        # First utterance
        for _ in range(3):
            vad.feed(speech)
        result1 = None
        for _ in range(3):
            r = vad.feed(silence)
            if r is not None:
                result1 = r
        assert result1 is not None

        # Second utterance
        for _ in range(3):
            vad.feed(speech)
        result2 = None
        for _ in range(3):
            r = vad.feed(silence)
            if r is not None:
                result2 = r
        assert result2 is not None

    def test_empty_chunk_returns_none(self):
        """Test that empty audio chunk returns None."""
        vad = VADProcessor()
        assert vad.feed(b"") is None
        assert vad.feed(None) is None

    def test_custom_threshold(self):
        """Test that custom threshold affects detection."""
        # Very high threshold - speech should not be detected
        vad = VADProcessor(energy_threshold=0.99)
        # Use moderate amplitude that would normally be speech
        speech = self._make_speech_frame(amplitude=5000)
        vad.feed(speech)
        # Should not have started speech detection
        assert vad._speech_started is False

    def test_get_buffered_audio_when_no_speech(self):
        """Test get_buffered_audio returns None when no speech detected."""
        vad = VADProcessor()
        assert vad.get_buffered_audio() is None
