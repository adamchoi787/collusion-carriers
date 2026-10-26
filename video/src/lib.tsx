import React from 'react';
import {Easing, interpolate} from 'remotion';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadSerif} from '@remotion/google-fonts/Newsreader';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';
import timeline from './timeline.json';

export const {fontFamily: SANS} = loadInter('normal', {weights: ['400', '500', '600', '700'], subsets: ['latin']});
export const {fontFamily: SERIF} = loadSerif('normal', {weights: ['400', '500', '600'], subsets: ['latin']});
export const {fontFamily: MONO} = loadMono('normal', {weights: ['400', '600'], subsets: ['latin']});

export const FPS = 30;
export const TL = timeline;

export const C = {
  bg: '#0A0E17',
  bg2: '#111827',
  panel: '#131A26',
  line: '#2A3446',
  text: '#F1F5F9',
  dim: '#94A3B8',
  faint: '#64748B',
  a: '#38BDF8', // firm A
  b: '#F5A524', // firm B
  chat: '#A78BFA',
  red: '#F43F5E',
  green: '#34D399',
  gold: '#FBBF24',
  luna: '#2B7BD9',
  haiku: '#EC6A36',
  qwen: '#1DB07B',
  gemma: '#EDA100',
};

/** Frame of a named cue (word start from Kokoro's timestamps). */
export const cue = (name: keyof typeof timeline.cues): number => Math.round(timeline.cues[name] * FPS);
export const sec = (s: number) => Math.round(s * FPS);

const ease = Easing.bezier(0.22, 1, 0.36, 1);

/** 0 → 1 over `dur` frames starting at `at`. */
export const inn = (frame: number, at: number, dur = 14) =>
  interpolate(frame, [at, at + dur], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});

/** 1 → 0 over `dur` frames starting at `at`. */
export const out = (frame: number, at: number, dur = 12) => 1 - inn(frame, at, dur);

/** Visible between `a` and `b` with fades. */
export const span = (frame: number, a: number, b: number, fi = 12, fo = 10) =>
  Math.min(inn(frame, a, fi), out(frame, b - fo, fo));

export const lerp = (t: number, a: number, b: number) => a + (b - a) * t;

/** Positioned box; data-t marks it as text for the layout checker. */
export const Box: React.FC<{
  x: number; y: number; w?: number; h?: number; style?: React.CSSProperties; children?: React.ReactNode;
  t?: boolean; id?: string;
}> = ({x, y, w, h, style, children, t, id}) => (
  <div
    data-t={t ? id ?? '1' : undefined}
    style={{position: 'absolute', left: x, top: y, width: w, height: h, ...style}}
  >
    {children}
  </div>
);

export const Chip: React.FC<{
  x: number; y: number; w?: number; color?: string; size?: number; o?: number; children: React.ReactNode; id?: string;
  bg?: string; dy?: number;
}> = ({x, y, w, color = C.dim, size = 26, o = 1, children, id, bg = 'rgba(19,26,38,0.92)', dy = 0}) => (
  <div
    style={{
      position: 'absolute', left: x, top: y + dy * (1 - o), width: w, opacity: o,
      border: `1.5px solid ${color}`, borderRadius: 14, background: bg, padding: '12px 20px',
      boxSizing: 'border-box',
    }}
  >
    <div data-t={id ?? 'chip'} style={{fontFamily: SANS, fontSize: size, color: C.text, lineHeight: 1.3}}>
      {children}
    </div>
  </div>
);

/** A definition card in the explanation rail: term in colour, then plain meaning. */
export const Gloss: React.FC<{x: number; y: number; w: number; o: number; term: string; color?: string; children: React.ReactNode; id?: string}> = ({
  x, y, w, o, term, color = C.gold, children, id,
}) => (
  <div style={{position: 'absolute', left: x, top: y + 10 * (1 - o), width: w, opacity: o}}>
    <div data-t={id ?? 'gloss'} style={{fontFamily: SANS, fontSize: 25, lineHeight: 1.35, color: C.dim}}>
      <span style={{color, fontWeight: 600, letterSpacing: 0.3}}>{term}</span>
      <span style={{color: C.faint}}>{'  ·  '}</span>
      {children}
    </div>
  </div>
);
