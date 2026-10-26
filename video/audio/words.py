"""Trim silence from each narration clip and estimate word timestamps, offline.

    python video/audio/words.py

Reads video/public/vo/<id>.wav and video/script.json, and writes:
  video/public/vo_trim/<id>.wav   the clip with leading and trailing silence removed
  video/src/words.json            {id: {"duration": s, "words": [[word, start, end], ...]}}

Alignment: pauses in the loudness envelope are matched to the script's punctuation, so each
phrase gets its measured start and end; words inside a phrase share its time in proportion
to their length. That is accurate to a phrase and close enough within one for captions and cues.
"""
import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"
BIN = Path.home() / ".local/share/av-env/bin"
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
HOP = 0.01


def load(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float) / 32768
        return x, w.getframerate()


def pauses(x: np.ndarray, sr: int, min_gap: float = 0.12) -> list[tuple[float, float]]:
    """Silent stretches (start, end) inside the clip, longest first."""
    hop = int(sr * HOP)
    rms = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, mode="same")[::hop])
    quiet = rms < 10 ** (-40 / 20) * max(rms.max(), 1e-9) / 10 ** (-20 / 20)
    gaps, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        if not q and start is not None:
            if (i - start) * HOP >= min_gap and start > 0:
                gaps.append((start * HOP, i * HOP))
            start = None
    return sorted(gaps, key=lambda g: g[0] - g[1])


def phrases(text: str) -> list[list[str]]:
    out, cur = [], []
    for w in text.split():
        cur.append(w)
        if re.search(r"[,.?:!;]$", w):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def align(text: str, x: np.ndarray, sr: int) -> list:
    dur = len(x) / sr
    ph = phrases(text)
    gaps = sorted(pauses(x, sr)[: len(ph) - 1])
    if len(gaps) != len(ph) - 1:  # fall back to one phrase spanning the clip
        ph, gaps = [[w for p in ph for w in p]], []
    bounds = [0.0] + [g for gap in gaps for g in gap] + [dur]
    words = []
    for i, p in enumerate(ph):
        t0, t1 = bounds[2 * i], bounds[2 * i + 1]
        weight = [len(re.sub(r"\W", "", w)) + 1.5 for w in p]
        t = t0
        for w, wt in zip(p, weight):
            d = (t1 - t0) * wt / sum(weight)
            words.append([w, round(t, 3), round(t + d, 3)])
            t += d
    return words


def main() -> None:
    script = json.loads((VIDEO / "script.json").read_text())
    (VIDEO / "public/vo_trim").mkdir(parents=True, exist_ok=True)
    out = {}
    for clip in script["clips"]:
        src = VIDEO / "public/vo" / f"{clip['id']}.wav"
        dst = VIDEO / "public/vo_trim" / src.name
        subprocess.run([BIN / "ffmpeg", "-v", "error", "-y", "-i", src, "-af", TRIM, dst], check=True)
        x, sr = load(dst)
        out[clip["id"]] = {"duration": round(len(x) / sr, 3), "words": align(clip["text"], x, sr)}
    (VIDEO / "src/words.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print(k, v["duration"], " ".join(f"{w}@{s:.2f}" for w, s, _ in v["words"]))


if __name__ == "__main__":
    main()
