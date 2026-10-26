"""Kokoro-82M narration on a Modal CPU container (Apache-2.0 model; weights baked into the image).

    modal run audio/modal_tts.py::samples   # voice samples -> voice_samples/
    python3 audio/tts.py                    # narration, calls `synth` remotely
"""

import io
import json
import pathlib

import modal

app = modal.App("collusion-explainer-tts")

tts_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("espeak-ng")
    .pip_install("torch==2.6.0", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("kokoro==0.9.4", "soundfile", "numpy<2.3", "transformers<5")
    .run_commands(
        "python -m spacy download en_core_web_sm",
        "python -c \"from kokoro import KPipeline; p=KPipeline(lang_code='a'); "
        "[p.load_voice(v) for v in ['af_heart','af_bella','am_michael','am_fenrir']]; "
        "q=KPipeline(lang_code='b'); [q.load_voice(v) for v in ['bf_emma','bm_george','bm_fable']]\"",
    )
)

SR = 24000


@app.function(image=tts_image, cpu=4, memory=4096, timeout=900)
def synth(lines: list[dict]) -> list[dict]:
    """Synthesise each line; return WAV bytes plus word timestamps (seconds from clip start).

    Each line is {"id", "say", "voice", "speed"}. Kokoro splits long text into chunks whose
    timestamps restart at zero, so each chunk is offset by the audio already produced.
    """
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipes = {}
    out = []
    for line in lines:
        lang = line["voice"][0]
        pipe = pipes.setdefault(lang, KPipeline(lang_code=lang))
        audio, words, offset = [], [], 0.0
        for res in pipe(line["say"], voice=line["voice"], speed=line.get("speed", 1.0), split_pattern=None):
            a = res.audio.numpy() if hasattr(res.audio, "numpy") else np.asarray(res.audio)
            for t in res.tokens or []:
                if t.start_ts is None or t.end_ts is None:
                    words.append({"text": t.text, "start": None, "end": None, "ws": t.whitespace})
                else:
                    words.append({"text": t.text, "start": offset + t.start_ts,
                                  "end": offset + t.end_ts, "ws": t.whitespace})
            audio.append(a)
            offset += len(a) / SR
        buf = io.BytesIO()
        sf.write(buf, np.concatenate(audio), SR, format="WAV", subtype="PCM_16")
        out.append({"id": line["id"], "wav": buf.getvalue(), "words": words})
    return out


SAMPLE_TEXT = ("Two AI firms formed a cartel by chatting: instead of competing, they secretly "
               "cooperated. Then we closed the chat, and measured, in bits, whether their private "
               "costs leaked into their ordinary actions instead.")


@app.local_entrypoint()
def samples():
    voices = [("af_heart", 1.0), ("bf_emma", 1.0), ("am_michael", 1.0), ("bm_george", 1.0)]
    res = synth.remote([{"id": v, "say": SAMPLE_TEXT, "voice": v, "speed": s} for v, s in voices])
    d = pathlib.Path(__file__).resolve().parent.parent / "voice_samples"
    d.mkdir(exist_ok=True)
    for i, r in enumerate(res, 1):
        (d / f"{i}_{r['id']}.wav").write_bytes(r["wav"])
        words = [w for w in r["words"] if w["text"].strip() and w["text"][0].isalnum()]
        dur = max(w["end"] for w in r["words"] if w["end"])
        print(f"{i}_{r['id']}: {len(words)} words, {dur:.1f} s, {60 * len(words) / dur:.0f} wpm")
    (d / "words.json").write_text(json.dumps([{k: r[k] for k in ("id", "words")} for r in res], indent=1))


@app.local_entrypoint()
def narrate(only: str = ""):
    """Synthesise every section of script.json (or a comma-separated subset) into audio/vo/."""
    root = pathlib.Path(__file__).resolve().parent.parent
    script = json.loads((root / "script.json").read_text())
    want = set(only.split(",")) if only else None
    lines = [{"id": s["id"], "say": s.get("say", s["text"]), "voice": script["voice"], "speed": s["speed"]}
             for s in script["sections"] if not want or s["id"] in want]
    out = root / "audio" / "vo"
    out.mkdir(exist_ok=True)
    for r in synth.remote(lines):
        (out / f"{r['id']}.wav").write_bytes(r["wav"])
        (out / f"{r['id']}.json").write_text(json.dumps(r["words"], indent=1))
        sec = next(s for s in script["sections"] if s["id"] == r["id"])
        dur = max(w["end"] for w in r["words"] if w["end"])
        n = len(sec["text"].split())
        print(f"{r['id']}: {n} words, speech {dur:.2f} s of {sec['end'] - sec['start']} s window, "
              f"{60 * n / dur:.0f} wpm")


@app.local_entrypoint()
def trial(lines_json: str, out_dir: str):
    """Synthesise ad-hoc lines ([{"id", "say", "speed"}]) for pronunciation checks."""
    root = pathlib.Path(__file__).resolve().parent.parent
    voice = json.loads((root / "script.json").read_text())["voice"]
    lines = [{**x, "voice": voice} for x in json.loads(lines_json)]
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for r in synth.remote(lines):
        (out / f"{r['id']}.wav").write_bytes(r["wav"])
        print(r["id"], " ".join(w["text"] for w in r["words"]))
