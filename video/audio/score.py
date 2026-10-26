"""Original underscore: felt piano, warm strings, soft pad and a light pizzicato pulse.

120 BPM, so a beat is 0.5 s and every section boundary (0, 12, 35, 55, 75, 90, 105, 120 s) lands
on a beat. Writes build/score.mid and renders build/music.wav (48 kHz stereo) with FluidSynth and
the MuseScore General soundfont.
"""

import pathlib
import random
import struct
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
AV = pathlib.Path.home() / ".local/share/av-env/bin"
SF = pathlib.Path.home() / ".local/share/soundfonts/MuseScore_General.sf3"
PPQ = 480
BEATS = 240  # 120 s

# Chord voicings: (bass root, pad notes). Key of D major.
CH = {
    "D": (38, [62, 66, 69]), "A": (45, [61, 64, 69]), "Bm": (47, [62, 66, 71]),
    "G": (43, [62, 67, 71]), "Em": (40, [64, 67, 71]), "F#m": (42, [61, 66, 69]),
    "Gmaj7": (43, [62, 66, 71]), "Asus": (45, [62, 64, 69]),
}

# (start beat, chord, beats). Sections: s1 0-24, s2 24-70, s3 70-110, s4 110-150,
# s5 150-180, s6 180-210, s7 210-240.
PLAN = [
    (0, "Bm", 8), (8, "Gmaj7", 8), (16, "D", 4), (20, "Asus", 4),
    (24, "D", 8), (32, "A", 8), (40, "Bm", 8), (48, "G", 8), (56, "Em", 8), (64, "Asus", 6),
    (70, "G", 8), (78, "D", 8), (86, "A", 8), (94, "Bm", 8), (102, "G", 4), (106, "A", 4),
    (110, "Em", 8), (118, "G", 8), (126, "D", 8), (134, "A", 8), (142, "Bm", 4), (146, "Asus", 4),
    (150, "G", 8), (158, "A", 8), (166, "D", 8), (174, "Asus", 6),
    (180, "Bm", 8), (188, "Gmaj7", 8), (196, "Em", 8), (204, "F#m", 6),
    (210, "G", 8), (218, "Asus", 8), (226, "D", 14),
]

# Per-section feel: piano density (notes per beat), piano velocity, pulse on/off, string level.
FEEL = [
    (0, 1, 38, False, 70), (24, 1, 42, False, 80), (32, 2, 44, True, 84), (70, 2, 48, True, 96),
    (110, 2, 46, True, 92), (150, 2, 44, True, 90), (180, 1, 38, False, 72), (210, 1, 42, True, 84),
    (226, 1, 40, False, 80),
]


def feel(beat):
    return [f for f in FEEL if f[0] <= beat][-1]


def vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def track(events):
    events.sort(key=lambda e: (e[0], e[1][0] & 0xF0 == 0x90))  # note-offs before note-ons
    data, last = b"", 0
    for t, msg in events:
        data += vlq(t - last) + msg
        last = t
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def tick(beat):
    return int(round(beat * PPQ))


def note(ev, ch, beat, dur, pitch, vel):
    ev.append((tick(beat), bytes([0x90 | ch, pitch, max(1, min(127, vel))])))
    ev.append((tick(beat + dur), bytes([0x80 | ch, pitch, 0])))


def cc(ev, ch, beat, num, val):
    ev.append((tick(beat), bytes([0xB0 | ch, num, max(0, min(127, int(val)))])))


def ramp(ev, ch, b0, b1, v0, v1, num=11, steps_per_beat=4):
    n = max(1, int((b1 - b0) * steps_per_beat))
    for i in range(n + 1):
        cc(ev, ch, b0 + (b1 - b0) * i / n, num, v0 + (v1 - v0) * i / n)


def main():
    rnd = random.Random(7)
    tempo = track([(0, b"\xff\x51\x03" + (500000).to_bytes(3, "big")), (0, b"\xff\x58\x04\x04\x02\x18\x08")])
    piano, strings, pad, pulse, cello = [], [], [], [], []
    for ev, ch, prog, vol in ((piano, 0, 0, 100), (strings, 1, 49, 92), (pad, 2, 89, 70),
                              (pulse, 3, 45, 84), (cello, 4, 42, 80)):
        ev.append((0, bytes([0xC0 | ch, prog])))
        cc(ev, ch, 0, 7, vol)
        cc(ev, ch, 0, 91, 70)  # reverb send
        cc(ev, ch, 0, 10, {0: 64, 1: 52, 2: 76, 3: 70, 4: 58}[ch])

    for start, name, beats in PLAN:
        bass, triad = CH[name]
        _, density, pvel, has_pulse, slvl = feel(start)
        last = start + beats >= BEATS
        # Strings and pad: sustained voicing, gentle swell within each chord.
        for p in triad:
            note(strings, 1, start, beats - 0.05, p - 12, 52)
            note(pad, 2, start, beats - 0.05, p, 44)
        note(cello, 4, start, beats - 0.05, bass, 50)
        ramp(strings, 1, start, start + beats / 2, slvl - 14, slvl)
        ramp(strings, 1, start + beats / 2, start + beats, slvl, slvl - 10 if not last else 0)
        # Piano: rising-falling arpeggio over the chord.
        arp = [bass + 12, triad[0], triad[1], triad[2], triad[0] + 12, triad[2], triad[1], triad[0]]
        step = 1 / density
        n = int(beats * density)
        for i in range(n):
            b = start + i * step
            if last and b >= BEATS - 6:
                break
            v = pvel + (6 if i % 4 == 0 else 0) + rnd.randint(-3, 3)
            note(piano, 0, b, step * 1.8, arp[i % len(arp)], v)
        if has_pulse:
            for i in range(int(beats * 2)):
                b = start + i * 0.5
                p = bass + (12 if i % 4 == 2 else 0)
                note(pulse, 3, b, 0.3, p, 34 + (6 if i % 2 == 0 else 0) + rnd.randint(-2, 2))
    # Opening fade-in and the final resolution: a soft D chord on the piano, then fade out by 119.6 s.
    for ch, ev in ((1, strings), (2, pad), (4, cello)):
        ramp(ev, ch, 0, 4, 0, 70)
    for p, dv in ((50, 0), (57, 3), (62, 6), (66, 8), (69, 10)):
        note(piano, 0, BEATS - 6 + dv * 0.04, 5.5, p, 40)
    for ch, ev in ((1, strings), (2, pad), (4, cello)):
        ramp(ev, ch, BEATS - 6, BEATS - 0.8, 80, 0)

    tracks = [tempo] + [track(e) for e in (piano, strings, pad, pulse, cello)]
    mid = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ) + b"".join(tracks)
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    (build / "score.mid").write_bytes(mid)
    subprocess.run([str(AV / "fluidsynth"), "-ni", "-q", "-g", "0.6", "-r", "48000",
                    "-o", "synth.reverb.active=1", "-o", "synth.reverb.room-size=0.75",
                    "-o", "synth.reverb.level=0.6", "-o", "synth.chorus.active=0",
                    "-F", str(build / "music_raw.wav"), str(SF), str(build / "score.mid")], check=True)
    # Trim or pad to exactly 120 s.
    subprocess.run([str(AV / "ffmpeg"), "-loglevel", "error", "-y", "-i", str(build / "music_raw.wav"),
                    "-af", "apad=whole_dur=120,atrim=0:120,afade=t=out:st=118.8:d=1.2", "-ar", "48000",
                    "-ac", "2", str(build / "music.wav")], check=True)
    print("wrote build/score.mid and build/music.wav")


if __name__ == "__main__":
    main()
