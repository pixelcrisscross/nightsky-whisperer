"""Bounded PCM audio capture helpers for NightSky Whisperer voice-link tests."""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterator

SAMPLE_RATE_HZ = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # PCM signed 16-bit little-endian
MAX_AUDIO_SECONDS = 15
MAX_AUDIO_BYTES = SAMPLE_RATE_HZ * CHANNELS * SAMPLE_WIDTH_BYTES * MAX_AUDIO_SECONDS
WS_CHUNK_BYTES = 8192

def normalize_pcm16(payload: bytes) -> bytes:
    """Return whole 16-bit samples only."""
    return payload if len(payload) % SAMPLE_WIDTH_BYTES == 0 else payload[:-1]

def write_pcm_wav(payload: bytes, path: str | Path, sample_rate_hz: int = SAMPLE_RATE_HZ) -> Path:
    """Persist mono PCM16 bytes as a standard WAV file."""
    pcm = normalize_pcm16(payload)
    if not pcm:
        raise ValueError("Cannot save an empty audio recording")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(int(sample_rate_hz))
        wav_file.writeframes(pcm)
    return output

def iter_pcm_chunks(payload: bytes, chunk_size: int = WS_CHUNK_BYTES) -> Iterator[bytes]:
    """Yield PCM in even-sized chunks for WebSocket binary frames."""
    size = max(SAMPLE_WIDTH_BYTES, int(chunk_size))
    if size % 2:
        size -= 1
    for start in range(0, len(payload), size):
        chunk = payload[start:start + size]
        if chunk:
            yield normalize_pcm16(chunk)
