"""Compare the captions with what an independent speech recogniser hears in the final audio.

    python3 audio/check_captions.py <audio-or-video>

Extracts the audio, transcribes it with faster-whisper medium.en on Modal (audio/modal_asr.py),
aligns the transcript with the caption words from src/timeline.json, and reports every word
mismatch and the timing offset between caption words and recognised words. Spelling variants
(signalling/signaling), apostrophes (rival's/rivals) and number formats (41/forty-one) are
normalised before comparing; nothing else is. Writes build/asr.json and build/caption_check.txt.
"""

import difflib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AV = pathlib.Path.home() / ".local/share/av-env/bin"
MODAL = ROOT.parent / ".venv" / "bin" / "modal"

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
UK_US = {"signalling": "signaling", "maximise": "maximize", "utilisation": "utilization"}


def num_words(n: int) -> list[str]:
    if n < 20:
        return [ONES[n]]
    if n < 100:
        return [TENS[n // 10]] + ([ONES[n % 10]] if n % 10 else [])
    return [str(n)]


def tokens(text: str) -> list[str]:
    text = re.sub(r"(\d) \.(\d)", r"\1.\2", text.lower().replace("’", "'"))
    text = text.replace("%", " percent").replace("1.5", " one and a half ")
    text = re.sub(r"(\d)-(\d)", r"\1 \2", text)
    out = []
    for raw in re.split(r"[\s\-–—]+", text):
        w = re.sub(r"[^\w'.]", "", raw).strip("'.")
        if not w:
            continue
        if w.isdigit():
            out += num_words(int(w))
            continue
        m = re.fullmatch(r"([a-z]+)(\d+)", w)  # e.g. gpt6
        if m:
            out += [m.group(1)] + num_words(int(m.group(2)))
            continue
        w = w.replace("'", "")  # rival's / rivals / rivals' and AI's / AIs sound the same
        out.append(UK_US.get(w, w))
    return out


def main():
    src = pathlib.Path(sys.argv[1]).resolve()
    build = ROOT / "build"
    wav = build / "asr_input.wav"
    subprocess.run([str(AV / "ffmpeg"), "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    asr_path = build / "asr.json"
    subprocess.run([str(MODAL), "run", str(ROOT / "audio" / "modal_asr.py"), "--wav-path", str(wav),
                    "--out-path", str(asr_path), "--prompt", "GPT-6 Luna, Qwen."], check=True, capture_output=True)
    asr = json.loads(asr_path.read_text())
    tl = json.loads((ROOT / "src" / "timeline.json").read_text())

    # Flatten both sides to normalised tokens, keeping each token's time.
    cap = [(t, w["start"]) for w in tl["words"] for t in tokens(w["text"])]
    rec = [(t, w["start"], w["p"], w["end"] - w["start"]) for w in asr for t in tokens(w["text"])]
    sm = difflib.SequenceMatcher(a=[c[0] for c in cap], b=[r[0] for r in rec], autojunk=False)
    lines, offsets = [], []
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            offsets += [rec[b0 + k][1] - cap[a0 + k][1] for k in range(a1 - a0)]
        else:
            t = cap[a0][1] if a0 < len(cap) else rec[b0][1]
            lines.append(f"{t:7.2f}s  {op:8} caption: {' '.join(c[0] for c in cap[a0:a1]) or '—'}"
                         f"   |   heard: {' '.join(f'{r[0]} (p={r[2]:.2f}, {r[3]:.2f} s)' for r in rec[b0:b1]) or '—'}")
    offsets.sort()
    n = len(offsets)
    summary = [
        f"caption tokens {len(cap)}, recognised tokens {len(rec)}, matched {n}, mismatched blocks {len(lines)}",
        f"word-start offset (recognised − caption): median {offsets[n // 2]:+.3f} s, "
        f"5th–95th pct {offsets[int(n * 0.05)]:+.3f} … {offsets[int(n * 0.95)]:+.3f} s, "
        f"max |offset| {max(abs(o) for o in offsets):.3f} s",
        "transcript: " + " ".join(w["text"].strip() for w in asr),
    ]
    report = "\n".join(summary + ["", "mismatches:"] + (lines or ["  none"])) + "\n"
    (build / "caption_check.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
