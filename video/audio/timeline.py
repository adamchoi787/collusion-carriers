"""Master timeline: where each narration clip starts and when each musical/visual cue fires.

    python video/audio/timeline.py     # writes video/src/timeline.json

Both the score (score.py) and the animation (src/) read this file, so a beat drop and the
element it accompanies always land on the same frame.
"""
import json
from pathlib import Path

VIDEO = Path(__file__).resolve().parents[1]
WORDS = json.loads((VIDEO / "src/words.json").read_text())

# Section start times (s). The brief's grid is 0/12/35/55/75/90/105/120; the narration is a
# little longer in Sections 1 and 6, so boundaries drift by a few seconds and the total stays < 2:00.
SECTIONS = [0.0, 15.5, 34.5, 51.0, 67.0, 81.0, 100.5, 118.5]

# Clip start times (s).
STARTS = {
    "s1a": 0.7, "s1b": 6.45,
    "s2a": 16.0, "s2b": 20.7,
    "s3a": 35.7, "s3b": 41.7,
    "s4a": 51.4, "s4b": 55.9, "s4c": 61.2,
    "s5a": 67.5, "s5b": 71.1, "s5c": 76.5,
    "s6a": 81.4, "s6b": 84.6, "s6c": 93.1,
    "s7a": 101.0, "s7b": 108.5,
}


def word(clip: str, text: str, edge: int = 1) -> float:
    """Absolute time of the first word in `clip` starting with `text` (edge 1 = start, 2 = end)."""
    for w in WORDS[clip]["words"]:
        if w[0].lower().strip(",.?:!").startswith(text.lower()):
            return round(STARTS[clip] + w[edge], 3)
    raise KeyError(f"{text!r} not in {clip}")


def end(clip: str) -> float:
    return round(STARTS[clip] + WORDS[clip]["duration"], 3)


def main() -> None:
    cues = {
        # Section 1: hook
        "balloon": word("s1b", "balloon"),
        "squeeze": word("s1b", "squeezing"),
        "others": word("s1b", "others"),
        "title": round(end("s1b") + 0.12, 3),
        # Section 2: setup
        "cartel": word("s2a", "cartel"),
        "closed": word("s2b", "closed"),
        "bits": word("s2b", "bits"),
        "actions": word("s2b", "actions"),
        "facts2": round(end("s2b") + 0.3, 3),
        # Section 3: result (the big drop lands on "zero")
        "build3": SECTIONS[2],
        "zero": word("s3a", "zero"),
        "drop3": round(end("s3a") + 0.12, 3),  # the line lands in near-silence, then the drop
        "worked": word("s3b", "worked"),
        "profit": word("s3b", "profit"),
        "counter": round(end("s3b") + 0.1, 3),
        # Section 4: control
        "broken": word("s4a", "broken"),
        "no": word("s4a", "no"),
        "code": word("s4b", "code"),
        "immediately": word("s4b", "immediately"),
        "drop4": round(end("s4b") + 0.1, 3),
        "capacity": word("s4c", "capacity"),
        "idea": word("s4c", "idea"),
        "facts4": round(end("s4c") + 0.25, 3),
        # Section 5: takeaway
        "talk": word("s5a", "talk"),
        "rule": word("s5b", "nothing"),
        "freetext": word("s5c", "would"),
        "untested": word("s5c", "haven't"),
        # Section 6: warnings
        "warn1": word("s6b", "promised"),
        "pressing": word("s6b", "pressing"),
        "claimed": word("s6c", "claimed"),
        "never": word("s6c", "never"),
        "trust": word("s6c", "don't"),
        # Section 7: limits and end card
        "limit1": word("s7a", "four"),
        "limit2": word("s7a", "weren't"),
        "next": word("s7b", "next"),
        "endcard": round(end("s7b") + 0.2, 3),
        "final": round(end("s7b") + 0.2 + 5 * 120 / 176, 3),  # finale at 176 bpm
    }
    clips = [{"id": k, "start": v, "end": end(k), "words": [[w, round(v + s, 3), round(v + e, 3)]
              for w, s, e in WORDS[k]["words"]]} for k, v in STARTS.items()]
    for a, b in zip(clips, clips[1:]):
        assert a["end"] + 0.2 <= b["start"], (a["id"], a["end"], b["start"])
    data = {"fps": 30, "duration": SECTIONS[-1], "sections": SECTIONS, "clips": clips, "cues": cues}
    (VIDEO / "src/timeline.json").write_text(json.dumps(data, indent=1))
    for k, v in cues.items():
        print(f"{k:12s} {v:7.2f}")


if __name__ == "__main__":
    main()
