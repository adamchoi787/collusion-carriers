# Explainer video

A 2-minute explainer for the report, *Closing the Chat Ended the Cartel*: narration, an orchestral re-arrangement of Offenbach's *Galop infernal* (the can-can, 1858, public domain) cut to the picture, and animation in [Remotion](https://www.remotion.dev).

One timeline drives everything. [`audio/timeline.py`](audio/timeline.py) places each narration line and names the cues (`zero`, `drop3`, `no`, `drop4`, `endcard`, …). The score and the animation both read `src/timeline.json`, so each beat drop and the element it accompanies land on the same frame.

| Step | Script | Output |
|---|---|---|
| Narration (OpenAI TTS, needs `OPENAI_API_KEY` in the repo's `.env`) | [`audio/tts.py`](audio/tts.py) | `public/vo/*.wav` |
| Trim silences and estimate word timings (offline) | [`audio/words.py`](audio/words.py) | `public/vo_trim/*.wav`, `src/words.json` |
| Timeline and cues | [`audio/timeline.py`](audio/timeline.py) | `src/timeline.json` |
| Score (MIDI) rendered with FluidSynth and the MuseScore General soundfont | [`audio/score.py`](audio/score.py) | `build/score.mid`, `public/music.wav`, `src/beats.json` |
| Mix: computed ducking (voice 15 dB over the music), two-pass loudnorm to −14 LUFS | [`audio/mix.py`](audio/mix.py) | `public/mix.wav` |
| Animation and render | `src/` | `out/explainer.mp4` |

The script text is in [`script.json`](script.json). Every number on screen comes from the report.

## Build

Requires Node 18+, Python 3 with numpy, `ffmpeg`/`ffprobe` and `fluidsynth` (the scripts look in `~/.local/share/av-env/bin`, a conda-forge environment), and `MuseScore_General.sf3` in `~/.local/share/soundfonts/`.

```bash
npm install
```

```bash
python3 audio/words.py && python3 audio/timeline.py && python3 audio/score.py && python3 audio/mix.py
```

```bash
npx remotion render src/index.ts Explainer out/explainer.mp4 --codec=h264 --crf=18 --audio-codec=aac --audio-bitrate=320k
```

`npx remotion studio src/index.ts` opens an interactive preview. `node stills.mjs <dir> <seconds…>` renders single frames for review, and `python3 audio/inspect_audio.py <wav> <png>` plots a mix's loudness and spectrogram against the cues.

The raw narration (`public/vo/`) is committed, because a new TTS run costs money and reads each line slightly differently. Derived audio and video (`public/*.wav`, `public/vo_trim/`, `build/`, `out/`) are not committed.
