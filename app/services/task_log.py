from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import app_data_dir


def log_dir() -> Path:
    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return bundle_dir / "log"
    return app_data_dir() / "logs"


def task_log_path() -> Path:
    return log_dir() / "tasks.jsonl"


def write_task_log(
    event: str,
    *,
    level: str | None = None,
    message: str | None = None,
    **fields: Any,
) -> None:
    path = task_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "level": _normalize_level(level or _infer_level(event)),
        "event": event,
        "message": message or _default_message(event),
        "pid": os.getpid(),
        **_json_safe(fields),
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _normalize_level(value: str) -> str:
    level = value.upper()
    if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return level
    return "INFO"


def _infer_level(event: str) -> str:
    lowered = event.lower()
    if "critical" in lowered:
        return "CRITICAL"
    if "failed" in lowered or "error" in lowered or "timeout" in lowered:
        if lowered == "silence_trim_failed":
            return "WARNING"
        return "ERROR"
    if "warning" in lowered or "skipped" in lowered:
        return "WARNING"
    if "prepared" in lowered or "received" in lowered:
        return "DEBUG"
    return "INFO"


def _default_message(event: str) -> str:
    messages = {
        "started": "开始生成语音",
        "finished": "语音生成完成",
        "failed": "语音生成失败",
        "silence_trim_finished": "停顿处理完成",
        "silence_trim_failed": "停顿处理失败，已保留原音频",
        "tts_request_prepared": "语音合成请求已准备",
        "tts_response_received": "语音合成接口已响应",
        "tts_output_written": "接口音频已写入本地文件",
        "tts_timeout": "语音合成接口请求超时",
        "tts_connection_error": "语音合成接口连接失败",
        "tts_invalid_url": "语音合成接口地址格式错误",
        "tts_http_error": "语音合成接口返回错误",
        "tts_response_error": "语音合成接口响应不是可用音频",
    }
    return messages.get(event, event)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseException):
        return str(value)
    return value
