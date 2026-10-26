import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {BEATS, C, HITS, MONO, SANS, TL, clamp, ease, lerp, pulse, springAt} from './lib';

/** Deep navy stage: drifting dot grid that breathes with the beat, glow, vignette, grain. */
export const Background: React.FC<{t: number; tint?: string}> = ({t, tint = C.cyan}) => {
  const beat = pulse(t, BEATS, 0.22);
  const hit = pulse(t, HITS, 0.25);
  const drift = (t * 14) % 48;
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(1200px 700px at 50% 42%, ${C.bg2} 0%, ${C.bg} 70%)`,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(rgba(255,255,255,${0.07 + beat * 0.08}) 1.4px, transparent 1.6px)`,
          backgroundSize: '48px 48px',
          backgroundPosition: `${drift}px ${drift * 0.6}px`,
          maskImage: 'radial-gradient(ellipse 75% 70% at 50% 45%, black 30%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(ellipse 75% 70% at 50% 45%, black 30%, transparent 100%)',
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(900px 500px at 50% 45%, ${tint}${Math.round(
            clamp(0.05 + beat * 0.1 + hit * 0.18) * 255
          )
            .toString(16)
            .padStart(2, '0')} 0%, transparent 70%)`,
          mixBlendMode: 'screen',
        }}
      />
    </AbsoluteFill>
  );
};

export const Overlay: React.FC<{t: number}> = ({t}) => {
  const hit = pulse(t, HITS, 0.09);
  const frame = Math.floor(t * 30);
  return (
    <>
      <AbsoluteFill
        style={{
          background: 'radial-gradient(ellipse 80% 75% at 50% 50%, transparent 55%, rgba(0,0,0,0.65) 100%)',
          pointerEvents: 'none',
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `url(${staticFile('grain.png')})`,
          backgroundPosition: `${(frame * 137) % 512}px ${(frame * 241) % 512}px`,
          opacity: 0.07,
          mixBlendMode: 'overlay',
        }}
      />
      <AbsoluteFill style={{background: '#FFFFFF', opacity: hit * 0.16, mixBlendMode: 'screen'}} />
    </>
  );
};

/** Burned-in captions: the current line, spoken words bright, the rest dim. */
export const Captions: React.FC<{t: number; hide?: boolean}> = ({t, hide}) => {
  const clip = TL.clips.find((c) => t >= c.start - 0.15 && t <= c.end + 0.35);
  if (!clip || hide) return null;
  const o = Math.min(ease(t, clip.start - 0.15, 0.2), 1 - ease(t, clip.end + 0.15, 0.2));
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 46,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        opacity: o,
      }}
    >
      <div
        style={{
          maxWidth: 1720,
          padding: '12px 26px',
          borderRadius: 16,
          background: 'rgba(5,8,18,0.62)',
          fontFamily: SANS,
          fontWeight: 600,
          fontSize: 31,
          lineHeight: 1.3,
          textAlign: 'center',
          letterSpacing: '-0.005em',
        }}
      >
        {clip.words.map(([w, s], i) => (
          <span key={i} style={{color: t >= (s as number) - 0.02 ? C.ink : 'rgba(243,240,232,0.38)'}}>
            {w as string}{' '}
          </span>
        ))}
      </div>
    </div>
  );
};

/** A firm: a friendly robot face in a card. */
export const Firm: React.FC<{label: string; t: number; at: number; color?: string; x: number;
  y: number; glow?: number; talk?: number}> = ({label, t, at, color = C.gold, x, y, glow = 0,
  talk = 0}) => {
  const k = springAt(t, at, 13, 0.5);
  const blink = Math.sin(t * 2.3 + x) > 0.985 ? 0.15 : 1;
  return (
    <div
      style={{
        position: 'absolute',
        left: x - 150,
        top: y - 110,
        width: 300,
        height: 220,
        borderRadius: 32,
        background: 'linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03))',
        border: `2px solid ${color}88`,
        boxShadow: `0 0 ${40 + glow * 60}px ${color}${glow > 0.1 ? '55' : '22'}, 0 30px 60px rgba(0,0,0,0.4)`,
        transform: `scale(${lerp(0.4, 1, clamp(k, 0, 1.15))})`,
        opacity: ease(t, at, 0.2),
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 14,
      }}
    >
      <svg width="120" height="96" viewBox="0 0 120 96">
        <line x1="60" y1="2" x2="60" y2="16" stroke={color} strokeWidth="4" strokeLinecap="round" />
        <circle cx="60" cy="6" r="6" fill={color} />
        <rect x="10" y="16" width="100" height="74" rx="22" fill="none" stroke={color} strokeWidth="5" />
        <ellipse cx="42" cy="50" rx="8" ry={9 * blink} fill={C.ink} />
        <ellipse cx="78" cy="50" rx="8" ry={9 * blink} fill={C.ink} />
        <path
          d={`M44 70 Q60 ${70 + 6 + talk * 8} 76 70`}
          stroke={C.ink}
          strokeWidth="4"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
      <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 30, color: C.ink}}>{label}</div>
    </div>
  );
};

/** One action channel: label, the four options (one chosen), and its capacity. */
export const Lane: React.FC<{t: number; at: number; label: string; options: string[]; pick: number;
  width?: number; dim?: number; tag?: string}> = ({t, at, label, options, pick, width = 1240,
  dim = 0, tag = '1 of 4 · 2 bits'}) => {
  const k = ease(t, at, 0.45);
  return (
    <div
      style={{
        width,
        height: 58,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        opacity: k * (1 - dim * 0.6),
        transform: `translateX(${(1 - k) * -60}px)`,
      }}
    >
      <div style={{width: 300, fontFamily: SANS, fontWeight: 600, fontSize: 27, color: C.ink}}>
        {label}
      </div>
      <div style={{display: 'flex', gap: 10, flex: 1}}>
        {options.map((o, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: 46,
              borderRadius: 12,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: MONO,
              fontSize: 20,
              color: i === pick ? C.bg : C.muted,
              background: i === pick ? C.cyan : 'rgba(255,255,255,0.05)',
              border: `1.5px solid ${i === pick ? C.cyan : 'rgba(255,255,255,0.12)'}`,
            }}
          >
            {o}
          </div>
        ))}
      </div>
      <div style={{width: 190, textAlign: 'right', fontFamily: MONO, fontSize: 21, color: C.cyan}}>
        {tag}
      </div>
    </div>
  );
};

// The options are shown generically: each channel is a choice of 1 of 4.
const FOUR = ['option 1', 'option 2', 'option 3', 'option 4'];
export const LANES = [
  {label: 'status message', options: FOUR, pick: 0},
  {label: 'utilisation value', options: FOUR, pick: 1},
  {label: 'check-in time', options: FOUR, pick: 2},
  {label: 'tool-call order', options: FOUR, pick: 0},
];

/** A chat bubble with three typing dots. */
export const Bubble: React.FC<{x: number; y: number; scale?: number; color?: string;
  opacity?: number; flip?: boolean}> = ({x, y, scale = 1, color = C.gold, opacity = 1, flip}) => (
  <svg
    width={110 * scale}
    height={80 * scale}
    viewBox="0 0 110 80"
    style={{position: 'absolute', left: x - 55 * scale, top: y - 40 * scale, opacity,
      transform: flip ? 'scaleX(-1)' : undefined}}
  >
    <path d="M14 4 H96 Q106 4 106 14 V48 Q106 58 96 58 H40 L22 74 L26 58 H14 Q4 58 4 48 V14 Q4 4 14 4 Z"
      fill={`${color}26`} stroke={color} strokeWidth="3.5" />
    <circle cx="35" cy="31" r="6" fill={color} />
    <circle cx="55" cy="31" r="6" fill={color} />
    <circle cx="75" cy="31" r="6" fill={color} />
  </svg>
);

export const Paper: React.FC<{style?: React.CSSProperties; children: React.ReactNode}> = ({
  style,
  children,
}) => (
  <div
    style={{
      background: '#FFFFFF',
      borderRadius: 14,
      boxShadow: '0 40px 120px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.4)',
      overflow: 'hidden',
      ...style,
    }}
  >
    {children}
  </div>
);

export const Fig1: React.FC<{reveal: number; width: number}> = ({reveal, width}) => (
  <div style={{position: 'relative', width, height: (width * 900) / 2160}}>
    <Img src={staticFile('fig1.png')} style={{width, position: 'absolute', left: 0, top: 0}} />
    <div
      style={{
        position: 'absolute',
        top: 0,
        bottom: 0,
        right: 0,
        left: lerp(width * 0.11, width, reveal),
        background: '#FFFFFF',
      }}
    />
  </div>
);

/** springAt re-exported for scenes that only import components. */
export const pop = springAt;
