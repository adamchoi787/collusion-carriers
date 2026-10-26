"""Place the narration clips on the 120 s timeline and derive captions and visual cues.

Reads script.json and audio/vo/<id>.{wav,json} (Kokoro audio and word timestamps). Writes:
  src/timeline.json   sections, caption words and phrases, cue times, speech intervals
  build/vo.wav        the narration alone on the 120 s timeline, 48 kHz mono

Caption words are rebuilt from Kokoro's own tokens and must reproduce the script text exactly,
so captions are word-for-word what was synthesised, at the times it was synthesised.
"""

import json
import pathlib
import re
import wave

import numpy as np
from scipy.signal import resample_poly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SR = 48000
TOTAL = 120.0
LEAD = 0.1  # seconds between a section's start and its clip's start (each clip has ~0.23 s of lead-in)

# Visual cues: (name, section, word as spoken, occurrence within that section's clip).
CUES = [
    ("s1_question", "s1", "if", 1), ("s1_colluding", "s1", "colluding", 1),
    ("s1_chat", "s1", "chat", 1), ("s1_sneakier", "s1", "sneakier", 1),
    ("s1_balloon", "s1", "balloon", 1), ("s1_squeeze", "s1", "squeezing", 1),
    ("s1_others", "s1", "others", 1),
    ("s2_firms", "s2", "two", 1), ("s2_contracts", "s2", "contracts", 1),
    ("s2_lowest", "s2", "lowest", 1), ("s2_allowed", "s2", "allowed", 1),
    ("s2_cartel", "s2", "cartel", 1), ("s2_sharing", "s2", "sharing", 1),
    ("s2_round41", "s2", "41", 1), ("s2_closed", "s2", "closed", 1),
    ("s2_routine", "s2", "routine", 1), ("s2_bits", "s2", "bits", 1),
    ("s2_tests", "s2", "tests", 1),
    ("s3_seeds", "s3", "32", 1), ("s3_models", "s3", "across", 1), ("s3_zero", "s3", "zero", 1),
    ("s3_stat", "s3", "statistically", 1), ("s3_luna", "s3", "gpt-6", 1), ("s3_cut", "s3", "cut", 1),
    ("s4_broken", "s4", "was", 1), ("s4_no", "s4", "no", 1), ("s4_code", "s4", "code", 1),
    ("s4_example", "s4", "capacity", 1), ("s4_qwen", "s4", "qwen", 1),
    ("s4_responded", "s4", "responded", 1), ("s4_chance", "s4", "chance", 1),
    ("s4_capacity", "s4", "capacity", 2), ("s4_idea", "s4", "idea", 1),
    ("s5_other", "s5", "other", 1), ("s5_found", "s5", "found", 1),
    ("s5_language", "s5", "language", 1), ("s5_rule", "s5", "rule", 1),
    ("s6_warnings", "s6", "two", 1), ("s6_button", "s6", "promised", 1),
    ("s6_nothing", "s6", "nothing", 1), ("s6_luna", "s6", "gpt-6", 1),
    ("s6_claimed", "s6", "agents", 1), ("s6_never", "s6", "never", 1), ("s6_trust", "s6", "trust", 1),
    ("s7_limits", "s7", "limits", 1), ("s7_reasoning", "s7", "low", 1),
    ("s7_warned", "s7", "weren't", 1), ("s7_next", "s7", "next", 1),
]


def norm(w: str) -> str:
    return re.sub(r"[^\w'\-.]", "", w.lower()).strip("'.").replace("’", "'")


def caption_words(tokens: list[dict]) -> list[dict]:
    """Merge Kokoro tokens into caption words: punctuation joins its neighbour as written."""
    words, prefix = [], ""
    for i, t in enumerate(tokens):
        if any(c.isalnum() for c in t["text"]):
            words.append({"text": prefix + t["text"], "start": t["start"], "end": t["end"], "ws": t["ws"]})
            prefix = ""
        elif words and not tokens[i - 1]["ws"]:
            words[-1]["text"] += t["text"]  # closing punctuation: no space before it
            words[-1]["ws"] = t["ws"]
        else:
            prefix += t["text"]  # opening quote: belongs to the next word
    return words


def read_wav(path: pathlib.Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        return x, w.getframerate()


def phrases(words: list[dict], max_chars: int = 44) -> list[dict]:
    """Group caption words into short phrases: split at clause punctuation, halve long clauses
    evenly, then merge very short neighbours. Quoted text is never split."""
    def text(i, j):
        return " ".join(words[k]["text"] for k in range(i, j + 1))

    clauses, start, quoted = [], 0, False
    for i, w in enumerate(words):
        quoted ^= w["text"].count("'") - w["text"].count("'s") - ("n't" in w["text"]) == 1
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or nxt["section"] != w["section"] or (w["text"][-1] in ".?!;:," and not quoted):
            clauses.append((start, i))
            start = i + 1

    out = []
    for i, j in clauses:
        parts = [(i, j)]
        while any(len(text(a, b)) > max_chars and b > a for a, b in parts):
            new = []
            for a, b in parts:
                if len(text(a, b)) > max_chars and b > a and not any(
                        words[k]["text"].startswith("'") for k in range(a, b + 1)):
                    total = len(text(a, b))
                    k = min(range(a, b), key=lambda k: abs(len(text(a, k)) - total / 2))
                    new += [(a, k), (k + 1, b)]
                else:
                    new.append((a, b))
            if new == parts:
                break
            parts = new
        out += [{"first": a, "last": b} for a, b in parts]

    merged = []
    for p in out:
        if merged:
            prev = merged[-1]
            same = words[p["first"]]["section"] == words[prev["last"]]["section"]
            prev_text, both = text(prev["first"], prev["last"]), text(prev["first"], p["last"])
            short = min(len(prev_text), len(text(p["first"], p["last"]))) <= 12
            if same and prev_text[-1] not in ".?!" and short and len(both) <= max_chars:
                prev["last"] = p["last"]
                continue
        merged.append(dict(p))
    for k, p in enumerate(merged):
        p["start"] = words[p["first"]]["start"]
        last_end = words[p["last"]]["end"]
        nxt = merged[k + 1] if k + 1 < len(merged) else None
        nxt_start = words[nxt["first"]]["start"] if nxt else last_end + 0.6
        p["end"] = min(nxt_start, last_end + 0.6) if nxt and nxt_start - last_end < 0.6 else last_end + 0.35
        p["text"] = " ".join(words[j]["text"] for j in range(p["first"], p["last"] + 1))
    return merged


def main():
    script = json.loads((ROOT / "script.json").read_text())
    vo = np.zeros(int(TOTAL * SR), dtype=np.float32)
    words, sections = [], []
    for sec in script["sections"]:
        sid = sec["id"]
        tokens = json.loads((ROOT / "audio" / "vo" / f"{sid}.json").read_text())
        cw = caption_words(tokens)
        rebuilt = "".join(w["text"] + (" " if w["ws"] else "") for w in cw).strip()
        if rebuilt != sec["text"].strip():
            raise SystemExit(f"{sid}: caption words do not reproduce the script\n  {rebuilt}\n  {sec['text']}")
        missing = [w["text"] for w in cw if w["start"] is None]
        if missing:
            raise SystemExit(f"{sid}: words without timestamps: {missing}")
        offset = sec["start"] + LEAD
        x, sr = read_wav(ROOT / "audio" / "vo" / f"{sid}.wav")
        x = resample_poly(x, SR // sr, 1) if sr != SR else x
        i0 = int(round(offset * SR))
        end = offset + len(x) / SR
        last_word_end = offset + cw[-1]["end"]
        if last_word_end > sec["end"] - 0.15:
            raise SystemExit(f"{sid}: speech runs to {last_word_end:.2f} s, past its window end {sec['end']}")
        vo[i0:i0 + len(x)] += x[: len(vo) - i0]
        for w in cw:
            words.append({"text": w["text"], "start": round(offset + w["start"], 3),
                          "end": round(offset + w["end"], 3), "section": sid})
        sections.append({"id": sid, "title": sec["title"], "start": sec["start"], "end": sec["end"],
                         "clipStart": round(offset, 3), "clipEnd": round(end, 3),
                         "speechStart": round(offset + cw[0]["start"], 3),
                         "speechEnd": round(last_word_end, 3)})

    cues = {}
    for name, sid, target, occ in CUES:
        hits = [w for w in words if w["section"] == sid and norm(w["text"]) == target]
        if len(hits) < occ:
            raise SystemExit(f"cue {name}: word '{target}' #{occ} not found in {sid}")
        cues[name] = hits[occ - 1]["start"]

    speech, cur = [], None
    for w in words:
        if cur and w["start"] - cur[1] < 0.35:
            cur[1] = w["end"]
        else:
            if cur:
                speech.append(cur)
            cur = [w["start"], w["end"]]
    speech.append(cur)

    out = {"fps": 30, "durationInFrames": int(TOTAL * 30), "sections": sections, "words": words,
           "phrases": phrases(words), "cues": cues, "speech": [[round(a, 3), round(b, 3)] for a, b in speech]}
    (ROOT / "src").mkdir(exist_ok=True)
    (ROOT / "src" / "timeline.json").write_text(json.dumps(out, indent=1))
    (ROOT / "build").mkdir(exist_ok=True)
    pcm = (np.clip(vo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(ROOT / "build" / "vo.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    for s in sections:
        print(f"{s['id']} {s['start']:>5}-{s['end']:<5} speech {s['speechStart']:6.2f}-{s['speechEnd']:6.2f}")
    print(f"{len(words)} words, {len(out['phrases'])} caption phrases, {len(cues)} cues")


if __name__ == "__main__":
    main()
