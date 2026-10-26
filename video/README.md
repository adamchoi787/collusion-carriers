# Explainer video

A 2:00 explainer for the report *Closing the Chat Ended the Cartel*, in seven sections at fixed timings ([`SCRIPT.md`](SCRIPT.md) has the script, the shot list and the word budgets). A single diagram builds up across the sections. The narration is [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0, voice `af_heart`), the score is original, and the animation is made in [Remotion](https://www.remotion.dev).

Everything is timed from Kokoro's own word timestamps, never from estimates. [`audio/timeline.py`](audio/timeline.py) places each section's clip inside its window, rebuilds the caption words from Kokoro's tokens (and fails if they don't reproduce [`script.json`](script.json) exactly), and turns named words into cue times that the animation reads from `src/timeline.json`.

| Step | Script | Output |
|---|---|---|
| Narration on a Modal CPU container | `modal run audio/modal_tts.py::narrate` | `audio/vo/<section>.wav` and `.json` (word timestamps) |
| Timeline, captions and cues | [`audio/timeline.py`](audio/timeline.py) | `src/timeline.json`, `build/vo.wav` |
| Score: MIDI rendered with FluidSynth and MuseScore General | [`audio/score.py`](audio/score.py) | `build/score.mid`, `build/music.wav` |
| Mix: music ducked 20 dB under the voice (BS.1770, per section), rising only in gaps; −14 LUFS, −1 dBTP ceiling | [`audio/mix.py`](audio/mix.py) | `public/mix.wav` |
| Render | `npm run render` | `out/explainer.mp4` |

The `modal` CLI is in the repository's `.venv`. The raw narration (`audio/vo/`) is committed, because Kokoro reads a line slightly differently on each run. Derived audio and video (`build/`, `public/mix.wav`, `out/`) are not committed. The `say` field in `script.json` holds pronunciation hints only, such as phonemes for "Qwen"; the words are identical to `text`.

## Checks

```bash
node check.mjs <dir> 15 0.25
```

Renders a still every 0.5 s with the layout checker on. It reports any text that overflows its box, leaves the frame, enters the caption band or overlaps other visible text.

```bash
python3 audio/check_captions.py out/explainer.mp4
```

Transcribes the final audio with faster-whisper `medium.en` ([`audio/modal_asr.py`](audio/modal_asr.py)) and aligns it word by word with the captions.

```bash
python3 verify.py out/explainer.mp4
```

Reports the duration and format, checks that section boundaries land within ±0.3 s of the brief, and measures loudness and true peak.

## Build

Requires Node 18+, Python 3 with numpy and scipy, `ffmpeg`/`ffprobe` and `fluidsynth` in `~/.local/share/av-env/bin` (a conda-forge environment), and `MuseScore_General.sf3` in `~/.local/share/soundfonts/`.

```bash
npm install
```

```bash
python3 audio/timeline.py && python3 audio/score.py && python3 audio/mix.py && npm run render
```
