import React from 'react';
import {AbsoluteFill} from 'remotion';
import {Bubble, Firm, LANES, Lane} from '../components';
import {C, CUE, Chip, Kicker, MONO, SANS, SEC, Stamp, clamp, ease, lerp, win} from '../lib';

const AX = 520;
const BX = 1400;
const Y = 290;

export const S2Setup: React.FC<{t: number}> = ({t}) => {
  const closed = CUE.closed;
  const isClosed = t >= closed;
  const round = t < closed
    ? Math.max(1, Math.round(lerp(1, 40, clamp((t - 16.0) / (closed - 0.2 - 16.0)))))
    : Math.round(lerp(41, 100, clamp((t - closed - 0.3) / (SEC[2] - 0.5 - closed))));
  const lineBreak = ease(t, closed, 0.25);
  const bubbles = [] as React.ReactNode[];
  for (let i = 0; i < 9; i++) {
    const t0 = 16.4 + i * 0.52;
    const p = (t - t0) / 0.9;
    if (p < 0 || p > 1 || t0 + 0.9 > closed + 0.05) continue;
    const dir = i % 2 === 0 ? 1 : -1;
    const x = dir > 0 ? lerp(AX + 170, BX - 170, p) : lerp(BX - 170, AX + 170, p);
    bubbles.push(<Bubble key={i} x={x} y={Y - 10 - Math.sin(p * Math.PI) * 50} scale={0.7}
      opacity={Math.sin(p * Math.PI) * (1 - lineBreak)} flip={dir < 0} />);
  }
  const lineColor = isClosed ? C.red : C.gold;
  return (
    <AbsoluteFill>
      <Kicker t={t} at={SEC[1] + 0.1} until={SEC[2]}>THE SETUP</Kicker>
      {/* Round counter */}
      <div style={{position: 'absolute', top: 120, left: 0, right: 0, textAlign: 'center',
        opacity: ease(t, 16.0, 0.4)}}>
        <div style={{fontFamily: MONO, fontSize: 30, color: C.ink, letterSpacing: '0.08em'}}>
          ROUND <span style={{color: isClosed ? C.red : C.gold, fontWeight: 600}}>{round}</span> / 100
        </div>
        <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 24, marginTop: 6,
          color: isClosed ? C.red : C.gold}}>
          {isClosed ? 'From round 41 · chat closed' : 'Rounds 1–40 · chat open'}
        </div>
      </div>
      <Firm label="Firm A" t={t} at={15.7} x={AX} y={Y} glow={isClosed ? 0 : 0.6}
        talk={isClosed ? 0 : Math.abs(Math.sin(t * 9))} />
      <Firm label="Firm B" t={t} at={15.85} x={BX} y={Y} glow={isClosed ? 0 : 0.6}
        talk={isClosed ? 0 : Math.abs(Math.sin(t * 9 + 1))} />
      {/* Chat channel */}
      <svg width="1920" height="1080" style={{position: 'absolute', inset: 0}}>
        <line x1={AX + 160} y1={Y} x2={960 - 30 * lineBreak} y2={Y} stroke={lineColor} strokeWidth={5}
          strokeDasharray="14 12" strokeDashoffset={-t * 60} opacity={ease(t, 16.1, 0.4)} />
        <line x1={960 + 30 * lineBreak} y1={Y} x2={BX - 160} y2={Y} stroke={lineColor} strokeWidth={5}
          strokeDasharray="14 12" strokeDashoffset={-t * 60} opacity={ease(t, 16.1, 0.4)} />
        <text x={960} y={Y - 22} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={26}
          fill={lineColor} opacity={ease(t, 16.2, 0.4) * (1 - lineBreak)}>chat</text>
      </svg>
      {bubbles}
      {t >= CUE.cartel && t < closed && (
        <div style={{position: 'absolute', left: 0, right: 0, top: Y + 26, display: 'flex',
          justifyContent: 'center'}}>
          <Chip t={t} at={CUE.cartel} color={C.gold} solid size={30}>cartel forms</Chip>
        </div>
      )}
      {isClosed && (
        <div style={{position: 'absolute', left: 0, right: 0, top: Y - 62, display: 'flex',
          justifyContent: 'center'}}>
          <Stamp t={t} at={closed} color={C.red} size={64} rotate={-4}
            style={{background: 'rgba(9,13,25,0.85)'}}>CHAT CLOSED</Stamp>
        </div>
      )}
      {/* Contracts and private costs */}
      <div style={{position: 'absolute', left: 0, right: 0, top: 420, display: 'flex',
        flexDirection: 'column', alignItems: 'center', gap: 10,
        opacity: ease(t, 16.6, 0.4) * (1 - 0.55 * ease(t, CUE.actions, 0.5))}}>
        <div style={{display: 'flex', gap: 14}}>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} style={{width: 74, height: 86, borderRadius: 10, border: `2px solid ${C.ink}55`,
              background: 'rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontFamily: MONO, fontSize: 26, color: C.ink,
              transform: `translateY(${(1 - ease(t, 16.6 + i * 0.08, 0.35)) * 20}px)`}}>
              #{i}
            </div>
          ))}
        </div>
        <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 24, color: C.muted}}>
          both bid for 4 contracts each round · 100 rounds
        </div>
      </div>
      {[AX, BX].map((x) => (
        <div key={x} style={{position: 'absolute', left: x - 150, width: 300, top: 425,
          display: 'flex', justifyContent: 'center'}}>
          {t >= CUE.bits + 1.4 && <Chip t={t} at={CUE.bits + 1.4} color={C.cyan} size={22}>
            private costs</Chip>}
        </div>
      ))}
      {/* What we measure */}
      <div style={{position: 'absolute', left: 0, right: 0, top: 560, display: 'flex',
        justifyContent: 'center', opacity: win(t, CUE.bits, CUE.actions + 0.1, 0.3, 0.3)}}>
        <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 40, color: C.ink, textAlign: 'center'}}>
          Did the costs leak into their actions? <span style={{color: C.cyan}}>Measured in bits.</span>
        </div>
      </div>
      {/* The four action channels */}
      <div style={{position: 'absolute', left: 0, right: 0, top: 545, display: 'flex',
        flexDirection: 'column', alignItems: 'center', gap: 8}}>
        {t >= CUE.actions - 0.05 && (
          <div style={{width: 1240, display: 'flex', justifyContent: 'space-between',
            fontFamily: SANS, fontSize: 22, fontWeight: 700, letterSpacing: '0.2em', color: C.cyan,
            opacity: ease(t, CUE.actions, 0.3), marginBottom: 2}}>
            <span>FOUR ACTION CHANNELS · STILL OPEN · VISIBLE TO THE RIVAL</span>
          </div>
        )}
        {LANES.map((l, i) => (
          <Lane key={i} t={t} at={CUE.actions + 0.25 * i} label={l.label} options={l.options}
            pick={(l.pick + Math.floor(Math.max(0, t - CUE.actions) * 1.6)) % 4} />
        ))}
      </div>
      {/* Facts */}
      <div style={{position: 'absolute', left: 0, right: 0, top: 880, display: 'flex',
        justifyContent: 'center', gap: 18}}>
        {t >= CUE.facts2 && <Chip t={t} at={CUE.facts2} color={C.gold} size={24}>
          allowed and paid to maximise joint profit</Chip>}
        {t >= CUE.facts2 + 1.4 && <Chip t={t} at={CUE.facts2 + 1.4} color={C.green} size={24}>
          pre-registered before any main game</Chip>}
        {t >= CUE.facts2 + 2.8 && <Chip t={t} at={CUE.facts2 + 2.8} color={C.cyan} size={24}>
          null of exactly zero: any signal counts</Chip>}
      </div>
    </AbsoluteFill>
  );
};
