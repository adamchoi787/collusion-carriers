"""Duck the music under the narration and master the mix.

Music sits DUCK_DB below the narration while anyone is speaking (measured as BS.1770 loudness
over the speech regions), and rises by RISE_DB only in gaps of at least MIN_GAP seconds. The mix
is then normalised to -14 LUFS integrated with true peak at or below -1 dBTP.

Reads build/vo.wav, build/music.wav and src/timeline.json; writes public/mix.wav and prints the
measured voice-over-music margin per section.
"""

import json
import pathlib
import wave

import numpy as np
from scipy.signal import lfilter, resample_poly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SR = 48000
DUCK_DB = 20.0
RISE_DB = 9.0
MIN_GAP = 0.8
TARGET_LUFS = -14.0
TP_CEILING = -1.0


def read(path):
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
        return x.reshape(-1, w.getnchannels()).T, w.getframerate()


def kweight(x):
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1, -1.99004745483398, 0.99007225036621]
    return lfilter(b2, a2, lfilter(b1, a1, x, axis=-1), axis=-1)


def block_power(x):
    """Mean-square K-weighted power of 400 ms blocks with 75% overlap, summed over channels."""
    z = kweight(np.atleast_2d(x)) ** 2
    n, hop = int(0.4 * SR), int(0.1 * SR)
    starts = np.arange(0, z.shape[1] - n + 1, hop)
    c = np.cumsum(np.pad(z, ((0, 0), (1, 0))), axis=1)
    return ((c[:, starts + n] - c[:, starts]) / n).sum(0), starts


def lufs(x, mask=None):
    """Gated integrated loudness (BS.1770-4); with mask, only blocks fully inside the mask count."""
    p, starts = block_power(x)
    if mask is not None:
        n = int(0.4 * SR)
        cm = np.concatenate([[0], np.cumsum(mask)])
        p = p[(cm[starts + n] - cm[starts]) == n]
    l = -0.691 + 10 * np.log10(p + 1e-20)
    p = p[l > -70]
    if not len(p):
        return -np.inf
    rel = -0.691 + 10 * np.log10(p.mean()) - 10
    p = p[-0.691 + 10 * np.log10(p) > rel]
    return -0.691 + 10 * np.log10(p.mean())


def true_peak_db(x):
    up = resample_poly(np.atleast_2d(x), 4, 1, axis=-1)
    return 20 * np.log10(np.abs(up).max() + 1e-20)


def limit(x, ceiling_db, lookahead=0.004, release=0.08):
    """Lookahead peak limiter on the 4x-oversampled peak, so true peak stays under the ceiling."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d

    c = 10 ** (ceiling_db / 20)
    up = np.abs(resample_poly(x, 4, 1, axis=-1)).max(0)
    peak = up[: x.shape[1] * 4].reshape(-1, 4).max(1)
    need = np.minimum(1.0, c / np.maximum(peak, 1e-9))
    L = int(lookahead * SR)
    g = minimum_filter1d(need, 2 * L + 1, origin=-L)       # look ahead L samples
    g = uniform_filter1d(g, L, origin=-(L // 2))          # smooth the attack inside the lookahead
    g = np.minimum(g, minimum_filter1d(need, 2 * L + 1))
    k = 1 - np.exp(-1 / (release * SR))
    out, cur = np.empty_like(g), 1.0
    for i, v in enumerate(g):                               # release: recover slowly, drop instantly
        cur = v if v < cur else cur + (v - cur) * k
        out[i] = cur
    return x * out, 20 * np.log10(out.min())


def envelope(n, speech):
    """Music gain in dB relative to the ducked level: 0 under speech, +RISE_DB in long gaps."""
    t = np.arange(n) / SR
    regions = [(max(0, a - 0.25), b + 0.35) for a, b in speech]
    merged = []
    for a, b in regions:
        if merged and a - merged[-1][1] < MIN_GAP:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    g = np.full(n, RISE_DB)
    attack, release = 0.35, 0.6
    for a, b in merged:
        # fall to 0 dB by a (start ramp `attack` earlier), rise back over `release` after b
        down = np.clip((t - (a - attack)) / attack, 0, 1)
        up = np.clip((t - b) / release, 0, 1)
        inside = 1 - np.maximum(1 - down, up)  # 1 inside the region, ramps at both edges
        g = np.minimum(g, RISE_DB * (1 - inside))
    return g


def main():
    tl = json.loads((ROOT / "src" / "timeline.json").read_text())
    vo, sr = read(ROOT / "build" / "vo.wav")
    mu, sr2 = read(ROOT / "build" / "music.wav")
    assert sr == sr2 == SR
    n = int(120 * SR)
    vo = np.pad(vo[:, :n], ((0, 0), (0, n - min(n, vo.shape[1]))))[0]
    mu = np.pad(mu[:, :n], ((0, 0), (0, n - min(n, mu.shape[1]))))

    speech = tl["speech"]
    smask = np.zeros(n, dtype=np.int64)
    for a, b in speech:
        smask[int(a * SR):int(b * SR)] = 1

    # Voice is mono, played equally in both channels; measure it as the stereo signal it becomes.
    vo2 = np.vstack([vo, vo])
    v_speech = lufs(vo2, smask)
    # Calibrate the ducked level per section (the score's dynamics differ between sections),
    # crossfading the calibration over 1 s at each boundary.
    t = np.arange(n) / SR
    base = np.zeros(n)
    weight = np.zeros(n)
    for s in tl["sections"]:
        sec = np.zeros(n, dtype=np.int64)
        sec[int(s["start"] * SR):int(s["end"] * SR)] = 1
        m = smask & sec
        b = (lufs(vo2, m) - DUCK_DB) - lufs(mu, m)
        w = np.clip(np.minimum(t - s["start"] + 0.5, s["end"] + 0.5 - t), 0, 1)
        base += b * w
        weight += w
    base /= np.maximum(weight, 1e-9)
    g_db = base + envelope(n, speech)
    mu_d = mu * 10 ** (g_db / 20)

    mix0 = vo2 + mu_d
    gain = TARGET_LUFS - lufs(mix0)
    for _ in range(4):  # limiting lowers loudness a little, so re-gain and re-limit until stable
        mix, gr = limit(mix0 * 10 ** (gain / 20), TP_CEILING - 0.5)
        err = TARGET_LUFS - lufs(mix)
        if abs(err) < 0.05:
            break
        gain += err
    tp = true_peak_db(mix)
    if tp > TP_CEILING:
        raise SystemExit(f"true peak {tp:.2f} dBTP is above the ceiling")
    print(f"limiter: up to {-gr:.1f} dB of gain reduction on peaks")

    print(f"voice over speech {v_speech:.1f} LUFS; ducked music over speech "
          f"{lufs(mu_d, smask):.1f} LUFS (target margin {DUCK_DB} dB)")
    print("section   voice-music margin under speech   music in gaps vs voice")
    for s in tl["sections"]:
        sec = np.zeros(n, dtype=np.int64)
        sec[int(s["start"] * SR):int(s["end"] * SR)] = 1
        m = smask & sec
        gaps = (1 - smask) & sec
        gap_l = lufs(mu_d, gaps) if gaps.sum() > 0.4 * SR else float("nan")
        print(f"  {s['id']}       {lufs(vo2, m) - lufs(mu_d, m):5.1f} dB"
              f"                      {gap_l - lufs(vo2, m):6.1f} dB")
    print(f"master: {lufs(mix):.2f} LUFS integrated, true peak {tp:.2f} dBTP")

    (ROOT / "public").mkdir(exist_ok=True)
    pcm = (np.clip(mix.T, -1, 1) * 32767).round().astype(np.int16)
    with wave.open(str(ROOT / "public" / "mix.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    # Stems at master gain, for checks.
    for name, x in (("vo_master.wav", vo2), ("music_master.wav", mu_d)):
        y = (np.clip((x * 10 ** (gain / 20)).T, -1, 1) * 32767).round().astype(np.int16)
        with wave.open(str(ROOT / "build" / name), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(y.tobytes())


if __name__ == "__main__":
    main()
