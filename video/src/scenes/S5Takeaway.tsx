import React from 'react';
import {AbsoluteFill} from 'remotion';
import {Bubble} from '../components';
import {C, CUE, Card, Kicker, Kinetic, MONO, SANS, SERIF, SEC, clipWords, ease, springAt} from '../lib';

export const S5Takeaway: React.FC<{t: number}> = ({t}) => {
  const rule = CUE.rule;
  const up = ease(t, rule - 0.7, 0.6);
  const card = springAt(t, rule - 0.2, 12, 0.55);
  const cursor = Math.floor(t * 2.2) % 2 === 0;
  return (
    <AbsoluteFill>
      <Kicker t={t} at={SEC[4] + 0.1} until={SEC[5]}>THE TAKEAWAY</Kicker>
      {[0, 1, 2, 3, 4].map((i) => (
        <Bubble key={i} x={300 + i * 330} y={330 + Math.sin(t * 1.3 + i * 1.7) * 18 - up * 120}
          scale={0.6} opacity={ease(t, SEC[4] + 0.3 + i * 0.12, 0.4) * (1 - up) * 0.55} flip={i % 2 === 1} />
      ))}
      <div style={{position: 'absolute', left: 0, right: 0, top: 440 - up * 280, display: 'flex',
        justifyContent: 'center', transform: `scale(${1 - up * 0.3})`}}>
        <Kinetic words={clipWords('s5a')} t={t} size={96} accent={{talk: C.gold}} italic={['talk']} />
      </div>
      {t >= rule - 0.2 && (
        <div style={{position: 'absolute', left: 0, right: 0, top: 360, display: 'flex',
          justifyContent: 'center', opacity: ease(t, rule - 0.2, 0.25)}}>
          <Card glow={C.cyan} style={{width: 1400, padding: '44px 64px', boxSizing: 'border-box',
            transform: `scale(${0.85 + 0.15 * Math.min(card, 1.05)})`}}>
            <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 22, letterSpacing: '0.24em',
              color: C.cyan}}>IN OUR TEST</div>
            <div style={{fontFamily: SERIF, fontSize: 70, lineHeight: 1.12, color: C.ink, marginTop: 12}}>
              Closing the chat worked when what was left
              <span style={{fontStyle: 'italic', color: C.cyan}}> couldn't carry language.</span>
            </div>
            <div style={{display: 'flex', gap: 14, marginTop: 30, alignItems: 'center',
              opacity: ease(t, rule + 0.8, 0.4)}}>
              <span style={{fontFamily: SANS, fontSize: 26, color: C.muted, marginRight: 8}}>
                what was left: four 1-of-4 menus
              </span>
              {['status', 'utilisation', 'check-in', 'tool order'].map((l, i) => (
                <span key={l} style={{fontFamily: MONO, fontSize: 22, color: C.ink, padding: '8px 16px',
                  borderRadius: 10, border: '1.5px solid rgba(255,255,255,0.18)', whiteSpace: 'nowrap',
                  opacity: ease(t, rule + 0.9 + i * 0.1, 0.3)}}>
                  {l}
                </span>
              ))}
            </div>
          </Card>
        </div>
      )}
      {t >= CUE.freetext - 0.1 && (
        <div style={{position: 'absolute', left: 0, right: 0, top: 790, display: 'flex',
          justifyContent: 'center', alignItems: 'center', gap: 28,
          opacity: ease(t, CUE.freetext - 0.1, 0.35),
          transform: `translateY(${(1 - ease(t, CUE.freetext - 0.1, 0.4)) * 30}px)`}}>
          <div style={{width: 360, height: 70, borderRadius: 14, border: `3px dashed ${C.gold}`,
            display: 'flex', alignItems: 'center', padding: '0 22px', boxSizing: 'border-box',
            fontFamily: MONO, fontSize: 26, color: C.muted}}>
            free text…<span style={{color: C.gold, opacity: cursor ? 1 : 0, marginLeft: 4}}>|</span>
          </div>
          <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 40, color: C.ink}}>
            A free-text field? <span style={{color: C.gold}}>Not tested yet.</span>
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
