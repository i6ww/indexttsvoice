from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

import lameenc
import miniaudio
import numpy as np


@dataclass(frozen=True)
class SilenceTrimSettings:
    min_silence_ms: int
    keep_silence_ms: int
    threshold_db: float


@dataclass(frozen=True)
class SilenceTrimResult:
    output_path: Path
    original_duration_ms: int
    processed_duration_ms: int
    compressed_segments: int


def shorten_silence(
    path: Path,
    min_silence_ms: int,
    keep_silence_ms: int,
    threshold_db: float,
) -> SilenceTrimResult:
    settings = SilenceTrimSettings(
        min_silence_ms=max(50, min(3000, int(min_silence_ms))),
        keep_silence_ms=max(30, min(2000, int(keep_silence_ms))),
        threshold_db=max(-80.0, min(-20.0, float(threshold_db))),
    )
    pcm, sample_rate, channels = _decode_audio(path)
    if pcm.size == 0:
        return SilenceTrimResult(path, 0, 0, 0)

    original_duration_ms = int((len(pcm) / sample_rate) * 1000)
    processed, compressed_segments = _compress_silence(pcm, sample_rate, settings)
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


def _decode_audio(path: Path) -> tuple[np.ndarray, int, int]:
    if path.suffix.lower() == ".wav":
        try:
            return _decode_wav(path)
        except (wave.Error, OSError, ValueError):
            pass
    decoded = miniaudio.decode_file(
        str(path),
        output_format=miniaudio.SampleFormat.SIGNED16,
    )
    sample_rate = int(decoded.sample_rate)
    channels = int(decoded.nchannels)
    pcm = np.frombuffer(decoded.samples, dtype=np.int16).reshape(-1, channels)
    return pcm, sample_rate, channels


def _decode_wav(path: Path) -> tuple[np.ndarray, int, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if channels <= 0 or sample_rate <= 0:
        raise ValueError("invalid wav metadata")
    if not frames:
        return np.empty((0, channels), dtype=np.int16), sample_rate, channels

    if sample_width == 1:
        pcm = (np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128) << 8
    elif sample_width == 2:
        pcm = np.frombuffer(frames, dtype="<i2").astype(np.int16, copy=False)
    elif sample_width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
        signed = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        signed = np.where(signed & 0x800000, signed | ~0xFFFFFF, signed)
        pcm = (signed >> 8).astype(np.int16)
    elif sample_width == 4:
        pcm = (np.frombuffer(frames, dtype="<i4") >> 16).astype(np.int16)
    else:
        raise ValueError(f"unsupported wav sample width: {sample_width}")

    usable = (pcm.size // channels) * channels
    if usable != pcm.size:
        pcm = pcm[:usable]
    return pcm.reshape(-1, channels), sample_rate, channels


def _compress_silence(
    pcm: np.ndarray,
    sample_rate: int,
    settings: SilenceTrimSettings,
) -> tuple[np.ndarray, int]:
    frame_ms = 20
    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    min_silence_frames = max(1, int(settings.min_silence_ms / frame_ms))
    keep_frames = max(1, int(settings.keep_silence_ms / frame_ms))

    mono = pcm.astype(np.float32).mean(axis=1)
    total_frames = int(np.ceil(len(mono) / frame_samples))
    silent = np.zeros(total_frames, dtype=bool)
    threshold = _db_to_amplitude(settings.threshold_db)

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
