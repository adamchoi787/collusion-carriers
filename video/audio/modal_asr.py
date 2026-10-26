"""faster-whisper (MIT) transcription with word timestamps, on a Modal CPU container.

Used only to check that the captions match what the narration actually says.
"""

import modal

app = modal.App("collusion-explainer-asr")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("faster-whisper==1.1.1", "requests")
    .run_commands("python -c \"from faster_whisper import WhisperModel; "
                  "WhisperModel('medium.en', device='cpu', compute_type='int8')\"")
)


@app.function(image=image, cpu=8, memory=8192, timeout=1200)
def transcribe(wav: bytes, prompt: str = "") -> list[dict]:
    import tempfile

    from faster_whisper import WhisperModel

    model = WhisperModel("medium.en", device="cpu", compute_type="int8", cpu_threads=8)
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        f.write(wav)
        f.flush()
        segs, _ = model.transcribe(f.name, language="en", word_timestamps=True, beam_size=5,
                                   initial_prompt=prompt or None, condition_on_previous_text=False)
        return [{"text": w.word, "start": w.start, "end": w.end, "p": w.probability}
                for s in segs for w in s.words]


@app.local_entrypoint()
def main(wav_path: str, out_path: str, prompt: str = ""):
    import json
    import pathlib

    words = transcribe.remote(pathlib.Path(wav_path).read_bytes(), prompt)
    pathlib.Path(out_path).write_text(json.dumps(words, indent=1))
    print(" ".join(w["text"].strip() for w in words))
