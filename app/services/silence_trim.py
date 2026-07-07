from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lameenc
import miniaudio
import numpy as np


@dataclass(frozen=True)
class SilenceTrimPreset:
    label: str
    min_silence_ms: int
    keep_silence_ms: int
    threshold_db: float


@dataclass(frozen=True)
class SilenceTrimResult:
    output_path: Path
    original_duration_ms: int
    processed_duration_ms: int
    compressed_segments: int


SILENCE_TRIM_PRESETS: dict[str, SilenceTrimPreset] = {
    "off": SilenceTrimPreset("关闭", 0, 0, -45.0),
    "natural": SilenceTrimPreset("自然", 600, 350, -45.0),
    "compact": SilenceTrimPreset("紧凑", 350, 180, -45.0),
    "short": SilenceTrimPreset("极短", 220, 100, -45.0),
}

SILENCE_TRIM_LABELS: dict[str, str] = {
    key: preset.label for key, preset in SILENCE_TRIM_PRESETS.items()
}


def normalize_silence_trim_mode(value: str) -> str:
    if value in SILENCE_TRIM_PRESETS:
        return value
    return "off"


def shorten_silence(path: Path, mode: str) -> SilenceTrimResult:
    mode = normalize_silence_trim_mode(mode)
    preset = SILENCE_TRIM_PRESETS[mode]
    if mode == "off":
        return SilenceTrimResult(path, 0, 0, 0)

    decoded = miniaudio.decode_file(
        str(path),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=2,
        sample_rate=44100,
    )
    sample_rate = int(decoded.sample_rate)
    channels = int(decoded.nchannels)
    pcm = np.frombuffer(decoded.samples, dtype=np.int16).reshape(-1, channels)
    if pcm.size == 0:
        return SilenceTrimResult(path, 0, 0, 0)

    original_duration_ms = int((len(pcm) / sample_rate) * 1000)
    processed, compressed_segments = _compress_silence(pcm, sample_rate, preset)
    processed_duration_ms = int((len(processed) / sample_rate) * 1000)

    if compressed_segments <= 0 or len(processed) >= len(pcm):
        return SilenceTrimResult(path, original_duration_ms, original_duration_ms, 0)

    if path.suffix.lower() == ".mp3":
        _write_mp3(path, processed, sample_rate, channels)
    elif path.suffix.lower() == ".wav":
        _write_wav(path, processed, sample_rate)
    else:
        target = path.with_suffix(".mp3")
        _write_mp3(target, processed, sample_rate, channels)
        path.unlink(missing_ok=True)
        path = target

    return SilenceTrimResult(
        output_path=path,
        original_duration_ms=original_duration_ms,
        processed_duration_ms=processed_duration_ms,
        compressed_segments=compressed_segments,
    )


def _compress_silence(
    pcm: np.ndarray,
    sample_rate: int,
    preset: SilenceTrimPreset,
) -> tuple[np.ndarray, int]:
    frame_ms = 20
    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    min_silence_frames = max(1, int(preset.min_silence_ms / frame_ms))
    keep_frames = max(1, int(preset.keep_silence_ms / frame_ms))

    mono = pcm.astype(np.float32).mean(axis=1)
    total_frames = int(np.ceil(len(mono) / frame_samples))
    silent = np.zeros(total_frames, dtype=bool)
    threshold = _db_to_amplitude(preset.threshold_db)

    for frame_index in range(total_frames):
        start = frame_index * frame_samples
        end = min(len(mono), start + frame_samples)
        frame = mono[start:end]
        if frame.size == 0:
            continue
        rms = float(np.sqrt(np.mean(frame * frame)))
        silent[frame_index] = rms <= threshold

    chunks: list[np.ndarray] = []
    compressed_segments = 0
    frame_index = 0
    while frame_index < total_frames:
        start_frame = frame_index
        is_silent = silent[frame_index]
        while frame_index < total_frames and silent[frame_index] == is_silent:
            frame_index += 1
        end_frame = frame_index

        start_sample = start_frame * frame_samples
        end_sample = min(len(pcm), end_frame * frame_samples)
        if is_silent and end_frame - start_frame >= min_silence_frames:
            keep_samples = min(end_sample - start_sample, keep_frames * frame_samples)
            end_sample = start_sample + keep_samples
            compressed_segments += 1
        chunks.append(pcm[start_sample:end_sample])

    if not chunks:
        return pcm, 0
    return np.concatenate(chunks), compressed_segments


def _db_to_amplitude(db: float) -> float:
    return 32767.0 * (10.0 ** (db / 20.0))


def _write_mp3(path: Path, pcm: np.ndarray, sample_rate: int, channels: int) -> None:
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(192)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    encoded = encoder.encode(pcm.astype(np.int16).tobytes()) + encoder.flush()
    path.write_bytes(encoded)


def _write_wav(path: Path, pcm: np.ndarray, sample_rate: int) -> None:
    import wave

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(pcm.shape[1])
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.astype(np.int16).tobytes())
