import React from 'react';
import {AbsoluteFill, Audio, staticFile} from 'remotion';
import {Background, Captions, Overlay} from './components';
import {C, SEC, ease, shake, useT} from './lib';
import {S1Hook} from './scenes/S1Hook';
import {S2Setup} from './scenes/S2Setup';
import {S3Result} from './scenes/S3Result';
import {S4Control} from './scenes/S4Control';
import {S5Takeaway} from './scenes/S5Takeaway';
import {S6Warnings} from './scenes/S6Warnings';
import {S7End} from './scenes/S7End';

const SCENES = [S1Hook, S2Setup, S3Result, S4Control, S5Takeaway, S6Warnings, S7End];
const TINTS = [C.gold, C.gold, C.cyan, C.cyan, C.cyan, C.red, C.gold];

/** Crossfade with a little push-in and blur at each section boundary. */
const Scene: React.FC<{t: number; from: number; to: number; first: boolean; last: boolean;
  children: React.ReactNode}> = ({t, from, to, first, last, children}) => {
  const fin = first ? 1 : ease(t, from - 0.2, 0.4);
  const fout = last ? 1 : 1 - ease(t, to - 0.15, 0.4);
  const o = Math.min(fin, fout);
  if (o <= 0.001) return null;
  const pushIn = (1 - fin) * 0.05 - (1 - fout) * 0.04;
  return (
    <AbsoluteFill style={{opacity: o, transform: `scale(${1 - pushIn})`, filter: `blur(${(1 - o) * 8}px)`}}>
      {children}
    </AbsoluteFill>
  );
};

export const Explainer: React.FC = () => {
  const t = useT();
  const s = shake(t);
  const sec = Math.max(0, SEC.findIndex((x) => x > t) - 1);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <Audio src={staticFile('mix.wav')} />
      <Background t={t} tint={TINTS[Math.min(sec, 6)]} />
      <AbsoluteFill style={{transform: `translate(${s.x}px, ${s.y}px) rotate(${s.r}deg)`}}>
        {SCENES.map((Comp, i) => (
          <Scene key={i} t={t} from={SEC[i]} to={SEC[i + 1]} first={i === 0} last={i === 6}>
            <Comp t={t} />
          </Scene>
        ))}
      </AbsoluteFill>
      <Captions t={t} />
      <Overlay t={t} />
      <AbsoluteFill style={{background: '#000', opacity: 1 - ease(t, 0, 0.6)}} />
    </AbsoluteFill>
  );
};
