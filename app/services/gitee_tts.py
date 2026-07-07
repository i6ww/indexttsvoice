from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class GiteeTTSRequest:
    api_key: str
    base_url: str
    model: str
    input_text: str
    output_path: Path
    voice: str
    prompt_audio_url: str
    emo_audio_prompt_url: str
    prompt_text: str = ""
    emo_alpha: float = 1.0
    failover_enabled: bool = True


class TTSServiceError(RuntimeError):
    """User-facing synthesis error."""


def require_public_url(value: str, field_name: str) -> None:
    label = _field_label(field_name)
    if not value.strip():
        raise ValueError(f"{label} 缺失：请先在音色库中填写公网音频 URL。")
    if not value.startswith(("http://", "https://")):
        raise ValueError(
            f"{label} 格式不正确：接口只能拉取公网 http/https 音频链接，不能使用本地文件路径。"
        )


async def create_speech(request: GiteeTTSRequest) -> Path:
    if not request.api_key.strip():
        raise TTSServiceError("API Key 缺失：请在设置中填写并保存 API Key。")
    require_public_url(request.prompt_audio_url, "prompt_audio_url")
    require_public_url(request.emo_audio_prompt_url, "emo_audio_prompt_url")
    request.output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "input": request.input_text,
        "model": request.model,
        "voice": request.voice,
        "prompt_audio_url": request.prompt_audio_url,
        "emo_audio_prompt_url": request.emo_audio_prompt_url,
        "emo_alpha": request.emo_alpha,
    }
    if request.prompt_text.strip():
        payload["prompt_text"] = request.prompt_text.strip()

    url = request.base_url.rstrip("/") + "/audio/speech"
    headers = {
        "Authorization": f"Bearer {request.api_key}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg, audio/wav, application/json",
    }
    if request.failover_enabled:
        headers["X-Failover-Enabled"] = "true"

    try:
        timeout = httpx.Timeout(300.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise TTSServiceError(
            "接口请求超时：服务器响应时间过长。请稍后重试，或减少单次并发生成数量。"
        ) from exc
    except httpx.ConnectError as exc:
        raise TTSServiceError(
            "网络连接失败：无法连接到语音合成接口，请检查网络、代理或 Base URL。"
        ) from exc
    except httpx.InvalidURL as exc:
        raise TTSServiceError("Base URL 格式不正确：请在设置中检查接口地址。") from exc
    except httpx.HTTPError as exc:
        raise TTSServiceError(f"网络请求失败：{exc}") from exc

    if response.status_code >= 400:
        raise TTSServiceError(_friendly_http_error(response))

    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        detail = _extract_error_message(response.text)
        raise TTSServiceError(f"接口没有返回音频：{detail or '请检查请求参数和音色配置。'}")

    output_path = _path_with_audio_suffix(request.output_path, content_type, response.content)
    await asyncio.to_thread(output_path.write_bytes, response.content)
    return output_path


def _path_with_audio_suffix(path: Path, content_type: str, content: bytes) -> Path:
    suffix = _suffix_from_audio_bytes(content) or _suffix_from_content_type(content_type)
    if suffix is None or path.suffix.lower() == suffix:
        return path
    return path.with_suffix(suffix)


def _suffix_from_audio_bytes(content: bytes) -> str | None:
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return ".wav"
    if content.startswith(b"ID3"):
        return ".mp3"
    if len(content) >= 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0:
        return ".mp3"
    return None


def _suffix_from_content_type(content_type: str) -> str | None:
    lowered = content_type.lower()
    if "mpeg" in lowered or "mp3" in lowered:
        return ".mp3"
    if "wav" in lowered or "wave" in lowered:
        return ".wav"
    return None


def _friendly_http_error(response: httpx.Response) -> str:
    status = response.status_code
    detail = _extract_error_message(response.text)
    lowered = f"{detail} {response.text}".lower()

    if status == 401:
        return "API Key 无效或已过期：请在设置中重新填写正确的 API Key，并点击保存设置。"
    if status == 403:
        return "API Key 权限不足：当前账号可能没有该模型或语音合成接口的调用权限。"
    if status == 404:
        return "接口地址不存在：请检查设置中的 Base URL 和模型接口地址。"
    if status == 408 or status == 504:
        return "接口请求超时：服务器处理时间过长，请稍后重试或降低同时生成数量。"
    if status == 429:
        return "请求过于频繁：接口触发限流，请降低同时生成数量，稍后再试。"
    if status in {400, 422} and _looks_like_reference_url_error(lowered):
        return (
            "参考音频 URL 拉取失败：接口服务器无法访问音色库中的音频链接。"
            "请确认链接是公网可访问的 mp3/wav 地址，并且浏览器无登录也能直接打开。"
        )
    if status >= 500:
        return f"接口服务异常（HTTP {status}）：请稍后重试。{detail}"
    return f"接口请求失败（HTTP {status}）：{detail or response.text[:500]}"


def _extract_error_message(text: str) -> str:
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        return text.strip()[:500]

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code") or error.get("type")
            if message:
                return str(message)
        for key in ("message", "msg", "detail", "error"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return text.strip()[:500]


def _looks_like_reference_url_error(text: str) -> bool:
    url_words = (
        "prompt_audio_url",
        "emo_audio_prompt_url",
        "audio url",
        "download",
        "fetch",
        "failed to fetch",
        "cannot access",
        "invalid url",
        "url",
    )
    audio_words = ("audio", "mp3", "wav", "reference", "prompt")
    return any(word in text for word in url_words) and any(
        word in text for word in audio_words
    )


def _field_label(field_name: str) -> str:
    if field_name == "prompt_audio_url":
        return "音色参考 URL"
    if field_name == "emo_audio_prompt_url":
        return "情绪参考 URL"
    return field_name
