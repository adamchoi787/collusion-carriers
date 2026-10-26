"""Mix narration and music into video/public/mix.wav.

    python video/audio/mix.py

1. Voice: each trimmed clip is placed at its timeline start and cleaned up with ffmpeg
   (high-pass, gentle compression, a little presence).
2. Music: light glue compression and a high shelf on the orchestra bus, then ducking: for every line, the music gain is set so the voice sits MARGIN dB above it,
   with fast attack and slow release ramps. Between lines, and on the drops, the music plays at
   full level. Stingers on cue words inside a line are ducked less, so they still punch.
3. Master: voice + ducked music, normalised to -14 LUFS integrated with a -1 dBTP ceiling
   (two-pass loudnorm), the usual target for streaming.
"""
import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

VIDEO = Path(__file__).resolve().parents[1]
BIN = Path.home() / ".local/share/av-env/bin"
TL = json.loads((VIDEO / "src/timeline.json").read_text())
DUR = TL["duration"]
SR = 48000
MARGIN = 15.0  # dB of voice over music while a line is spoken
STINGERS = ["closed", "no", "never", "trust", "pressing"]
BUILD = Path(VIDEO / "build")


def ffmpeg(*args):
    subprocess.run([BIN / "ffmpeg", "-hide_banner", "-v", "error", "-y", *map(str, args)], check=True)


def load(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getframerate() == SR, path
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        x = x.reshape(-1, w.getnchannels())
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    n = int(DUR * SR)
    return np.pad(x, ((0, max(0, n - len(x))), (0, 0)))[:n]


def save(path: Path, x: np.ndarray):
    y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(y.tobytes())


def voice_stem() -> np.ndarray:
    args, parts = [], []
    for i, c in enumerate(TL["clips"]):
        args += ["-i", VIDEO / "public/vo_trim" / f"{c['id']}.wav"]
        ms = int(round(c["start"] * 1000))
        parts.append(f"[{i}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{i}]")
    n = len(TL["clips"])
    parts.append("".join(f"[v{i}]" for i in range(n)) +
                 f"amix=inputs={n}:normalize=0:duration=longest,apad=whole_dur={DUR},"
                 f"atrim=0:{DUR},highpass=f=85,"
                 "acompressor=threshold=-20dB:ratio=3:attack=4:release=90:makeup=2,"
                 "equalizer=f=3200:t=q:w=1.1:g=2.5,equalizer=f=220:t=q:w=1:g=-1.5[out]")
    path = BUILD / "voice.wav"
    ffmpeg(*args, "-filter_complex", ";".join(parts), "-map", "[out]", "-ar", SR, path)
    return load(path)


def rms_db(x: np.ndarray) -> float:
    return 10 * np.log10(np.mean(x ** 2) + 1e-12)


def duck_envelope(voice: np.ndarray, music: np.ndarray) -> np.ndarray:
    rate = 100  # envelope points per second
    target = np.ones(int(DUR * rate) + 1)
    for c in TL["clips"]:
        a, b = int(c["start"] * SR), int(c["end"] * SR)
        gain = min(1.0, 10 ** ((rms_db(voice[a:b]) - MARGIN - rms_db(music[a:b])) / 20))
        lo, hi = int((c["start"] - 0.12) * rate), int((c["end"] + 0.2) * rate)
        target[lo:hi] = np.minimum(target[lo:hi], max(gain, 0.05))
    for k in STINGERS:
        t = TL["cues"][k]
        lo, hi = int((t - 0.01) * rate), int((t + 0.22) * rate)
        target[lo:hi] = np.maximum(target[lo:hi], 0.5)
    env = target.copy()
    down, up = np.exp(-1 / (0.06 * rate)), np.exp(-1 / (0.35 * rate))
    for i in range(1, len(env)):
        k = down if target[i] < env[i - 1] else up
        env[i] = k * env[i - 1] + (1 - k) * target[i]
    # Re-assert the stinger openings after smoothing (fast in, smoothed out).
    for k in STINGERS:
        t = TL["cues"][k]
        lo, hi = int((t - 0.01) * rate), int((t + 0.08) * rate)
        env[lo:hi] = np.maximum(env[lo:hi], 0.5)
    tt = np.arange(int(DUR * SR)) / SR
    return np.interp(tt, np.arange(len(env)) / rate, env).astype(np.float32)[:, None]


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    voice = voice_stem()
    bus = BUILD / "music_bus.wav"  # glue compression and a little air on the orchestra
    ffmpeg("-i", VIDEO / "public/music.wav", "-af",
           "acompressor=threshold=-16dB:ratio=2:attack=25:release=250:makeup=1.5,"
           "highshelf=f=9000:g=2,equalizer=f=60:t=q:w=1:g=1.5", "-ar", SR, bus)
    music = load(bus) * 0.9
    env = duck_envelope(voice, music)
    ducked = music * env
    for c in TL["clips"]:
        a, b = int(c["start"] * SR), int(c["end"] * SR)
        print(f"{c['id']}: voice over music {rms_db(voice[a:b]) - rms_db(ducked[a:b]):5.1f} dB")
    fade = np.clip((DUR - np.arange(len(voice)) / SR) / 0.9, 0, 1)[:, None]
    pre = BUILD / "premaster.wav"
    save(pre, (voice + ducked) * fade * 0.5)
    r = subprocess.run([BIN / "ffmpeg", "-hide_banner", "-i", pre, "-af",
                        "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    s = json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr)[-1])
    ln = ("loudnorm=I=-14:TP=-1.0:LRA=11:linear=true:"
          f"measured_I={s['input_i']}:measured_TP={s['input_tp']}:measured_LRA={s['input_lra']}:"
          f"measured_thresh={s['input_thresh']}:offset={s['target_offset']}")
    ffmpeg("-i", pre, "-af", ln, "-ar", SR, "-c:a", "pcm_s16le", VIDEO / "public/mix.wav")
    print("wrote", VIDEO / "public/mix.wav")


if __name__ == "__main__":
    main()
