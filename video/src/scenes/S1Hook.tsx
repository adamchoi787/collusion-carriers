import React from 'react';
import {AbsoluteFill} from 'remotion';
import {Bubble, Firm} from '../components';
import {C, CUE, Center, Kinetic, SANS, SERIF, clamp, clipWords, ease, lerp, springAt, win} from '../lib';

const Balloon: React.FC<{t: number}> = ({t}) => {
  const sq = ease(t, CUE.squeeze, 0.7);
  const wob = springAt(t, CUE.squeeze, 9, 0.28);
  const grow = lerp(1, 1.36, clamp(wob, 0, 1.3));
  const breathe = 1 + Math.sin(t * 2.2) * 0.012;
  const bob = Math.sin(t * 1.4) * 6;
  const L = {x: 690, y: 575, rx: lerp(165, 58, sq) * breathe, ry: lerp(150, 118, sq) * breathe};
  const R = {x: 1120 + (grow - 1) * 90, y: 560, rx: 215 * grow * breathe, ry: 190 * grow * breathe};
  const neckH = lerp(110, 60, sq);
  const knotX = R.x + R.rx;
  return (
    <svg width="1920" height="1080" style={{position: 'absolute', inset: 0}}>
      <defs>
        <linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.28" />
          <stop offset="60%" stopColor="#FFFFFF" stopOpacity="0" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.25" />
        </linearGradient>
        <clipPath id="bal">
          <ellipse cx={L.x} cy={L.y} rx={L.rx} ry={L.ry} />
          <rect x={L.x} y={(L.y + R.y) / 2 - neckH / 2} width={R.x - L.x} height={neckH} />
          <ellipse cx={R.x} cy={R.y} rx={R.rx} ry={R.ry} />
        </clipPath>
      </defs>
      <g transform={`translate(0 ${bob})`}>
        <g clipPath="url(#bal)">
          <rect x={0} y={0} width={1920} height={1080} fill={C.gold} />
          <rect x={0} y={250} width={1920} height={700} fill="url(#shade)" />
        </g>
        <ellipse cx={R.x - R.rx * 0.35} cy={R.y - R.ry * 0.5} rx={R.rx * 0.22} ry={R.ry * 0.1}
          fill="#FFFFFF" opacity={0.4} transform={`rotate(-18 ${R.x - R.rx * 0.35} ${R.y - R.ry * 0.5})`} />
        <path d={`M ${knotX - 4} ${R.y} l 26 -16 l 0 32 z`} fill="#B9761A" />
        <text x={L.x} y={L.y + 14} textAnchor="middle" fontFamily={SANS} fontWeight={800}
          fontSize={lerp(48, 34, sq)} fill={sq > 0.5 ? '#8E1F1F' : C.bg}>chat</text>
        <text x={R.x} y={R.y + 16} textAnchor="middle" fontFamily={SANS} fontWeight={800}
          fontSize={44 * lerp(1, 1.12, clamp(wob, 0, 1))} fill={C.bg}>other channels</text>
      </g>
      {/* The clamp: two jaws closing on the chat lobe */}
      <g opacity={ease(t, CUE.squeeze - 0.3, 0.25)} transform={`translate(0 ${bob})`}>
        <rect x={L.x - 30} y={L.y - L.ry - 44} width={60} height={34} rx={10} fill={C.ink} />
        <rect x={L.x - 8} y={L.y - L.ry - 120} width={16} height={80} rx={6} fill={C.ink} />
        <rect x={L.x - 30} y={L.y + L.ry + 10} width={60} height={34} rx={10} fill={C.ink} />
        <rect x={L.x - 8} y={L.y + L.ry + 40} width={16} height={80} rx={6} fill={C.ink} />
      </g>
      <g opacity={ease(t, CUE.others - 0.2, 0.4)}>
        {[-1, 0, 1].map((i) => {
          const k = ease(t, CUE.others + (i + 1) * 0.1, 0.4);
          const a = (i * 32 * Math.PI) / 180;
          const r0 = R.rx + 40;
          return (
            <line key={i} x1={R.x + Math.cos(a) * r0} y1={R.y + bob + Math.sin(a) * r0 * 0.9}
              x2={R.x + Math.cos(a) * (r0 + 70 * k)} y2={R.y + bob + Math.sin(a) * (r0 + 70 * k) * 0.9}
              stroke={C.gold} strokeWidth={7} strokeLinecap="round" />
          );
        })}
      </g>
    </svg>
  );
};

export const S1Hook: React.FC<{t: number}> = ({t}) => {
  const a = clipWords('s1a');
  const qOut = 1 - ease(t, 6.15, 0.35);
  const take = a.find(([w]) => w.startsWith('away'))![1];
  const lift = ease(t, take, 0.6);
  const balloonWin = win(t, 6.35, CUE.title, 0.4, 0.15);
  const kick = ease(t, CUE.balloon - 0.1, 0.5);
  return (
    <AbsoluteFill>
      {/* Phase A: the question */}
      <AbsoluteFill style={{opacity: qOut}}>
        <Firm label="AI firm A" t={t} at={0.45} x={640} y={300} />
        <Firm label="AI firm B" t={t} at={0.6} x={1280} y={300} />
        <Bubble x={960} y={lerp(290, 150, lift)} scale={1.2} opacity={ease(t, 0.8, 0.3) * (1 - lift)} />
        <div style={{position: 'absolute', left: 0, right: 0, top: 520, display: 'flex', justifyContent: 'center'}}>
          <Kinetic words={a} t={t} size={78} maxWidth={1500} italic={['sneakier']}
            accent={{sneakier: C.gold}} />
        </div>
      </AbsoluteFill>
      {/* Phase B: the balloon effect */}
      <AbsoluteFill style={{opacity: balloonWin}}>
        <div
          style={{
            position: 'absolute',
            top: 120,
            left: 0,
            right: 0,
            textAlign: 'center',
            fontFamily: SERIF,
            fontStyle: 'italic',
            fontSize: 110,
            color: C.gold,
            opacity: kick,
            transform: `translateY(${(1 - kick) * 30}px)`,
          }}
        >
          The balloon effect
        </div>
        <Balloon t={t} />
        <div
          style={{
            position: 'absolute',
            top: 860,
            left: 0,
            right: 0,
            textAlign: 'center',
            fontFamily: SANS,
            fontWeight: 600,
            fontSize: 38,
            color: C.ink,
            opacity: ease(t, CUE.squeeze, 0.4),
          }}
        >
          squeeze one channel <span style={{color: C.gold}}>→</span> collusion moves to the others?
        </div>
      </AbsoluteFill>
      {/* Phase C: title card */}
      {t >= CUE.title && <Title t={t} />}
    </AbsoluteFill>
  );
};

const Title: React.FC<{t: number}> = ({t}) => {
  const h = CUE.title;
  const k1 = springAt(t, h, 18, 0.5);
  const k2 = ease(t, h + 0.8, 0.4);
  const k3 = ease(t, h + 1.1, 0.4);
  const zoom = 1 + (t - h) * 0.012;
  return (
    <Center style={{transform: `scale(${zoom})`}}>
      <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 22, letterSpacing: '0.3em',
        color: C.gold, opacity: k3, marginBottom: 36}}>
        AI COLLUSION RESEARCH SPRINT · TRACK 3
      </div>
      <div
        style={{
          fontFamily: SERIF,
          fontSize: 122,
          lineHeight: 1.02,
          color: C.ink,
          textAlign: 'center',
          transform: `scale(${lerp(1.5, 1, clamp(k1, 0, 1.1))})`,
          opacity: ease(t, h, 0.06),
          letterSpacing: '-0.015em',
        }}
      >
        Closing the Chat <br />
        <span style={{fontStyle: 'italic', color: C.gold}}>Ended the Cartel</span>
      </div>
      <div style={{fontFamily: SANS, fontWeight: 500, fontSize: 38, color: C.ink, marginTop: 30,
        opacity: k2, transform: `translateY(${(1 - k2) * 20}px)`}}>
        Four LLMs Did Not Reroute Collusion into Action Channels
      </div>
      <div style={{fontFamily: SANS, fontWeight: 500, fontSize: 28, color: C.muted, marginTop: 40,
        opacity: k3, textAlign: 'center', lineHeight: 1.5}}>
        Choi Cheuk Man · Tsang Cheuk Nam
        <br />
        The Hong Kong University of Science and Technology · with Apart Research
      </div>
    </Center>
  );
};
