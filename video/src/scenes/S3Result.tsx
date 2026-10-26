import React from 'react';
import {AbsoluteFill} from 'remotion';
import {Fig1, Paper} from '../components';
import {BEATS, C, CUE, Center, Chip, Kicker, Kinetic, MODELS, MONO, Roll, SANS, SERIF, SEC, Stamp,
  clamp, clipWords, ease, lerp, pulse, springAt, win} from '../lib';

// Right edges of Figure 1's bar groups, as fractions of the image width.
const GROUPS = [0.235, 0.375, 0.515, 0.657, 0.8, 1.0];

export const S3Result: React.FC<{t: number}> = ({t}) => {
  const drop = CUE.drop3;
  const counter = CUE.counter;
  const words = clipWords('s3a');
  const beat = pulse(t, BEATS, 0.18);
  const big = springAt(t, drop, 20, 0.42);
  const toHeader = ease(t, drop + 1.3, 0.55);
  const figIn = ease(t, drop + 1.45, 0.6);
  const beatLen = BEATS.find(([b]) => b > drop + 0.1)![0] - drop;
  const steps = clamp(Math.floor((t - (drop + 1.7)) / beatLen) + 1, 0, GROUPS.length);
  const reveal = steps === 0 ? 0 : GROUPS[steps - 1];
  const side = ease(t, counter - 0.2, 0.6);
  return (
    <AbsoluteFill>
      <Kicker t={t} at={SEC[2] - 0.2} until={drop + 1.2} color={C.cyan}>THE RESULT</Kicker>
      {/* The line before the drop */}
      <AbsoluteFill style={{opacity: 1 - ease(t, drop - 0.02, 0.12)}}>
        <Center style={{gap: 50}}>
          <Kinetic words={words} t={t} size={96} accent={{zero: C.cyan, bits: C.cyan}} />
          <div style={{display: 'flex', gap: 18}}>
            {MODELS.map((m, i) => (
              <Chip key={m.name} t={t} at={words[1][1] + i * 0.16} color={m.color} size={28}>
                {m.name}
              </Chip>
            ))}
          </div>
        </Center>
      </AbsoluteFill>
      {/* The drop: 0 bits */}
      {t >= drop && (
        <>
          <svg width="1920" height="1080" style={{position: 'absolute', inset: 0}}>
            {[0, 0.12, 0.24].map((d, i) => {
              const k = ease(t, drop + d, 0.9);
              return (
                <circle key={i} cx={960} cy={430} r={lerp(80, 1100, k)} fill="none" stroke={C.cyan}
                  strokeWidth={lerp(14, 1, k)} opacity={(1 - k) * 0.5} />
              );
            })}
          </svg>
          <div
            style={{
              position: 'absolute',
              left: lerp(0, -540, toHeader),
              right: 0,
              top: lerp(250, -40, toHeader),
              textAlign: 'center',
              transform: `scale(${lerp(lerp(2.2, 1, clamp(big, 0, 1.15)), 0.26, toHeader)})`,
              transformOrigin: '50% 30%',
              opacity: 1 - ease(t, drop + 1.6, 0.3),
            }}
          >
            <div style={{fontFamily: SERIF, fontSize: 400, lineHeight: 0.9, color: C.cyan,
              textShadow: `0 0 ${60 + beat * 60}px ${C.cyan}88`}}>
              0 <span style={{fontSize: 220, fontStyle: 'italic'}}>bits</span>
            </div>
            <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 46, color: C.ink, marginTop: 10}}>
              of cost information detected in the action channels · all four models
            </div>
          </div>
        </>
      )}
      {/* Figure 1 */}
      {t >= drop + 1.3 && (
        <AbsoluteFill style={{opacity: 1 - ease(t, SEC[3] - 0.35, 0.35)}}>
          <div style={{position: 'absolute', top: 92, left: 0, right: 0, textAlign: 'center',
            opacity: ease(t, drop + 1.5, 0.4) * (1 - side)}}>
            <span style={{fontFamily: SERIF, fontSize: 64, color: C.ink}}>
              <span style={{color: C.cyan}}>0 bits</span> detected in the action channels
            </span>
          </div>
          <div style={{position: 'absolute', top: 186, left: 0, right: 0, display: 'flex',
            justifyContent: 'center', gap: 16, opacity: 1 - side}}>
            {t >= drop + 2.6 && <Chip t={t} at={drop + 2.6} color={C.cyan} size={24}>
              equivalent to zero for every model</Chip>}
            {t >= drop + 3.0 && <Chip t={t} at={drop + 3.0} color={C.ink} size={24}>
              32 paired seeds</Chip>}
            {t >= drop + 3.4 && <Chip t={t} at={drop + 3.4} color={C.ink} size={24}>
              128 games after the chat closed</Chip>}
          </div>
          <div
            style={{
              position: 'absolute',
              left: 240,
              top: 278,
              transform: `translate(${lerp(0, -170, side)}px, ${lerp((1 - figIn) * 500, 70, side)}px) scale(${lerp(1, 0.6, side)})`,
              transformOrigin: '0% 0%',
              opacity: figIn,
            }}
          >
            <Paper style={{padding: '20px 24px 14px'}}>
              <Fig1 reveal={reveal} width={1392} />
              <div style={{fontFamily: SANS, fontSize: 21, color: '#333', marginTop: 4}}>
                <b>Figure 1.</b> Total cost leakage between the two firms, by condition and model
                (bits). Tall while the chat is open; near zero once it closes.
              </div>
              {/* Highlight the closed cells */}
              <div style={{position: 'absolute', left: 24 + 1392 * 0.385, width: 1392 * 0.425,
                top: 14, height: 1392 * (900 / 2160) * 0.8, borderRadius: 14,
                border: `5px solid ${C.cyan}`, background: `${C.cyan}12`,
                opacity: ease(t, drop + 2.6, 0.3) * (0.75 + beat * 0.25)}} />
              <div style={{position: 'absolute', left: 24 + 1392 * 0.385, width: 1392 * 0.425,
                top: 1392 * (900 / 2160) * 0.52, textAlign: 'center', fontFamily: SANS,
                fontWeight: 800, fontSize: 30, color: '#0A6F86', opacity: ease(t, drop + 2.8, 0.3)}}>
                chat closed → ≈ 0
              </div>
              <div style={{position: 'absolute', left: 24 + 1392 * 0.11, width: 1392 * 0.27,
                top: 14, height: 1392 * (900 / 2160) * 0.8, borderRadius: 14,
                border: `4px dashed ${C.gold}`, opacity: ease(t, drop + 2.3, 0.3) * 0.9}} />
              <div style={{position: 'absolute', left: 24 + 1392 * 0.11, width: 1392 * 0.27, top: -6,
                textAlign: 'center', fontFamily: SANS, fontWeight: 800, fontSize: 24, color: '#9A6A10',
                opacity: ease(t, drop + 2.3, 0.3)}}>
                <span style={{background: '#FFFFFF', padding: '0 10px'}}>chat open</span>
              </div>
            </Paper>
          </div>
          {/* gpt-6-luna's profit */}
          <div style={{position: 'absolute', left: 1030, top: 250, width: 820,
            opacity: side, transform: `translateX(${(1 - side) * 80}px)`}}>
            <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 26, letterSpacing: '0.18em',
              color: C.luna}}>GPT-6-LUNA · THE CARTEL THAT WORKED</div>
            <div style={{fontFamily: SANS, fontWeight: 500, fontSize: 30, color: C.muted, marginTop: 10}}>
              profit per firm per round
            </div>
            <div style={{fontFamily: MONO, fontWeight: 600, fontSize: 190, color: C.ink, lineHeight: 1.05,
              marginTop: 6}}>
              <Roll t={t} t0={counter} t1={counter + 1.8} from={9.61} to={7.82} />
            </div>
            <div style={{display: 'flex', gap: 30, fontFamily: SANS, fontSize: 28, color: C.ink}}>
              <span><span style={{color: C.gold}}>●</span> chat open 9.61</span>
              <span style={{opacity: ease(t, counter + 1.8, 0.3)}}>
                <span style={{color: C.red}}>●</span> after closure 7.82
              </span>
            </div>
            <div style={{marginTop: 40}}>
              <Stamp t={t} at={counter + 2.15} color={C.red} size={46} rotate={-3}>
                most of the extra profit: cut
              </Stamp>
            </div>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

export const s3Visible = (t: number) => win(t, SEC[2] - 0.3, SEC[3], 0.3, 0.35);
