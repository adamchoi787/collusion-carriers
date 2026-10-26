"""Plot a WAV's loudness envelope and spectrogram with the timeline's cues marked.

    python video/audio/inspect_audio.py video/public/music.wav out.png
"""
import json
import sys
import wave
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIDEO = Path(__file__).resolve().parents[1]
tl = json.loads((VIDEO / "src/timeline.json").read_text())
with wave.open(sys.argv[1]) as w:
    sr, ch = w.getframerate(), w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float) / 32768
x = x.reshape(-1, ch).mean(axis=1)
hop = sr // 50
rms = np.sqrt(np.convolve(x ** 2, np.ones(hop * 2) / (hop * 2), mode="same")[::hop])
db = 20 * np.log10(rms + 1e-6)
t = np.arange(len(db)) / 50
fig, ax = plt.subplots(2, 1, figsize=(22, 8), sharex=True)
ax[0].plot(t, db, lw=0.6)
ax[0].set_ylim(-60, 0)
ax[1].specgram(x[::4], NFFT=1024, Fs=sr / 4, noverlap=512, cmap="magma", vmin=-120)
ax[1].set_ylim(0, 4000)
for k, v in tl["cues"].items():
    for a in ax:
        a.axvline(v, color="c", lw=0.5)
    ax[0].text(v, -2, k, rotation=90, fontsize=7, va="top")
for v in tl["sections"]:
    for a in ax:
        a.axvline(v, color="r", lw=1)
for c in tl["clips"]:
    ax[0].axvspan(c["start"], c["end"], color="g", alpha=0.08)
ax[1].set_xlim(0, tl["duration"] + 2)
ax[1].set_xticks(range(0, int(tl["duration"]) + 3, 2))
fig.tight_layout()
fig.savefig(sys.argv[2], dpi=70)
