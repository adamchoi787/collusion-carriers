"""Orchestral score: a re-arrangement of Offenbach's Galop infernal ("can-can", 1858, public
domain), cut to the video's timeline so that every beat drop lands on its on-screen cue.

    python video/audio/score.py        # writes video/build/score.mid and video/public/music.wav

Reads video/src/timeline.json. The plan, section by section:
  1 hook      C minor, celesta and pizzicato theme over tremolo strings; timpani roll -> title hit
              in C major with the opening fanfare.
  2 setup     light can-can (clarinet, flute, pizzicato); a brass slam as the chat closes; then
              a ticking measurement texture with a "bit" motif and one note per action channel.
  3 result    a long build, a beat of silence, then the DROP on "zero": full orchestra, faster.
              The profit counter gets a sinking brass line, then a cadence.
  4 control   suspense; a tutti stab on "No."; the second drop on "immediately" (brass lead).
  5 takeaway  the theme slowed and broadened in F major (horn, slow strings, harp).
  6 warnings  C minor pizzicato and bassoon; three clicks for the button presses; a dissonant
              stab on "never happened".
  7 end       reflective strings, an accelerating build, the finale in D major on the end card.
"""
import json
import random
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

VIDEO = Path(__file__).resolve().parents[1]
TL = json.loads((VIDEO / "src/timeline.json").read_text())
CUE = TL["cues"]
SEC = TL["sections"]
SF = Path.home() / ".local/share/soundfonts/MuseScore_General.sf3"
BIN = Path.home() / ".local/share/av-env/bin"
rng = random.Random(7)

# Stereo seating (MIDI pan, 64 = centre), roughly as an orchestra sits on stage.
PAN = {"vln": 38, "fl": 56, "cl": 70, "tpt": 76, "hn": 48, "tbn": 86, "tba": 92, "pz": 50,
       "cb": 94, "perc": 64, "timp": 66, "glk": 80, "hp": 30, "xy": 44, "pad": 64, "cel": 60}
# channel -> (GM program, reverb send)
CH = {
    "vln": (0, 48, 70),    # Strings Fast
    "fl": (1, 73, 60),     # Flute (piccolo for the finale)
    "cl": (2, 71, 60),     # Clarinet (bassoon in Section 6)
    "tpt": (3, 56, 50),    # Trumpet
    "hn": (4, 60, 70),     # French Horns
    "tbn": (5, 57, 50),    # Trombone
    "tba": (6, 58, 45),    # Tuba
    "pz": (7, 45, 60),     # Strings Pizzicato
    "cb": (8, 43, 55),     # Contrabass
    "perc": (9, 48, 45),   # Orchestra Kit (bank 128)
    "timp": (10, 47, 60),  # Timpani
    "glk": (11, 9, 75),    # Glockenspiel
    "hp": (12, 46, 75),    # Harp
    "xy": (13, 13, 55),    # Xylophone
    "pad": (14, 44, 80),   # Strings Tremolo, then Strings Slow
    "cel": (15, 8, 80),    # Celesta, then Choir Aahs
}
BD, SD, CAST, TAMB, CYM, CYM2, TRI, WB_HI, WB_LO = 36, 38, 39, 54, 57, 59, 81, 76, 77

# Galop infernal main theme, as (semitones above the tonic or None for a rest, sixteenths).
A_MAJ = [
    (0, 4), (2, 1), (5, 1), (4, 1), (2, 1),
    (7, 4), (7, 4),
    (7, 4), (9, 1), (4, 1), (5, 1), (2, 1),
    (2, 4), (2, 4),
    (2, 4), (5, 1), (4, 1), (2, 1), (0, 1),
    (12, 1), (11, 1), (9, 1), (7, 1), (5, 1), (4, 1), (2, 1), (0, 1),
    (2, 1), (7, 1), (2, 1), (4, 1), (0, 4),
    (None, 5), (-5, 1), (-3, 1), (-1, 1),
]
A_HARM = ["I", "I", "I", "I", "V7", "V7", "V7", "V7", "V7", "V7", "I", "I", "V7", "I", "I", "V7"]
MINOR = {4: 3, 9: 8, 16: 15, 21: 20, -3: -4}
A_MIN = [(MINOR.get(p, p) if p is not None else None, d) for p, d in A_MAJ]
A_MIN_HARM = ["i" if h == "I" else h for h in A_HARM]
# Second strain (our own, in the galop's idiom).
B_MAJ = [
    (9, 4), (9, 4),
    (9, 4), (10, 1), (9, 1), (7, 1), (5, 1),
    (7, 4), (7, 4),
    (7, 4), (9, 1), (7, 1), (5, 1), (4, 1),
    (5, 4), (5, 4),
    (5, 4), (7, 1), (5, 1), (4, 1), (2, 1),
    (4, 4), (0, 4),
    (7, 4), (None, 4),
]
B_HARM = ["IV", "IV", "IV", "IV", "I", "I", "I", "I", "ii", "ii", "V7", "V7", "I", "I", "V7", "V7"]
CHORD = {"I": [0, 4, 7], "i": [0, 3, 7], "V7": [7, 11, 14, 17], "IV": [5, 9, 12], "ii": [2, 5, 9],
         "vi": [9, 12, 16], "iv": [5, 8, 12], "Isus": [0, 5, 7], "dim": [11, 14, 17, 20],
         "bVI": [8, 12, 15]}
BASS = {"I": 0, "i": 0, "V7": -5, "IV": 5, "ii": 2, "vi": -3, "iv": 5, "Isus": 0, "dim": -1,
        "bVI": -4}


def bars(theme, n):
    """The first n bars (8 sixteenths each) of a theme."""
    out, total = [], 0
    for p, d in theme:
        if total >= n * 8:
            break
        out.append((p, d))
        total += d
    return out


class Score:
    def __init__(self):
        self.ev = defaultdict(list)  # channel -> [(time, order, bytes)]
        self.beats = []  # [time, strength 0-1]: galop beats, for on-screen pulses
        self.hits = []  # [time, strength 0-1]: accent hits, for flashes and camera shake
        for name, (ch, prog, rev) in CH.items():
            self.program(name, 0.0, prog)
            self.cc(name, 0.0, 91, rev)
            self.cc(name, 0.0, 93, 0)
            self.cc(name, 0.0, 7, 100)
            self.cc(name, 0.0, 11, 110)
            self.cc(name, 0.0, 10, PAN[name])

    def _add(self, name, t, order, data):
        self.ev[CH[name][0]].append((max(0.0, t), order, bytes(data)))

    def program(self, name, t, prog):
        ch = CH[name][0]
        self._add(name, t, 0, [0xC0 | ch, prog])

    def cc(self, name, t, ctrl, val):
        self._add(name, t, 1, [0xB0 | CH[name][0], ctrl, int(max(0, min(127, val)))])

    def ramp(self, name, t0, t1, v0, v1, ctrl=11, steps=24):
        for i in range(steps + 1):
            self.cc(name, t0 + (t1 - t0) * i / steps, ctrl, v0 + (v1 - v0) * i / steps)

    def note(self, name, t, dur, pitch, vel, jitter=True):
        if jitter:
            t += rng.uniform(-0.004, 0.004)
            vel += rng.randint(-4, 4)
        ch = CH[name][0]
        vel = int(max(1, min(127, vel)))
        self._add(name, t, 3, [0x90 | ch, pitch, vel])
        self._add(name, t + max(0.02, dur), 2, [0x80 | ch, pitch, 0])

    def chord(self, name, t, dur, pitches, vel, **kw):
        for p in pitches:
            self.note(name, t, dur, p, vel, **kw)

    def hit(self, t, vel=118):
        """Drum hit to underline a cue (no jitter, so it is frame-exact)."""
        self.hits.append([round(t, 3), round(vel / 127, 2)])
        self.note("perc", t, 0.5, BD, vel, jitter=False)
        self.note("perc", t, 1.6, CYM, vel - 6, jitter=False)

    def write(self, path: Path):
        def vlq(n):
            out = [n & 0x7F]
            n >>= 7
            while n:
                out.insert(0, (n & 0x7F) | 0x80)
                n >>= 7
            return bytes(out)

        tracks = [b"\x00\xff\x51\x03\x07\xa1\x20" + b"\x00\xff\x2f\x00"]  # 120 bpm, 960 ppq
        for ch in sorted(self.ev):
            data, last = b"", 0
            for t, _, msg in sorted(self.ev[ch], key=lambda e: (e[0], e[1])):
                tick = round(t * 1920)
                data += vlq(tick - last) + msg
                last = tick
            tracks.append(data + b"\x00\xff\x2f\x00")
        body = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), 960)
        for tr in tracks:
            body += b"MTrk" + struct.pack(">I", len(tr)) + tr
        path.write_bytes(body)


def voicing(pcs, root, lo, hi):
    out = []
    for pc in pcs:
        p = root + pc
        while p < lo:
            p += 12
        while p > hi:
            p -= 12
        out.append(p)
    return sorted(set(out))


def melody(s, t0, bpm, theme, root, parts, legato=0.85):
    """parts: [(instrument, octave shift, velocity)]. Returns the end time."""
    six = 60 / bpm / 4
    t = t0
    for p, d in theme:
        if p is not None:
            for name, octave, vel in parts:
                s.note(name, t, d * six * legato, root + p + 12 * octave, vel + (6 if d >= 4 else 0))
        t += d * six
    return t


def galop(s, t0, bpm, harm, root, vel=80, bass=("tba", "cb"), chords=("hn", "pz"), drums=True,
          cymbal_every=4, tamb=False, cast=False, timp=False):
    """Oom-pah accompaniment: bass on the beat, chord on the off-beat, one harmony per beat."""
    beat = 60 / bpm
    for i, h in enumerate(harm):
        t = t0 + i * beat
        s.beats.append([round(t, 3), round(vel / 127 * (1.0 if i % 2 == 0 else 0.7), 2)])
        b = root - 24 + BASS[h] + (7 if i % 2 and h in ("I", "i", "IV") else 0)
        for name in bass:
            s.note(name, t, beat * 0.45, b, vel)
        for name in chords:
            s.chord(name, t + beat / 2, beat * 0.35, voicing(CHORD[h], root, 55, 68), vel - 12)
        if timp and i % 2 == 0:
            s.note("timp", t, 0.3, root - 24 + (BASS[h] % 12), vel - 10)
        if drums:
            s.note("perc", t, 0.2, BD if i % 2 == 0 else SD, vel - (5 if i % 2 == 0 else 20))
            if tamb:
                s.note("perc", t + beat / 2, 0.1, TAMB, vel - 25)
            if cast and i % 2 == 1:
                s.note("perc", t + beat * 0.75, 0.1, CAST, vel - 30)
            if cymbal_every and i % (2 * cymbal_every) == 0:
                s.note("perc", t, 1.2, CYM, vel - 10)
    return t0 + len(harm) * beat


def sustain(s, t0, bpm, harm, root, vel=78):
    """A choir pad holding the harmony, one chord per bar, under a fast theme. It uses its own
    channel so the short off-beat chords elsewhere never cut its notes off."""
    bar = 120 / bpm
    for i in range(0, len(harm), 2):
        pitches = voicing(CHORD[harm[i]], root - 12, 52, 67)
        s.chord("cel", t0 + i / 2 * bar, bar * 0.95, pitches, vel)


def roll(s, name, pitch, t0, t1, v0, v1, rate=24):
    n = max(1, int((t1 - t0) * rate))
    for i in range(n):
        s.note(name, t0 + i / rate, 1 / rate, pitch, v0 + (v1 - v0) * i / n, jitter=False)


def scale_run(s, name, t0, t1, pitches, vel):
    for i, p in enumerate(pitches):
        s.note(name, t0 + (t1 - t0) * i / len(pitches), (t1 - t0) / len(pitches) * 0.9, p, vel)


def compose() -> Score:
    s = Score()
    C, F, D = 72, 65, 74  # melody tonic pitches (C5, F4, D5)

    # ---- 1. Hook: C minor mystery, then the title hit ----------------------------------
    title = CUE["title"]
    s.ramp("pad", 0.0, title - 0.25, 25, 95)
    s.chord("pad", 0.0, title - 0.22, [48, 55, 60, 63], 70)
    s.note("cb", 0.0, title - 0.22, 36, 70)
    bpm1 = 84
    t = melody(s, 0.7, bpm1, bars(A_MIN, 4), C, [("cel", 0, 70)], legato=0.9)
    melody(s, t, bpm1, A_MIN[len(bars(A_MIN, 4)):len(bars(A_MIN, 7))], C - 12,
           [("pz", 0, 72), ("cl", 0, 55)])
    galop(s, 0.7, bpm1, A_MIN_HARM[:12], C, vel=50, bass=("pz",), chords=(), drums=False)
    scale_run(s, "hp", CUE["balloon"], CUE["balloon"] + 0.6, [48, 51, 55, 60, 63, 67, 72, 75, 79], 70)
    s.note("timp", CUE["squeeze"], 1.0, 43, 105, jitter=False)
    s.chord("hn", CUE["squeeze"], 2.4, [55, 60, 63], 60)
    s.ramp("hn", CUE["squeeze"], CUE["squeeze"] + 2.4, 50, 110)
    roll(s, "timp", 43, title - 2.0, title - 0.22, 40, 112)
    roll(s, "perc", SD, title - 1.2, title - 0.22, 30, 100, rate=28)
    scale_run(s, "vln", title - 0.9, title - 0.22, [67, 69, 71, 72, 74, 76, 77, 79], 85)
    # Title: C major arrives with the opening fanfare.
    s.program("pad", title, 49)
    s.hit(title, 124)
    s.note("timp", title, 0.8, 48, 125, jitter=False)
    s.chord("tbn", title, 0.35, [48, 55, 60, 64], 112, jitter=False)
    s.note("tba", title, 0.5, 36, 115, jitter=False)
    s.chord("pad", title, 1.6, [60, 64, 67, 72], 90)
    bpm = 150
    end = melody(s, title, bpm, bars(A_MAJ, 2), C, [("tpt", 0, 112), ("vln", 0, 105), ("fl", 1, 95)])
    galop(s, title, bpm, A_HARM[:4], C, vel=105, tamb=True)
    s.chord("tbn", end, 0.25, [48, 55, 64], 105)
    s.chord("hn", end, 0.25, [60, 64, 67], 105)
    s.note("tba", end, 0.25, 36, 110)
    s.hit(end, 112)

    # ---- 2. Setup: playful cartel, the chat closes, the measurement texture -----------
    t0, closed = SEC[1], CUE["closed"]
    n = 6
    bpm2 = n * 2 * 60 / (closed - t0)
    melody(s, t0, bpm2, bars(A_MAJ, n), C, [("cl", 0, 78), ("fl", 1, 62)], legato=0.7)
    galop(s, t0, bpm2, A_HARM[: 2 * n], C, vel=62, bass=("pz",), chords=("pz",), cymbal_every=0,
          tamb=False, cast=True)
    for i in range(2 * n):
        s.note("perc", t0 + (i + 0.5) * 60 / bpm2, 0.2, TRI, 50)
    # The slam.
    s.hit(closed, 125)
    s.note("timp", closed, 1.0, 36 + 12, 127, jitter=False)
    s.chord("tbn", closed, 0.6, [36, 43, 48, 51], 122, jitter=False)
    s.chord("tba", closed, 0.6, [24, 36], 122, jitter=False)
    s.chord("hn", closed, 0.6, [55, 60, 63], 118, jitter=False)
    scale_run(s, "vln", closed + 0.05, closed + 0.75, list(range(84, 60, -2)), 70)
    # Measuring: a clock of xylophone ticks over a low pedal.
    tick0, tick1 = closed + 0.9, SEC[2] + 0.0
    s.chord("pad", tick0, tick1 - tick0, [48, 55, 60], 55)
    s.ramp("pad", tick0, tick1, 40, 80)
    k = 0
    t = tick0
    while t < tick1 - 0.05:
        s.note("xy", t, 0.08, 84 if k % 4 == 0 else 79, 52 if k % 4 == 0 else 38)
        if k % 2 == 0:
            s.note("pz", t, 0.2, 36 if k % 4 == 0 else 43, 62)
        t += 0.25
        k += 1
    s.chord("glk", CUE["bits"], 0.3, [96], 85, jitter=False)
    s.chord("glk", CUE["bits"] + 0.18, 0.4, [103], 85, jitter=False)
    for i, p in enumerate([72, 76, 79, 84]):  # one note per action channel label
        s.note("glk", CUE["actions"] + 0.25 * i, 0.5, p + 12, 80, jitter=False)
    for i, p in enumerate([79, 84, 88]):  # one ping per fact chip
        s.note("hp", CUE["facts2"] + 1.4 * i, 1.0, p, 85, jitter=False)
        s.note("glk", CUE["facts2"] + 1.4 * i, 0.6, p + 12, 60, jitter=False)

    # ---- 3. Result: build, the line over held tension, DROP after "zero bits." ------------
    drop, line = CUE["drop3"], TL["clips"][4]["start"]
    b0 = SEC[2] - 1.5
    s.program("pad", b0, 44)
    for i, root in enumerate([55, 56, 57, 58]):  # rising tremolo steps up to the line
        a = b0 + i * (line - b0) / 4
        s.chord("pad", a, (line - b0) / 4, [root, root + 7, root + 12], 60 + i * 10)
    s.ramp("pad", b0, line, 50, 115)
    roll(s, "timp", 43, b0, line - 0.05, 30, 105)
    s.hit(line - 0.05, 100)
    # Under "Across four models: zero bits." only a high suspended tremolo and a heartbeat.
    s.chord("pad", line, drop - 0.3 - line, [79, 86, 91], 60)
    s.ramp("pad", line, drop - 0.3, 70, 95)
    t = line + 0.4
    while t < drop - 0.5:
        s.note("timp", t, 0.3, 36, 70, jitter=False)
        s.note("timp", t + 0.22, 0.3, 36, 55, jitter=False)
        t += 0.85
    roll(s, "perc", SD, drop - 0.9, drop - 0.28, 40, 112, rate=32)
    s.program("pad", drop, 49)
    # (drop - 0.28 .. drop is silent: the beat before the drop)
    counter = CUE["counter"]
    n3 = round((counter - drop) / (120 / 168))
    bpm3 = n3 * 2 * 60 / (counter - drop)
    s.hit(drop, 127)
    s.note("timp", drop, 0.8, 48, 127, jitter=False)
    s.note("perc", drop, 2.0, CYM2, 120, jitter=False)
    s.chord("tbn", drop, 0.4, [48, 55, 60, 64], 124, jitter=False)
    t = melody(s, drop, bpm3, A_MAJ, C, [("vln", 0, 112), ("tpt", 0, 108), ("fl", 1, 100),
                                          ("glk", 1, 58)])
    s.program("cel", drop, 52)
    sustain(s, drop, bpm3, A_HARM[:16], C)
    melody(s, t, bpm3, bars(B_MAJ, n3 - 8), C, [("vln", 0, 100), ("cl", 0, 90), ("fl", 1, 85)])
    galop(s, drop, bpm3, (A_HARM + B_HARM)[: 2 * n3], C, vel=108, tamb=True, cast=True, timp=True)
    s.chord("pad", drop, counter - drop, [60, 64, 67], 70)
    # The profit counter sinks: a falling brass line in the gap.
    fall = [67, 66, 65, 64, 63, 62, 61, 60, 59, 58, 57, 55]
    scale_run(s, "tbn", counter, counter + 1.8, fall, 98)
    scale_run(s, "cl", counter, counter + 1.8, [p + 12 for p in fall], 80)
    roll(s, "timp", 43, counter + 0.6, counter + 1.9, 40, 90)
    for i, h in enumerate(["V7", "V7", "I"]):
        t = counter + 2.15 + i * 0.35
        s.chord("hn", t, 0.25, voicing(CHORD[h], C, 55, 70), 110)
        s.chord("tbn", t, 0.25, voicing(CHORD[h], C - 12, 43, 58), 110)
        s.note("tba", t, 0.25, C - 36 + BASS[h] + 12, 112)
        s.note("perc", t, 0.4, BD, 110)
    s.note("perc", counter + 2.85, 1.6, CYM, 110)

    # ---- 4. Control: suspense, "No.", the second drop after "immediately." -----------------
    t0, no, imm = SEC[3], CUE["no"], CUE["drop4"]
    s.program("pad", t0, 44)
    s.chord("pad", t0, no - 0.2 - t0, [59, 62, 65, 68], 55)
    s.ramp("pad", t0, no - 0.2, 40, 85)
    t = t0 + 0.3
    while t < no - 0.25:
        s.note("perc", t, 0.1, WB_HI, 55)
        t += 0.5
    s.hit(no, 125)
    s.chord("tbn", no, 0.3, [48, 55, 60, 64], 120, jitter=False)
    s.chord("hn", no, 0.3, [60, 64, 67], 118, jitter=False)
    s.chord("vln", no, 0.3, [72, 76, 79, 84], 118, jitter=False)
    s.note("timp", no, 0.6, 48, 125, jitter=False)
    s.program("pad", no + 0.4, 49)
    # A light pizzicato ostinato while the code is shown, rising to the drop.
    t = no + 0.6
    k = 0
    while t < imm - 0.3:
        s.note("pz", t, 0.15, [60, 64, 67, 72][k % 4], 60 + k)
        t += 0.2
        k += 1
    roll(s, "perc", SD, imm - 1.0, imm - 0.25, 30, 110, rate=32)
    s.chord("glk", CUE["code"], 0.6, [96, 100, 103], 80, jitter=False)
    end4 = SEC[4] - 0.3
    n4 = round((end4 - imm) / (120 / 170))
    bpm4 = n4 * 2 * 60 / (end4 - imm)
    s.hit(imm, 127)
    s.note("timp", imm, 0.8, 48, 127, jitter=False)
    s.chord("tbn", imm, 0.4, [48, 55, 60, 64], 124, jitter=False)
    t = melody(s, imm, bpm4, bars(A_MAJ, n4 - 1), C,
               [("tpt", 0, 115), ("hn", -1, 100), ("vln", 1, 100), ("xy", 1, 70), ("glk", 1, 55)])
    galop(s, imm, bpm4, A_HARM[: 2 * (n4 - 1)], C, vel=106, bass=("tba", "cb", "tbn"), tamb=True,
          timp=True)
    eighth = 30 / bpm4
    for i, h in enumerate(["V7", "V7", "V7"]):
        s.chord("hn", t + i * eighth, eighth * 0.6, voicing(CHORD[h], C, 55, 70), 115, jitter=False)
        s.chord("tbn", t + i * eighth, eighth * 0.6, voicing(CHORD[h], C - 12, 43, 58), 112,
                jitter=False)
        s.note("perc", t + i * eighth, 0.2, SD, 105, jitter=False)
    s.chord("pad", end4, 0.5, [60, 64, 67, 72], 90)
    s.chord("hn", end4, 0.4, [60, 64, 67], 110, jitter=False)
    s.note("tba", end4, 0.4, 36, 112, jitter=False)
    s.hit(end4, 112)

    # ---- 5. Takeaway: broad theme in F major ----------------------------------------------
    t0 = SEC[4]
    s.program("vln", t0, 49)
    s.program("cel", t0, 8)
    broad = [(p, d * 2) for p, d in bars(A_MAJ, 4)]
    bpm5 = 92
    t = melody(s, t0 + 0.3, bpm5, broad, F, [("hn", 0, 88), ("vln", 1, 70)], legato=0.98)
    harm5 = [h for h in A_HARM[:8] for _ in range(2)]
    beat = 60 / bpm5
    for i, h in enumerate(harm5):
        tt = t0 + 0.3 + i * beat
        if i % 2 == 0:
            s.chord("pad", tt, beat * 2, voicing(CHORD[h], F, 53, 72), 68)
            s.note("cb", tt, beat * 2, F - 24 + BASS[h] - (12 if BASS[h] > 4 else 0), 70)
        for j, p in enumerate(voicing(CHORD[h], F + 12, 72, 90)[:3]):
            s.note("hp", tt + j * beat / 3, beat / 3, p, 60)
    s.note("perc", CUE["rule"] - 1.2, 1.3, CYM2, 40)
    s.ramp("perc", CUE["rule"] - 1.2, CUE["rule"], 40, 110)
    s.chord("cel", CUE["rule"], 1.5, [84, 88, 91, 96], 75, jitter=False)
    # An unresolved suspension under the open question.
    s.chord("pad", CUE["freetext"], SEC[5] - CUE["freetext"], voicing(CHORD["Isus"], F, 53, 72), 70)
    s.note("cb", CUE["freetext"], SEC[5] - CUE["freetext"], F - 24, 65)
    s.chord("hp", CUE["untested"], 1.5, [77, 82, 84], 65)
    roll(s, "timp", 41, SEC[5] - 1.6, SEC[5] - 0.05, 25, 80)

    # ---- 6. Warnings: C minor sneak ----------------------------------------------------------
    t0 = SEC[5]
    s.program("vln", t0, 48)
    s.program("cl", t0, 70)  # bassoon
    s.note("perc", t0, 0.6, BD, 112, jitter=False)
    s.chord("hn", t0, 1.2, [48, 55, 60, 63], 95)
    s.chord("tbn", t0 + 0.35, 0.9, [43, 50, 55, 59], 90)
    w = CUE["warn1"]
    bpm6 = 132
    t = melody(s, w, bpm6, A_MIN, C - 12, [("pz", 0, 82), ("cl", -1, 70)], legato=0.4)
    t = melody(s, t, bpm6, bars(A_MIN, 4), C - 12, [("pz", 0, 75), ("cl", -1, 62)], legato=0.4)
    galop(s, w, bpm6, A_MIN_HARM + A_MIN_HARM[:8], C, vel=58, bass=("cb",), chords=(), drums=False)
    beat = 60 / bpm6
    tt = w
    while tt < SEC[6] - 0.3:
        s.note("perc", tt, 0.1, WB_LO, 45)
        tt += beat
    for i in range(3):  # the button presses
        s.note("xy", CUE["pressing"] + 0.36 * i, 0.1, 96, 100, jitter=False)
        s.note("perc", CUE["pressing"] + 0.36 * i, 0.1, WB_HI, 95, jitter=False)
    s.chord("pad", CUE["claimed"], CUE["never"] - CUE["claimed"], [60, 63, 67], 55)
    s.hit(CUE["never"], 122)
    s.chord("tbn", CUE["never"], 0.9, [42, 48, 54, 55], 120, jitter=False)  # dissonant cluster
    s.chord("hn", CUE["never"], 0.9, [54, 60, 61], 110, jitter=False)
    s.note("timp", CUE["never"], 0.8, 42, 120, jitter=False)
    s.chord("cb", CUE["trust"], 0.8, [24, 36], 120, jitter=False)
    s.note("perc", CUE["trust"], 0.5, BD, 115, jitter=False)
    s.chord("vln", CUE["trust"], 0.5, [48, 55, 60, 63], 105, jitter=False)

    # ---- 7. Limits, build, finale in D major ---------------------------------------------------
    t0, nxt, card, fin = SEC[6], CUE["next"], CUE["endcard"], CUE["final"]
    prog7 = [("I", 0), ("vi", 0), ("IV", 0), ("V7", 0)]
    span = (nxt - t0) / 4
    for i, (h, _) in enumerate(prog7):
        tt = t0 + i * span
        s.chord("pad", tt, span, voicing(CHORD[h], C, 55, 76), 70)
        s.note("cb", tt, span, 36 + BASS[h] if BASS[h] >= 0 else 48 + BASS[h], 70)
        for j, p in enumerate(voicing(CHORD[h], C + 12, 72, 91) * 2):
            s.note("hp", tt + j * span / 6, span / 6, p, 55)
    for c in ("limit1", "limit2"):
        s.note("glk", CUE[c], 0.6, 96, 80, jitter=False)
    # Accelerating build into the end card.
    t, period, k = nxt, 0.42, 0
    while t < card - 0.3:
        s.note("vln", t, period * 0.8, [62, 66, 69, 74][k % 4] + 12 * (k // 8), 70 + 2 * k)
        s.note("pz", t, period * 0.5, [38, 45][k % 2], 80)
        t += period
        period = max(0.12, period * 0.93)
        k += 1
    roll(s, "timp", 45, nxt + 1.0, card - 0.25, 30, 118)
    roll(s, "perc", SD, card - 1.6, card - 0.25, 30, 118, rate=32)
    s.program("fl", card, 72)   # piccolo
    s.program("cel", card, 52)  # choir
    bpm7 = 176
    s.hit(card, 127)
    s.note("timp", card, 0.8, 50, 127, jitter=False)
    t = melody(s, card, bpm7, bars(A_MAJ, 4), D,
               [("tpt", 0, 118), ("vln", 0, 112), ("fl", 1, 100), ("hn", -1, 100), ("xy", 1, 70)])
    galop(s, card, bpm7, A_HARM[:8], D, vel=112, bass=("tba", "cb", "tbn"), tamb=True, cast=True,
          timp=True, cymbal_every=2)
    sustain(s, card, bpm7, A_HARM[:8], D, vel=92)
    eighth = 30 / bpm7
    for i in range(3):  # "da da da" ...
        tt = t + i * eighth
        s.chord("hn", tt, eighth * 0.6, voicing(CHORD["V7"], D, 55, 72), 120, jitter=False)
        s.chord("tpt", tt, eighth * 0.6, voicing(CHORD["V7"], D + 12, 67, 84), 115, jitter=False)
        s.chord("tbn", tt, eighth * 0.6, voicing(CHORD["V7"], D - 12, 43, 58), 118, jitter=False)
        s.note("tba", tt, eighth * 0.6, D - 36 + 7 + 12, 120, jitter=False)
        s.note("perc", tt, 0.2, SD, 115, jitter=False)
    roll(s, "perc", SD, t + 3 * eighth, fin - 0.02, 70, 120, rate=32)
    # ... DAAA.
    s.hit(fin, 127)
    s.note("perc", fin, 3.0, CYM2, 124, jitter=False)
    s.note("timp", fin, 0.5, 50, 127, jitter=False)
    roll(s, "timp", 50, fin + 0.3, TL["duration"] - 0.6, 100, 30)
    hold = TL["duration"] - fin - 0.4
    for name, pitches in [("tpt", [74, 78, 81, 86]), ("hn", [62, 66, 69, 74]),
                          ("tbn", [50, 57, 62]), ("tba", [38]), ("vln", [74, 78, 81, 86, 90]),
                          ("fl", [98]), ("cel", [62, 66, 69, 74]), ("pad", [50, 62, 66, 69]),
                          ("cb", [26, 38])]:
        s.chord(name, fin, hold, pitches, 120, jitter=False)
        s.ramp(name, fin + 0.4, fin + hold, 120, 20)
    return s


def main() -> None:
    build = VIDEO / "build"
    build.mkdir(exist_ok=True)
    mid = build / "score.mid"
    score = compose()
    score.write(mid)
    (VIDEO / "src/beats.json").write_text(json.dumps(
        {"beats": sorted(score.beats), "hits": sorted(score.hits)}))
    wav = VIDEO / "public/music.wav"
    subprocess.run([BIN / "fluidsynth", "-ni", "-q", "-F", str(wav), "-r", "48000", "-g", "0.5",
                    "-o", "synth.reverb.room-size=0.75", "-o", "synth.reverb.damp=0.35",
                    "-o", "synth.reverb.width=0.9", "-o", "synth.reverb.level=0.75",
                    "-o", "synth.chorus.active=0", "-o", "synth.polyphony=512",
                    str(SF), str(mid)], check=True)
    print("wrote", mid, wav)


if __name__ == "__main__":
    main()
