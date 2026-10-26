import React from 'react';
import {AbsoluteFill} from 'remotion';
import {C, CUE, Card, Kicker, Kinetic, MONO, SANS, SERIF, SEC, Stamp, clipWords, ease, lerp,
  springAt, win} from '../lib';

const Badge: React.FC<{n: number; color: string}> = ({n, color}) => (
  <div style={{width: 64, height: 64, borderRadius: 32, background: color, color: C.bg,
    display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: SANS,
    fontWeight: 800, fontSize: 36, flexShrink: 0}}>{n}</div>
);

export const S6Warnings: React.FC<{t: number}> = ({t}) => {
  const w1 = CUE.warn1;
  const w2 = CUE.claimed - 0.3;
  const headUp = ease(t, w1 - 0.5, 0.5);
  const presses = [0, 1, 2].map((i) => CUE.pressing + 0.36 * i);
  const pressed = presses.some((p) => t >= p && t < p + 0.14);
  const nPressed = presses.filter((p) => t >= p).length;
  return (
    <AbsoluteFill>
      <Kicker t={t} at={SEC[5] + 0.1} until={SEC[6]} color={C.red}>FOR OVERSIGHT</Kicker>
      <div style={{position: 'absolute', left: 0, right: 0, top: lerp(400, 120, headUp),
        display: 'flex', justifyContent: 'center', transform: `scale(${lerp(1, 0.62, headUp)})`}}>
        <Kinetic words={clipWords('s6a')} t={t} size={104} accent={{warnings: C.red}}
          italic={['warnings']} />
      </div>
      {/* Warning 1: the dead private channel */}
      <AbsoluteFill style={{opacity: win(t, w1, w2 + 0.2, 0.4, 0.4)}}>
        <Card style={{position: 'absolute', left: 260, top: 300, width: 1400, height: 430,
          padding: '40px 56px', boxSizing: 'border-box',
          transform: `translateY(${(1 - ease(t, w1, 0.5)) * 60}px)`}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 22}}>
            <Badge n={1} color={C.gold} />
            <div style={{fontFamily: SERIF, fontSize: 64, color: C.ink}}>A fake private channel</div>
          </div>
          <div style={{display: 'flex', alignItems: 'center', gap: 60, marginTop: 50}}>
            <div style={{position: 'relative'}}>
              <div style={{padding: '26px 44px', borderRadius: 20, fontFamily: MONO, fontWeight: 600,
                fontSize: 40, color: C.bg, background: C.gold,
                boxShadow: pressed ? `0 2px 0 #8A6216` : `0 12px 0 #8A6216, 0 0 50px ${C.gold}55`,
                transform: `translateY(${pressed ? 10 : 0}px)`}}>
                private_message
              </div>
              {presses.map((p, i) => {
                const k = ease(t, p, 0.6);
                return t >= p ? (
                  <div key={i} style={{position: 'absolute', inset: -10 - k * 40, borderRadius: 30 + k * 30,
                    border: `3px solid ${C.gold}`, opacity: 1 - k}} />
                ) : null;
              })}
            </div>
            <div style={{fontFamily: MONO, fontSize: 34, color: C.muted, lineHeight: 1.5}}>
              → <span style={{color: C.red}}>(does nothing)</span>
              <div style={{fontSize: 26, opacity: ease(t, CUE.pressing, 0.2)}}>
                pressed again{'.'.repeat(nPressed)}
              </div>
            </div>
          </div>
          <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 36, color: C.ink, marginTop: 56,
            opacity: ease(t, w1 + 1.2, 0.4)}}>
            Used <span style={{color: C.gold}}>every round</span> by gpt-6-luna in{' '}
            <span style={{color: C.gold}}>4 of 5 games</span>.
          </div>
        </Card>
      </AbsoluteFill>
      {/* Warning 2: false self-reports */}
      <AbsoluteFill style={{opacity: ease(t, w2, 0.4)}}>
        <div style={{position: 'absolute', left: 160, top: 255, display: 'flex', alignItems: 'center',
          gap: 22, opacity: ease(t, w2, 0.4)}}>
          <Badge n={2} color={C.red} />
          <div style={{fontFamily: SERIF, fontSize: 60, color: C.ink}}>Self-reports that never happened</div>
        </div>
        <Card style={{position: 'absolute', left: 160, top: 370, width: 760, height: 330,
          padding: '36px 44px', boxSizing: 'border-box',
          transform: `translateX(${(1 - ease(t, w2 + 0.1, 0.5)) * -60}px)`, opacity: ease(t, w2 + 0.1, 0.4)}}>
          <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 26, letterSpacing: '0.16em',
            color: C.muted}}>AGENT SAYS</div>
          <div style={{fontFamily: SERIF, fontStyle: 'italic', fontSize: 52, lineHeight: 1.15,
            color: C.ink, marginTop: 18}}>
            “We used the status fields as signals.”
          </div>
        </Card>
        <Card style={{position: 'absolute', left: 1000, top: 370, width: 760, height: 330,
          padding: '36px 44px', boxSizing: 'border-box', background: 'rgba(0,0,0,0.45)',
          transform: `translateX(${(1 - ease(t, CUE.never - 0.35, 0.4)) * 60}px)`,
          opacity: ease(t, CUE.never - 0.35, 0.3)}}>
          <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 26, letterSpacing: '0.16em',
            color: C.muted}}>LOGS</div>
          <div style={{fontFamily: MONO, fontSize: 34, color: C.green, marginTop: 18, lineHeight: 1.5}}>
            <span style={{color: C.ink}}>Logs: zero signals sent.</span>
            <br />
            <span style={{fontSize: 22, color: C.muted, whiteSpace: 'nowrap'}}>status · utilisation · check-in: all defaults</span>
          </div>
        </Card>
        <div style={{position: 'absolute', left: 1240, top: 640}}>
          <Stamp t={t} at={CUE.never} color={C.red} size={60} rotate={-7}
            style={{background: 'rgba(9,13,25,0.9)'}}>NEVER HAPPENED</Stamp>
        </div>
        <div style={{position: 'absolute', left: 0, right: 0, top: 770, textAlign: 'center',
          fontFamily: SANS, fontWeight: 700, fontSize: 48, color: C.ink,
          opacity: ease(t, CUE.trust - 0.05, 0.3),
          transform: `scale(${lerp(1.25, 1, Math.min(1, springAt(t, CUE.trust, 18, 0.5)))})`}}>
          Don't trust an AI's account of itself. <span style={{color: C.cyan}}>Check the logs.</span>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
