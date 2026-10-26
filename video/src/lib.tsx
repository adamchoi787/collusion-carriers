import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadSerif} from '@remotion/google-fonts/InstrumentSerif';
import {loadFont as loadSans} from '@remotion/google-fonts/Inter';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';
import timeline from './timeline.json';
import beatData from './beats.json';

export const SERIF = loadSerif('normal', {weights: ['400'], subsets: ['latin']}).fontFamily;
loadSerif('italic', {weights: ['400'], subsets: ['latin']});
export const SANS = loadSans('normal', {weights: ['400', '500', '600', '700', '800'], subsets: ['latin']})
  .fontFamily;
export const MONO = loadMono('normal', {weights: ['400', '600'], subsets: ['latin']}).fontFamily;

export const C = {
  bg: '#090D19',
  bg2: '#111832',
  ink: '#F3F0E8',
  muted: '#8E95AD',
  faint: '#3A4263',
  gold: '#F2B544',
  cyan: '#4FD8F5',
  red: '#FF5D5D',
  green: '#5BE39B',
  luna: '#2F80E0',
  haiku: '#EC6A35',
  qwen: '#1BB07A',
  gemma: '#EFA200',
};

export const MODELS = [
  {name: 'gpt-6-luna', color: C.luna},
  {name: 'claude-haiku-5-5', color: C.haiku},
  {name: 'Qwen3.8-27B', color: C.qwen},
  {name: 'Gemma-4-26B', color: C.gemma},
];

export const TL = timeline;
export const CUE = timeline.cues as Record<string, number>;
export const SEC = timeline.sections;
export const BEATS = beatData.beats as [number, number][];
export const HITS = beatData.hits as [number, number][];

/** Global time in seconds. Every scene works in absolute timeline seconds. */
export const useT = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return frame / fps;
};

export const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));

/** 0 -> 1 over [t0, t0 + dur] with an ease-out. */
export const ease = (t: number, t0: number, dur = 0.5, fn = Easing.out(Easing.cubic)) =>
  fn(clamp((t - t0) / dur));

/** Damped spring from 0 to 1 starting at t0 (overshoots a little). */
export const springAt = (t: number, t0: number, stiffness = 14, damping = 0.55) => {
  const x = t - t0;
  if (x <= 0) return 0;
  const w = stiffness;
  return 1 - Math.exp(-damping * w * x) * Math.cos(w * Math.sqrt(1 - damping * damping) * x);
};

/** Visibility window with fades: 0 before t0, 1 inside, 0 after t1. */
export const win = (t: number, t0: number, t1: number, fadeIn = 0.35, fadeOut = 0.35) =>
  Math.min(ease(t, t0, fadeIn), 1 - ease(t, t1 - fadeOut, fadeOut, Easing.in(Easing.cubic)));

export const lerp = (a: number, b: number, x: number) => a + (b - a) * x;

/** Strength of the most recent beat/hit, decaying over `decay` seconds. */
export const pulse = (t: number, list: [number, number][], decay = 0.35) => {
  let v = 0;
  for (const [bt, s] of list) {
    if (bt > t) break;
    if (t - bt < decay * 3) v = Math.max(v, s * Math.exp(-(t - bt) / decay));
  }
  return v;
};

/** Camera shake offset from accent hits. */
export const shake = (t: number) => {
  const p = pulse(t, HITS, 0.12);
  return {x: Math.sin(t * 97) * 14 * p, y: Math.cos(t * 83) * 10 * p, r: Math.sin(t * 71) * 0.6 * p};
};

export const Center: React.FC<{style?: React.CSSProperties; children: React.ReactNode}> = ({
  style,
  children,
}) => (
  <div
    style={{
      position: 'absolute',
      inset: 0,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      ...style,
    }}
  >
    {children}
  </div>
);

/** Words that rise in one by one at their spoken times. */
export const Kinetic: React.FC<{
  words: [string, number][];
  t: number;
  size?: number;
  font?: string;
  color?: string;
  accent?: Record<string, string>;
  italic?: string[];
  weight?: number;
  maxWidth?: number;
  align?: 'center' | 'left';
  lineHeight?: number;
}> = ({words, t, size = 80, font = SERIF, color = C.ink, accent = {}, italic = [], weight = 400,
  maxWidth = 1500, align = 'center', lineHeight = 1.12}) => (
  <div
    style={{
      fontFamily: font,
      fontSize: size,
      fontWeight: weight,
      color,
      maxWidth,
      lineHeight,
      textAlign: align,
      letterSpacing: font === SERIF ? '-0.01em' : '-0.02em',
    }}
  >
    {words.map(([w, at], i) => {
      const k = ease(t, at - 0.05, 0.35);
      const key = w.toLowerCase().replace(/[^a-z0-9-]/g, '');
      return (
        <span
          key={i}
          style={{
            display: 'inline-block',
            marginRight: '0.24em',
            opacity: k,
            transform: `translateY(${(1 - k) * 0.35}em)`,
            filter: `blur(${(1 - k) * 8}px)`,
            color: accent[key] ?? color,
            fontStyle: italic.includes(key) ? 'italic' : 'normal',
          }}
        >
          {w}
        </span>
      );
    })}
  </div>
);

/** Word timings of a narration clip as [word, absolute start]. */
export const clipWords = (id: string): [string, number][] => {
  const c = TL.clips.find((x) => x.id === id)!;
  return c.words.map((w) => [w[0] as string, w[1] as number]);
};

/** Words appearing at given times, independent of narration. */
export const spread = (text: string, t0: number, step = 0.12): [string, number][] =>
  text.split(' ').map((w, i) => [w, t0 + i * step]);

export const Chip: React.FC<{
  t: number;
  at: number;
  color?: string;
  children: React.ReactNode;
  size?: number;
  solid?: boolean;
  style?: React.CSSProperties;
}> = ({t, at, color = C.cyan, children, size = 28, solid = false, style}) => {
  const k = springAt(t, at, 16, 0.5);
  const o = ease(t, at, 0.2);
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 12,
        padding: `${size * 0.42}px ${size * 0.8}px`,
        borderRadius: 999,
        border: `2px solid ${color}`,
        background: solid ? color : `${color}1A`,
        color: solid ? C.bg : C.ink,
        fontFamily: SANS,
        fontWeight: 600,
        fontSize: size,
        letterSpacing: '-0.01em',
        whiteSpace: 'nowrap',
        opacity: o,
        transform: `scale(${lerp(0.6, 1, k)})`,
        boxShadow: `0 0 ${30 * o}px ${color}33`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const Kicker: React.FC<{t: number; at: number; until: number; children: React.ReactNode;
  color?: string}> = ({t, at, until, children, color = C.gold}) => {
  const o = win(t, at, until, 0.4, 0.3);
  return (
    <div
      style={{
        position: 'absolute',
        top: 70,
        left: 0,
        right: 0,
        textAlign: 'center',
        fontFamily: SANS,
        fontWeight: 700,
        fontSize: 22,
        letterSpacing: '0.32em',
        color,
        opacity: o,
        transform: `translateY(${(1 - ease(t, at, 0.5)) * -14}px)`,
      }}
    >
      {children}
    </div>
  );
};

/** Big stamped word that slams in from scale 2.4. */
export const Stamp: React.FC<{t: number; at: number; color: string; size?: number; rotate?: number;
  children: React.ReactNode; style?: React.CSSProperties; border?: boolean}> = ({
  t, at, color, size = 120, rotate = -6, children, style, border = true,
}) => {
  if (t < at) return null;
  const k = springAt(t, at, 22, 0.45);
  return (
    <div
      style={{
        fontFamily: SANS,
        fontWeight: 800,
        fontSize: size,
        color,
        letterSpacing: '-0.02em',
        padding: border ? `${size * 0.08}px ${size * 0.3}px` : 0,
        border: border ? `${Math.max(4, size * 0.05)}px solid ${color}` : 'none',
        borderRadius: size * 0.16,
        transform: `rotate(${rotate}deg) scale(${lerp(2.4, 1, clamp(k, 0, 1.2))})`,
        opacity: ease(t, at, 0.08),
        textShadow: `0 0 40px ${color}55`,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** A number that rolls from `from` to `to` between t0 and t1. */
export const Roll: React.FC<{t: number; t0: number; t1: number; from: number; to: number;
  digits?: number}> = ({t, t0, t1, from, to, digits = 2}) => {
  const k = ease(t, t0, t1 - t0, Easing.inOut(Easing.cubic));
  return <>{lerp(from, to, k).toFixed(digits)}</>;
};

export const Card: React.FC<{style?: React.CSSProperties; children: React.ReactNode;
  glow?: string}> = ({style, children, glow}) => (
  <div
    style={{
      background: 'linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.025))',
      border: '1.5px solid rgba(255,255,255,0.12)',
      borderRadius: 28,
      boxShadow: `0 30px 80px rgba(0,0,0,0.45)${glow ? `, 0 0 60px ${glow}33` : ''}`,
      backdropFilter: 'blur(6px)',
      ...style,
    }}
  >
    {children}
  </div>
);

export const interp = interpolate;
