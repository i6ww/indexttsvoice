from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APP_NAME = "MiaoTuVoiceFactory"
OLD_APP_NAME = "XiaoMiVoiceClone"
DEFAULT_AUDIO_URL = "https://www.panurl.cn/down.php/f1d29ad47d4716f37345514c853d6afc.mp3"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def config_path() -> Path:
    return app_data_dir() / "config.json"


def old_config_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / OLD_APP_NAME / "config.json"
    return Path.home() / f".{OLD_APP_NAME.lower()}" / "config.json"


@dataclass
class VoiceProfile:
    name: str = "小鱼"
    voice: str = "alloy"
    prompt_audio_url: str = DEFAULT_AUDIO_URL
    emo_audio_prompt_url: str = DEFAULT_AUDIO_URL
    prompt_text: str = ""
    emo_alpha: float = 1.0


def default_voice_profiles() -> list[VoiceProfile]:
    return [VoiceProfile()]


@dataclass
class AppConfig:
    api_key: str = ""
    base_url: str = "https://ai.gitee.com/v1"
    model: str = "IndexTTS-2"
    output_dir: str = "outputs"
    output_format: str = "wav"
    max_concurrent_tasks: int = 3
    silence_trim_mode: str = "off"
    failover_enabled: bool = True
    selected_voice_profile: str = "小鱼"
    voice_profiles: list[VoiceProfile] = field(default_factory=default_voice_profiles)


def load_config() -> AppConfig:
    config = AppConfig()
    env_key = os.environ.get("GITEE_AI_API_KEY", "")
    if env_key:
        config.api_key = env_key

    path = config_path()
    if not path.exists():
        legacy_path = old_config_path()
        if legacy_path.exists():
            path = legacy_path
    if not path.exists():
        return config

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config

    profiles = _load_voice_profiles(data)
    loaded = AppConfig(
        api_key=data.get("api_key", config.api_key),
        base_url=data.get("base_url", config.base_url),
        model=data.get("model", config.model),
        output_dir=data.get("output_dir", config.output_dir),
        output_format=str(data.get("output_format", config.output_format)).lower(),
        max_concurrent_tasks=_coerce_int(
            data.get("max_concurrent_tasks"), config.max_concurrent_tasks, 1, 10
        ),
        silence_trim_mode=str(data.get("silence_trim_mode", config.silence_trim_mode)),
        failover_enabled=bool(data.get("failover_enabled", config.failover_enabled)),
        selected_voice_profile=data.get(
            "selected_voice_profile", profiles[0].name
        ),
        voice_profiles=profiles,
    )
    if env_key:
        loaded.api_key = env_key
    if not any(profile.name == loaded.selected_voice_profile for profile in profiles):
        loaded.selected_voice_profile = profiles[0].name
    return loaded


def _load_voice_profiles(data: dict[str, Any]) -> list[VoiceProfile]:
    raw_profiles = data.get("voice_profiles")
    profiles: list[VoiceProfile] = []
    if isinstance(raw_profiles, list):
        for item in raw_profiles:
            if not isinstance(item, dict):
                continue
            profile = VoiceProfile(
                name=str(item.get("name") or "未命名音色"),
                voice=str(item.get("voice") or "alloy"),
                prompt_audio_url=str(item.get("prompt_audio_url") or ""),
                emo_audio_prompt_url=str(item.get("emo_audio_prompt_url") or ""),
                prompt_text=str(item.get("prompt_text") or ""),
                emo_alpha=_coerce_float(item.get("emo_alpha"), 1.0),
            )
            profiles.append(profile)

    if profiles:
        return profiles

    old_prompt_audio_url = data.get("prompt_audio_url")
    old_emo_audio_prompt_url = data.get("emo_audio_prompt_url")
    if old_prompt_audio_url or old_emo_audio_prompt_url:
        return [
            VoiceProfile(
                name="默认音色",
                voice=str(data.get("voice") or "alloy"),
                prompt_audio_url=str(old_prompt_audio_url or DEFAULT_AUDIO_URL),
                emo_audio_prompt_url=str(old_emo_audio_prompt_url or DEFAULT_AUDIO_URL),
                prompt_text=str(data.get("prompt_text") or ""),
                emo_alpha=_coerce_float(data.get("emo_alpha"), 1.0),
            )
        ]

    return default_voice_profiles()


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def save_config(config: AppConfig) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
