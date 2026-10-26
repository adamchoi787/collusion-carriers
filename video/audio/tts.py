"""Generate the narration clips with OpenAI text-to-speech.

    python video/audio/tts.py            # writes video/public/vo/<id>.wav for every clip
    python video/audio/tts.py s3a s4b    # regenerate selected clips

Reads OPENAI_API_KEY from the repository's .env (never printed). One request per clip,
so each line can be timed and placed independently. Costs a few cents in total.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"
OUT = VIDEO / "public" / "vo"
MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")


def api_key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OPENAI_API_KEY not set in .env")


def synth(key: str, text: str, voice: str, instructions: str) -> bytes:
    body = json.dumps({"model": MODEL, "voice": voice, "input": text,
                       "instructions": instructions, "response_format": "wav"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main() -> None:
    script = json.loads((VIDEO / "script.json").read_text())
    only = set(sys.argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    key = api_key()
    for clip in script["clips"]:
        if only and clip["id"] not in only:
            continue
        audio = synth(key, clip.get("say", clip["text"]), script["voice"], script["instructions"])
        (OUT / f"{clip['id']}.wav").write_bytes(audio)
        print(clip["id"], len(audio), "bytes")


if __name__ == "__main__":
    main()
