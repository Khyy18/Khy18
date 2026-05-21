"""Energy-based Voice Activity Detection (VAD)."""

import logging
import math
import struct
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Default configuration
VAD_ENERGY_THRESHOLD = 0.01
VAD_SILENCE_DURATION_MS = 800
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit PCM
FRAME_DURATION_MS = 20  # Typical frame duration


def calculate_rms(audio_frame: bytes) -> float:
    """Calculate RMS energy of a 16-bit PCM audio frame.

    Args:
        audio_frame: Raw 16-bit PCM audio bytes (little-endian).

    Returns:
        RMS energy normalized to [0.0, 1.0].
    """
    if not audio_frame or len(audio_frame) < 2:
        return 0.0

    num_samples = len(audio_frame) // SAMPLE_WIDTH
    if num_samples == 0:
        return 0.0

    # Unpack 16-bit signed integers (little-endian)
    fmt = f"<{num_samples}h"
    try:
        samples = struct.unpack(fmt, audio_frame[:num_samples * SAMPLE_WIDTH])
    except struct.error:
        return 0.0

    # Calculate RMS, normalized by max 16-bit value
    sum_squares = sum(s * s for s in samples)
    rms = math.sqrt(sum_squares / num_samples) / 32768.0
    return rms


class VADProcessor:
    """Voice Activity Detection processor using energy thresholding.

    Buffers audio frames and detects complete utterances by looking
    for silence periods after speech activity.

    Usage:
        vad = VADProcessor()
        for chunk in audio_stream:
            utterance = vad.feed(chunk)
            if utterance is not None:
                # Process complete utterance
                process(utterance)
    """

    def __init__(
        self,
        energy_threshold: float = VAD_ENERGY_THRESHOLD,
        silence_duration_ms: int = VAD_SILENCE_DURATION_MS,
        sample_rate: int = SAMPLE_RATE,
    ):
        """Initialize VAD processor.

        Args:
            energy_threshold: RMS energy threshold for speech detection.
            silence_duration_ms: Duration of silence to mark end of utterance.
            sample_rate: Audio sample rate in Hz.
        """
        self.energy_threshold = energy_threshold
        self.silence_duration_ms = silence_duration_ms
        self.sample_rate = sample_rate

        self._buffer: bytearray = bytearray()
        self._speech_started: bool = False
        self._silence_frames: int = 0
        self._frames_per_silence: int = self._calculate_silence_frames()

    def _calculate_silence_frames(self) -> int:
        """Calculate how many frames of silence constitute end-of-utterance."""
        # Assume each feed() call provides one frame worth of audio
        # Frame duration depends on chunk size, but we use a conservative estimate
        frame_duration_ms = FRAME_DURATION_MS
        return max(1, self.silence_duration_ms // frame_duration_ms)

    def feed(self, audio_chunk: bytes) -> Optional[bytes]:
        """Feed an audio chunk and check for complete utterance.

        Args:
            audio_chunk: Raw 16-bit PCM audio bytes.

        Returns:
            Complete utterance bytes if end-of-speech detected, None otherwise.
        """
        if not audio_chunk:
            return None

        energy = calculate_rms(audio_chunk)

        if energy >= self.energy_threshold:
            # Speech detected
            self._speech_started = True
            self._silence_frames = 0
            self._buffer.extend(audio_chunk)
        elif self._speech_started:
            # Silence after speech
            self._silence_frames += 1
            self._buffer.extend(audio_chunk)

            if self._silence_frames >= self._frames_per_silence:
                # End of utterance detected
                utterance = bytes(self._buffer)
                self.reset()
                return utterance
        # else: silence before any speech - ignore

        return None

    def reset(self) -> None:
        """Reset the VAD processor state."""
        self._buffer = bytearray()
        self._speech_started = False
        self._silence_frames = 0

    def get_buffered_audio(self) -> Optional[bytes]:
        """Get any buffered audio without waiting for silence.

        Useful for flushing when a session ends.
        """
        if self._buffer and self._speech_started:
            utterance = bytes(self._buffer)
            self.reset()
            return utterance
        return None
