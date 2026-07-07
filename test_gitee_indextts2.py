import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_URL = "https://ai.gitee.com/v1/audio/speech"
MODEL = "IndexTTS-2"
DEFAULT_REFERENCE_AUDIO = "小鱼.MP3"


def load_input_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text.strip()
    return Path(args.text_file).read_text(encoding="utf-8").strip()


def resolve_audio_reference(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("data:"):
        raise ValueError("Gitee IndexTTS-2 rejects data URLs; use a public audio URL.")

    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(f"Audio reference not found: {value}")

    raise ValueError(
        "Gitee IndexTTS-2 requires prompt_audio_url and emo_audio_prompt_url to "
        "be public URLs. Local audio files cannot be fetched by the API server."
    )


def create_speech(
    api_key: str,
    input_text: str,
    output_path: Path,
    prompt_audio_url: str,
    prompt_text: str,
    emo_audio_prompt_url: str,
    emo_alpha: float,
    voice: str,
) -> None:
    payload = {
        "input": input_text,
        "model": MODEL,
        "voice": voice,
        "prompt_audio_url": prompt_audio_url,
        "emo_audio_prompt_url": emo_audio_prompt_url,
        "emo_alpha": emo_alpha,
    }
    if prompt_text:
        payload["prompt_text"] = prompt_text

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/mpeg, audio/wav, application/json",
            "X-Failover-Enabled": "true",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if "data:audio/" in error_body:
            error_body = error_body[:1000] + "\n... redacted local audio data URL ..."
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc

    if "application/json" in content_type:
        text = body.decode("utf-8", errors="replace")
        raise RuntimeError(f"Expected audio but received JSON:\n{text}")

    output_path.write_bytes(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Gitee AI IndexTTS-2 speech synthesis."
    )
    parser.add_argument("--text", help="Text to synthesize.")
    parser.add_argument("--text-file", default="文案.txt", help="UTF-8 text file.")
    parser.add_argument("--output", default="gitee_indextts2.wav")
    parser.add_argument("--voice", default="alloy")
    parser.add_argument(
        "--prompt-audio-url",
        default=DEFAULT_REFERENCE_AUDIO,
        help="Public URL, data URL, or local MP3/WAV path for voice reference.",
    )
    parser.add_argument(
        "--prompt-text",
        default="",
        help="Transcript of prompt audio. Leave empty if unknown.",
    )
    parser.add_argument(
        "--emo-audio-prompt-url",
        default=DEFAULT_REFERENCE_AUDIO,
        help="Public URL, data URL, or local MP3/WAV path for emotion reference.",
    )
    parser.add_argument("--emo-alpha", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("GITEE_AI_API_KEY")
    if not api_key:
        print("Missing GITEE_AI_API_KEY environment variable.", file=sys.stderr)
        return 2

    try:
        create_speech(
            api_key=api_key,
            input_text=load_input_text(args),
            output_path=Path(args.output),
            prompt_audio_url=resolve_audio_reference(args.prompt_audio_url),
            prompt_text=args.prompt_text,
            emo_audio_prompt_url=resolve_audio_reference(args.emo_audio_prompt_url),
            emo_alpha=args.emo_alpha,
            voice=args.voice,
        )
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 1

    print(f"Saved synthesized audio to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
