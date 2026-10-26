"""Objective checks on the rendered video.

    python3 verify.py out/explainer.mp4

- duration, resolution, frame rate and codecs (ffprobe);
- section boundaries: the largest frame-to-frame visual change within ±1 s of each boundary in
  the brief must land within ±0.3 s of it, and each section's narration must sit inside its window;
- loudness: integrated loudness and true peak of the final audio (ffmpeg ebur128).
"""

import json
import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
AV = pathlib.Path.home() / ".local/share/av-env/bin"
BOUNDS = [12, 35, 55, 75, 90, 105]


def run(*args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True)


def main():
    mp4 = pathlib.Path(sys.argv[1])
    ok = True
    probe = json.loads(run(AV / "ffprobe", "-v", "error", "-show_entries",
                           "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                           "-of", "json", mp4).stdout)
    dur = float(probe["format"]["duration"])
    print(f"duration {dur:.3f} s ({'ok' if 90 <= dur <= 120 else 'OUT OF RANGE'})")
    ok &= 90 <= dur <= 120
    for s in probe["streams"]:
        print("  stream", {k: v for k, v in s.items()})

    # Visual change around each boundary.
    w, h = 96, 54
    raw = run(AV / "ffmpeg", "-v", "error", "-i", mp4, "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-").stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, h * w).astype(np.float32)
    diff = np.abs(np.diff(frames, axis=0)).mean(1)  # diff[i]: change from frame i to i+1
    fps = 30
    tl = json.loads((ROOT / "src" / "timeline.json").read_text())
    print("section boundaries (largest visual change within ±1 s):")
    for b in BOUNDS:
        lo, hi = (b - 1) * fps, (b + 1) * fps
        k = lo + int(np.argmax(diff[lo:hi]))
        t = (k + 1) / fps
        good = abs(t - b) <= 0.3
        ok &= good
        print(f"  {b:>4} s → change peaks at {t:6.2f} s ({t - b:+.2f} s) {'ok' if good else 'MISSED'}")
    print("narration inside each section window:")
    for s in tl["sections"]:
        good = s["start"] <= s["speechStart"] and s["speechEnd"] <= s["end"]
        ok &= good
        print(f"  {s['id']} {s['start']:>3}–{s['end']:<3} s: speech {s['speechStart']:.2f}–{s['speechEnd']:.2f} s {'ok' if good else 'OUTSIDE'}")

    # Loudness of the delivered audio.
    log = subprocess.run([str(AV / "ffmpeg"), "-nostats", "-i", str(mp4), "-vn", "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = log[log.rindex("Summary:"):]
    I = float(summary.split("I:")[1].split("LUFS")[0])
    tp = float(summary.split("Peak:")[1].split("dBFS")[0])
    good = abs(I + 14) <= 0.5 and tp <= -1.0
    ok &= good
    print(f"loudness {I:.1f} LUFS integrated, true peak {tp:.1f} dBTP {'ok' if good else 'OFF TARGET'}")
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")


if __name__ == "__main__":
    main()
