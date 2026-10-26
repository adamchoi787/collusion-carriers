import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BEATS, C, CUE, Card, Center, Kicker, MONO, SANS, SERIF, SEC, clamp, ease, lerp, pulse,
  springAt, win} from '../lib';

const LIMITS = [
  {at: 'limit1', text: '4 mid-sized models, low reasoning'},
  {at: 'limit2', text: "Agents weren't told the chat would close"},
];

/** The four action channels doing a kick line on the finale's beats. */
const KickLine: React.FC<{t: number}> = ({t}) => {
  const beats = BEATS.filter(([b]) => b >= CUE.endcard - 0.01 && b < CUE.final);
  return (
    <div style={{display: 'flex', gap: 26, justifyContent: 'center'}}>
      {['status', 'utilisation', 'check-in', 'tool order'].map((l, i) => {
        let lift = 0;
        beats.forEach(([b], j) => {
          if (j % 4 === i && t >= b) lift = Math.max(lift, Math.exp(-(t - b) / 0.16));
        });
        if (t >= CUE.final) lift = Math.max(lift, Math.exp(-(t - CUE.final) / 0.3));
        return (
          <div key={l} style={{fontFamily: MONO, fontSize: 24, color: C.ink, padding: '10px 20px',
            borderRadius: 12, border: `1.5px solid ${C.cyan}88`, background: `${C.cyan}14`,
            transform: `translateY(${-lift * 26}px) rotate(${(i % 2 ? 1 : -1) * lift * 8}deg)`}}>
            {l}
          </div>
        );
      })}
    </div>
  );
};

export const S7End: React.FC<{t: number}> = ({t}) => {
  const card = CUE.endcard;
  const listOut = 1 - ease(t, card - 0.3, 0.3);
  const k = springAt(t, card, 16, 0.5);
  const beat = pulse(t, BEATS, 0.16);
  const fin = springAt(t, CUE.final, 18, 0.45);
  return (
    <AbsoluteFill>
      <Kicker t={t} at={SEC[6] + 0.1} until={card - 0.3} color={C.muted}>LIMITS AND NEXT STEPS</Kicker>
      <AbsoluteFill style={{opacity: listOut}}>
        <div style={{position: 'absolute', left: 300, top: 220, fontFamily: SERIF, fontSize: 90,
          color: C.ink, opacity: ease(t, SEC[6] + 0.3, 0.5)}}>Limits</div>
        {LIMITS.map((l, i) => (
          <div key={l.at} style={{position: 'absolute', left: 300, top: 370 + i * 110, display: 'flex',
            alignItems: 'center', gap: 26, opacity: ease(t, CUE[l.at] - 0.1, 0.4),
            transform: `translateX(${(1 - ease(t, CUE[l.at] - 0.1, 0.5)) * -50}px)`}}>
            <div style={{width: 18, height: 18, borderRadius: 9, background: C.gold}} />
            <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 50, color: C.ink}}>{l.text}</div>
          </div>
        ))}
        <Card glow={C.gold} style={{position: 'absolute', left: 300, top: 640, width: 1320,
          padding: '30px 44px', boxSizing: 'border-box', opacity: ease(t, CUE.next - 0.1, 0.4),
          transform: `translateY(${(1 - ease(t, CUE.next - 0.1, 0.5)) * 40}px)`}}>
          <span style={{fontFamily: SANS, fontWeight: 700, fontSize: 24, letterSpacing: '0.2em',
            color: C.gold}}>NEXT </span>
          <span style={{fontFamily: SERIF, fontSize: 56, color: C.ink, marginLeft: 16}}>
            Warn them the chat will close. <i style={{color: C.gold}}>Do they plan a code?</i>
          </span>
        </Card>
      </AbsoluteFill>
      {t >= card && (
        <Center style={{gap: 0, transform: `scale(${lerp(1.12, 1, clamp(k, 0, 1)) * (1 + beat * 0.008)})`,
          opacity: ease(t, card, 0.12) * (1 - ease(t, TL_END - 0.45, 0.45))}}>
          <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 22, letterSpacing: '0.3em',
            color: C.gold, marginBottom: 30}}>AI COLLUSION RESEARCH SPRINT · TRACK 3</div>
          <div style={{fontFamily: SERIF, fontSize: 104, lineHeight: 1.02, color: C.ink,
            textAlign: 'center', letterSpacing: '-0.015em'}}>
            Closing the Chat <span style={{fontStyle: 'italic', color: C.gold}}>Ended the Cartel</span>
          </div>
          <div style={{fontFamily: SANS, fontWeight: 500, fontSize: 34, color: C.ink, marginTop: 20}}>
            Four LLMs Did Not Reroute Collusion into Action Channels
          </div>
          <div style={{fontFamily: SANS, fontWeight: 500, fontSize: 28, color: C.muted, marginTop: 34,
            textAlign: 'center', lineHeight: 1.5}}>
            Choi Cheuk Man · Tsang Cheuk Nam
            <br />
            The Hong Kong University of Science and Technology · with Apart Research
          </div>
          <div style={{marginTop: 40, padding: '16px 34px', borderRadius: 999, fontFamily: MONO,
            fontSize: 32, color: C.bg, background: C.cyan, fontWeight: 600,
            transform: `scale(${1 + clamp(fin, 0, 1.2) * 0.0 + (t >= CUE.final ? (1 - clamp(fin)) * 0.15 : 0)})`,
            boxShadow: `0 0 ${40 + beat * 40}px ${C.cyan}66`}}>
            github.com/adamchoi787/collusion-carriers
          </div>
          <div style={{marginTop: 54, opacity: ease(t, card + 0.2, 0.3)}}>
            <KickLine t={t} />
          </div>
        </Center>
      )}
    </AbsoluteFill>
  );
};

const TL_END = SEC[7];
export const s7Window = (t: number) => win(t, SEC[6] - 0.3, SEC[7] + 1, 0.3, 0.1);
