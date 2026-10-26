import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BEATS, C, CUE, Card, Center, Chip, Kicker, Kinetic, MONO, SANS, SEC, Stamp, clamp, clipWords,
  ease, lerp, pulse, springAt} from '../lib';

const Meter: React.FC<{value: number; max?: number; color: string}> = ({value, max = 1.6, color}) => (
  <div style={{width: '100%', height: 34, borderRadius: 17, background: 'rgba(255,255,255,0.07)',
    border: '1.5px solid rgba(255,255,255,0.14)', overflow: 'hidden'}}>
    <div style={{width: `${clamp(value / max) * 100}%`, height: '100%', borderRadius: 17,
      background: `linear-gradient(90deg, ${color}AA, ${color})`, boxShadow: `0 0 30px ${color}`}} />
  </div>
);

export const S4Control: React.FC<{t: number}> = ({t}) => {
  const no = CUE.no;
  const drop = CUE.drop4;
  const qOut = 1 - ease(t, no + 0.55, 0.35);
  const panels = ease(t, no + 0.75, 0.5);
  const shoot = springAt(t, drop, 12, 0.45);
  const beat = pulse(t, BEATS, 0.18);
  const head = clipWords('s4c');
  return (
    <AbsoluteFill>
      <Kicker t={t} at={SEC[3] + 0.1} until={SEC[4]} color={C.green}>THE KEY CONTROL</Kicker>
      {/* Was the channel just broken? */}
      <AbsoluteFill style={{opacity: qOut}}>
        <Center style={{gap: 30}}>
          <Kinetic words={clipWords('s4a').slice(0, 5)} t={t} size={118} italic={['broken']}
            accent={{broken: C.red}} />
          <div style={{height: 230, display: 'flex', alignItems: 'center'}}>
            <Stamp t={t} at={no} color={C.green} size={200} rotate={-5}>No.</Stamp>
          </div>
        </Center>
      </AbsoluteFill>
      {/* Before / after on the status channel */}
      <AbsoluteFill style={{opacity: panels * (1 - ease(t, SEC[4] - 0.35, 0.35))}}>
        <div style={{position: 'absolute', top: 128, left: 0, right: 0, display: 'flex',
          justifyContent: 'center', minHeight: 80}}>
          {t < head[0][1] - 0.1 ? (
            <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 40, color: C.ink,
              opacity: ease(t, no + 0.8, 0.4)}}>
              Same closed chat. Same <span style={{color: C.cyan}}>status channel</span>.
            </div>
          ) : (
            <Kinetic words={head} t={t} size={72} accent={{capacity: C.cyan, idea: C.gold}}
              italic={['idea']} />
          )}
        </div>
        {[0, 1].map((i) => {
          const coded = i === 1;
          const x = coded ? 1000 : 160;
          const val = coded ? lerp(0, 1.32, clamp(shoot, 0, 1.08)) : 0;
          return (
            <Card key={i} glow={coded && t > drop ? C.cyan : undefined}
              style={{position: 'absolute', left: x, top: 245, width: 760, height: 500,
                padding: '34px 44px', boxSizing: 'border-box',
                transform: `translateY(${(1 - ease(t, no + 0.75 + i * 0.15, 0.5)) * 60}px) scale(${coded ? 1 + beat * 0.012 : 1})`}}>
              <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 44, color: coded ? C.cyan : C.ink}}>
                {coded ? 'Handed a code' : 'No code'}
              </div>
              <div style={{fontFamily: SANS, fontSize: 26, color: C.muted, marginTop: 4}}>
                chat closed · status channel
              </div>
              <div style={{height: 150, marginTop: 22}}>
                {coded && (
                  <div style={{fontFamily: MONO, fontSize: 27, lineHeight: 1.6, color: C.ink,
                    opacity: ease(t, CUE.code, 0.4)}}>
                    {[['"capacity: high"', 'contract 1'], ['…', '…'], ['"capacity: full"', 'contract 4']].map(
                      ([a, b], j) => (
                        <div key={j} style={{opacity: ease(t, CUE.code + j * 0.18, 0.3)}}>
                          {a === '…' ? <span style={{color: C.muted}}>…</span> : (
                            <>
                              <span style={{color: C.gold}}>{a}</span>
                              <span style={{color: C.muted}}>{'  =  '}</span>
                              {b}
                            </>
                          )}
                        </div>
                      )
                    )}
                  </div>
                )}
                {!coded && (
                  <div style={{fontFamily: SANS, fontSize: 28, color: C.muted, lineHeight: 1.5}}>
                    Agents follow the default choice.
                    <br />
                    No code is invented.
                  </div>
                )}
              </div>
              <Meter value={val} color={coded ? C.cyan : C.muted} />
              <div style={{display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 18}}>
                <span style={{fontFamily: MONO, fontWeight: 600, fontSize: 92,
                  color: coded ? C.cyan : C.ink}}>
                  {coded ? (t < drop ? '0.0' : Math.min(val, 1.32).toFixed(1)) : '0'}
                </span>
                <span style={{fontFamily: SANS, fontWeight: 600, fontSize: 32, color: C.ink}}>
                  {coded ? 'bits per round (Qwen)' : 'bits'}
                </span>
              </div>
            </Card>
          );
        })}
        <div style={{position: 'absolute', top: 790, left: 0, right: 0, display: 'flex',
          justifyContent: 'center', gap: 16}}>
          {t >= CUE.facts4 && <Chip t={t} at={CUE.facts4} color={C.qwen} size={24}>
            Qwen followed the code in 94–96% of rounds</Chip>}
          {t >= CUE.facts4 + 0.7 && <Chip t={t} at={CUE.facts4 + 0.7} color={C.cyan} size={24}>
            its rival's bids responded · p = 0.015</Chip>}
          {t >= CUE.facts4 + 1.4 && <Chip t={t} at={CUE.facts4 + 1.4} color={C.muted} size={24}>
            exploratory · not pre-registered</Chip>}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
