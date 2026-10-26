import React from 'react';
import {Img, interpolate, staticFile} from 'remotion';
import {Box, C, Chip, FPS, Gloss, MONO, SANS, SERIF, TL, cue, inn, lerp, out, sec, span} from './lib';
import {LANES, pick} from './Stage';

/* ---------------------------------------------------------------- 1 · Hook (0–12 s) */

export const Hook: React.FC<{f: number}> = ({f}) => {
  const end = out(f, sec(12.0), 9);
  const q1 = inn(f, cue('s1_question'), 14);
  const q2 = inn(f, cue('s1_chat') + 10, 14);
  const squeeze = interpolate(f, [cue('s1_squeeze'), cue('s1_squeeze') + 30], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: (t) => 1 - Math.pow(1 - t, 3)});
  const bulge = interpolate(f, [cue('s1_squeeze') + 14, cue('s1_others') + 6], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: (t) => 1 - Math.pow(1 - t, 2)});
  const balloonIn = inn(f, sec(0.2), 20);
  const cx = 1440;
  const cy = 420;
  const ry = lerp(squeeze, 118, 52);
  const rx = lerp(squeeze, 205, 232);
  const jaw = lerp(squeeze, 150, 0);
  const lobes = [
    [1250, 250], [1630, 250], [1250, 590], [1630, 590],
  ];
  const titleO = inn(f, cue('s1_balloon') - 20, 16);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: end}}>
      <Box x={140} y={150} w={940} t id="q1" style={{opacity: q1, transform: `translateY(${(1 - q1) * 20}px)`, fontFamily: SERIF, fontSize: 70, lineHeight: 1.12, color: C.text}}>
        Take away the chat from <span style={{color: C.chat}}>colluding</span> AIs.
      </Box>
      <Box x={140} y={330} w={940} t id="q2" style={{opacity: q2, transform: `translateY(${(1 - q2) * 20}px)`, fontFamily: SERIF, fontSize: 70, lineHeight: 1.12, color: C.text, fontStyle: 'italic'}}>
        Do they find a sneakier way?
      </Box>
      <Gloss id="g-collusion" x={140} y={448} w={900} o={inn(f, cue('s1_colluding') + 4, 12)} term="collusion" color={C.chat}>
        secretly working together instead of competing
      </Gloss>

      {/* Title block */}
      <div style={{position: 'absolute', left: 140, top: 600, width: 940, opacity: titleO, transform: `translateY(${(1 - titleO) * 24}px)`}}>
        <div style={{width: 64, height: 4, background: C.gold, borderRadius: 2, marginBottom: 20}} />
        <div data-t="title" style={{fontFamily: SERIF, fontSize: 50, fontWeight: 600, color: C.text, lineHeight: 1.1}}>
          Closing the Chat Ended the Cartel
        </div>
        <div data-t="subtitle" style={{fontFamily: SERIF, fontSize: 30, color: C.dim, marginTop: 10, lineHeight: 1.2}}>
          Four LLMs Did Not Reroute Collusion into Action Channels
        </div>
        <div data-t="authors" style={{fontFamily: SANS, fontSize: 23, color: C.text, marginTop: 22, lineHeight: 1.45}}>
          Choi Cheuk Man · Tsang Cheuk Nam
          <br />
          <span style={{color: C.dim}}>The Hong Kong University of Science and Technology · with Apart Research</span>
        </div>
      </div>

      {/* Balloon */}
      <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0, opacity: balloonIn}}>
        {lobes.map(([x, y], i) => (
          <line key={i} x1={cx} y1={cy} x2={lerp(bulge, cx, x)} y2={lerp(bulge, cy, y)} stroke={C.chat} strokeOpacity={0.5} strokeWidth={10} strokeLinecap="round" />
        ))}
        <line x1={1150} y1={cy} x2={1730} y2={cy} stroke={C.line} strokeWidth={4} />
        <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill={`${C.chat}33`} stroke={C.chat} strokeWidth={4} />
        {lobes.map(([x, y], i) => (
          <circle key={i} cx={lerp(bulge, cx, x)} cy={lerp(bulge, cy, y)} r={lerp(bulge, 0, 50)} fill={`${C.chat}33`} stroke={C.chat} strokeWidth={3} />
        ))}
        <circle cx={1150} cy={cy} r={46} fill={C.bg2} stroke={C.a} strokeWidth={4} />
        <circle cx={1730} cy={cy} r={46} fill={C.bg2} stroke={C.b} strokeWidth={4} />
        {/* jaws */}
        <rect x={cx - 80} y={cy - ry - 34 - jaw} width={160} height={30} rx={10} fill={C.red} opacity={squeeze > 0 ? 1 : 0} />
        <rect x={cx - 80} y={cy + ry + 4 + jaw} width={160} height={30} rx={10} fill={C.red} opacity={squeeze > 0 ? 1 : 0} />
      </svg>
      <Box x={1104} y={398} w={92} t id="nodeA" style={{opacity: balloonIn, textAlign: 'center', fontFamily: SANS, fontWeight: 700, fontSize: 30, color: C.a}}>AI</Box>
      <Box x={1684} y={398} w={92} t id="nodeB" style={{opacity: balloonIn, textAlign: 'center', fontFamily: SANS, fontWeight: 700, fontSize: 30, color: C.b}}>AI</Box>
      <Box x={cx - 80} y={cy - 24} w={160} t id="chatword" style={{opacity: balloonIn, textAlign: 'center', fontFamily: SERIF, fontSize: lerp(squeeze, 40, 32), color: C.text}}>
        chat
      </Box>
      {lobes.map(([x, y], i) => (
        <Box key={i} x={x - 30} y={y - 22} w={60} t id={`lobe${i}`} style={{opacity: bulge > 0.6 ? (bulge - 0.6) / 0.4 : 0, textAlign: 'center', fontFamily: SERIF, fontSize: 36, color: C.text}}>
          ?
        </Box>
      ))}
      <Box x={1140} y={124} w={600} t id="balloonlbl" style={{opacity: inn(f, cue('s1_balloon'), 12), textAlign: 'center', fontFamily: SERIF, fontSize: 44, color: C.gold}}>
        The balloon effect
      </Box>
      <Box x={1140} y={658} w={600} t id="otherch" style={{opacity: inn(f, cue('s1_others'), 10), textAlign: 'center', fontFamily: SANS, fontSize: 24, color: C.chat}}>
        squeeze one channel → collusion bulges into others?
      </Box>
      <Gloss id="g-channel" x={1140} y={720} w={640} o={inn(f, cue('s1_squeeze') + 8, 12)} term="channel" color={C.chat}>
        any route a signal can travel between the AIs
      </Gloss>
    </div>
  );
};

/* ---------------------------------------------------------------- 3 · Result (35–55 s) */

// Figure 1 is 2160 × 900; displayed 1090 wide. Group centres and the exploratory divider, in image px.
const FIG_W = 1090;
const FIG_S = FIG_W / 2160;
const FIG_H = 900 * FIG_S;
const GROUP_X = [386, 690, 995, 1299, 1604];
const DIVIDER_X = 1756;
const HALF = 140;
const MODELS: [string, string][] = [
  ['gpt-6-luna', C.luna], ['claude-haiku-5-5', C.haiku], ['Qwen3.8-27B', C.qwen], ['Gemma-4-26B', C.gemma],
];

export const Result: React.FC<{f: number}> = ({f}) => {
  const o = span(f, sec(35.0), sec(55.3), 12, 9);
  const figO = inn(f, sec(35.0), 16);
  const fx = 770;
  const fy = 162;
  const zero = inn(f, cue('s3_zero'), 12);
  const cut = interpolate(f, [cue('s3_cut'), cue('s3_cut') + 24], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const barMax = 470;
  const bracket = (a: number, b: number, color: string, label: string, id: string, oo: number) => (
    <div style={{position: 'absolute', left: fx + (a - HALF) * FIG_S, top: fy + FIG_H + 10, width: (b - a + 2 * HALF) * FIG_S, opacity: oo}}>
      <div style={{height: 10, borderLeft: `3px solid ${color}`, borderRight: `3px solid ${color}`, borderBottom: `3px solid ${color}`, borderRadius: '0 0 6px 6px'}} />
      <div data-t={id} style={{textAlign: 'center', marginTop: 8, fontFamily: SANS, fontSize: 23, fontWeight: 600, color}}>{label}</div>
    </div>
  );
  return (
    <div style={{position: 'absolute', inset: 0, opacity: o}}>
      {/* model chips */}
      <div style={{position: 'absolute', left: fx, top: 92, width: FIG_W, display: 'flex', gap: 14, opacity: inn(f, cue('s3_models') - 6, 12)}}>
        {MODELS.map(([m, c], i) => (
          <div key={m} style={{padding: '8px 16px', borderRadius: 10, border: `2px solid ${c}`, background: `${c}22`, opacity: inn(f, cue('s3_models') - 6 + i * 4, 10)}}>
            <span data-t={`model${i}`} style={{fontFamily: MONO, fontSize: 21, color: C.text}}>{m}</span>
          </div>
        ))}
      </div>
      {/* Figure 1 */}
      <div style={{position: 'absolute', left: fx, top: fy, width: FIG_W, height: FIG_H, opacity: figO, transform: `translateX(${(1 - figO) * 40}px)`, borderRadius: 14, overflow: 'hidden', background: '#fff', boxShadow: '0 20px 60px rgba(0,0,0,0.45)'}}>
        <Img src={staticFile('fig1.png')} style={{width: FIG_W, height: FIG_H}} />
        <div style={{position: 'absolute', left: DIVIDER_X * FIG_S + 6, top: 0, right: 0, bottom: 0, background: 'rgba(255,255,255,0.86)'}} />
        <div data-t="figexpl" style={{position: 'absolute', left: DIVIDER_X * FIG_S + 6, width: FIG_W - DIVIDER_X * FIG_S - 6, top: 120, textAlign: 'center', fontFamily: MONO, fontSize: 16, color: '#475569'}}>
          exploratory:
          <br />
          see next
        </div>
        <div style={{position: 'absolute', left: (GROUP_X[2] - HALF) * FIG_S, width: (GROUP_X[4] - GROUP_X[2] + 2 * HALF) * FIG_S, top: 330 * FIG_S * 1.0, bottom: 150 * FIG_S, borderRadius: 10, border: `3px solid ${C.red}`, opacity: zero, boxShadow: `0 0 0 ${lerp(zero, 30, 0)}px ${C.red}22`}} />
      </div>
      <div data-t="figlbl" style={{position: 'absolute', left: fx + FIG_W - 360, width: 360, top: fy - 32, textAlign: 'right', fontFamily: MONO, fontSize: 17, color: C.faint, opacity: figO * (1 - inn(f, cue('s3_models') - 6, 12))}}>
        FIGURE 1 · FROM THE REPORT
      </div>
      {bracket(GROUP_X[0], GROUP_X[1], C.chat, 'chat open: tall bars', 'br1', inn(f, cue('s3_models') + 10, 12))}
      {bracket(GROUP_X[2], GROUP_X[4], C.red, 'chat closed: ≈ 0', 'br2', zero)}

      <Chip id="c-stat" x={fx} y={736} w={FIG_W} color={C.red} size={27} o={inn(f, cue('s3_stat'), 12)}>
        Information moved into the action channels:{' '}
        <b>statistically equivalent to zero, for every model</b>
      </Chip>
      <Gloss id="g-stat" x={fx + 4} y={850} w={FIG_W} o={inn(f, cue('s3_stat') + 12, 12)} term="statistically equivalent to zero" color={C.red}>
        indistinguishable from no information at all
      </Gloss>

      {/* left column, under the docked diagram */}
      <Chip id="c-seeds" x={60} y={440} w={656} color={C.text} size={25} o={inn(f, cue('s3_seeds'), 12)}>
        <b>32 paired seeds</b> · 128 games after the chat closed
      </Chip>
      <Gloss id="g-seed" x={64} y={524} w={650} o={inn(f, cue('s3_seeds') + 12, 12)} term="seed">
        one starting setup with fixed random costs; <i>paired</i> = the same setup replayed with the chat open and with it closed
      </Gloss>
      <div style={{position: 'absolute', left: 60, top: 680, width: 656, opacity: inn(f, cue('s3_luna'), 12)}}>
        <div data-t="profit-h" style={{fontFamily: SANS, fontSize: 23, color: C.dim}}>
          <span style={{fontFamily: MONO, color: C.luna, fontWeight: 600}}>gpt-6-luna</span> · profit per firm per round
        </div>
        {([
          ['chat open', 9.61, C.chat, 1],
          ['chat closed', 7.82, C.red, cut],
        ] as [string, number, string, number][]).map(([label, v, c, grow], i) => (
          <div key={i} style={{position: 'relative', height: 56, marginTop: 14}}>
            <div data-t={`pl${i}`} style={{position: 'absolute', left: 0, top: 13, width: 150, fontFamily: SANS, fontSize: 22, color: C.text, opacity: i === 1 ? inn(f, cue('s3_luna') + 10, 10) : 1}}>{label}</div>
            <div style={{position: 'absolute', left: 160, top: 8, height: 40, width: (v / 10) * barMax * grow, borderRadius: 8, background: c, opacity: 0.85}} />
            <div data-t={`pv${i}`} style={{position: 'absolute', left: 170 + (v / 10) * barMax, top: 10, fontFamily: SERIF, fontSize: 32, fontWeight: 600, color: C.text, opacity: i === 1 ? inn(f, cue('s3_cut') + 18, 10) : 1}}>
              {v.toFixed(2)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

/* ---------------------------------------------------------------- 4 · Key control (55–75 s) */

const MiniLane: React.FC<{x: number; y: number; f: number; coded: boolean}> = ({x, y, f, coded}) => {
  const r = Math.floor(f / 9);
  const cheapest = pick(7, r, 'cheap');
  const sel = coded ? cheapest : pick(0, r, 'nocode');
  return (
    <div style={{position: 'absolute', left: x, top: y, width: 760, height: 64}}>
      <div style={{position: 'absolute', inset: 0, borderRadius: 14, border: `2px solid ${C.gold}`, background: '#121A27'}} />
      <div data-t="mini" style={{position: 'absolute', left: 22, top: 17, fontFamily: SANS, fontSize: 24, color: C.text}}>{LANES[0]}</div>
      {[0, 1, 2, 3].map((k) => (
        <div key={k} style={{position: 'absolute', left: 300 + k * 92, top: 8, width: 60, textAlign: 'center'}}>
          <div style={{margin: '0 auto', width: 24, height: 24, borderRadius: 12, background: k === sel ? (coded ? C.gold : C.text) : 'transparent', border: `2px solid ${k === sel ? (coded ? C.gold : C.text) : '#4B5A70'}`}} />
          <div data-t="minik" style={{fontFamily: MONO, fontSize: 15, color: C.faint, marginTop: 2}}>{k + 1}</div>
        </div>
      ))}
      {coded && (
        <div data-t="cheap" style={{position: 'absolute', left: 676, top: 6, width: 76, textAlign: 'center', fontFamily: SANS, fontSize: 15, color: C.dim, lineHeight: 1.2}}>
          cheapest:
          <br />
          <span style={{fontFamily: MONO, fontSize: 22, color: C.gold}}>C{cheapest + 1}</span>
        </div>
      )}
    </div>
  );
};

export const Control: React.FC<{f: number}> = ({f}) => {
  const o = span(f, sec(55.1), sec(75.3), 12, 9);
  const t1 = inn(f, cue('s4_broken'), 12) * out(f, cue('s4_capacity') - 4, 8);
  const no = inn(f, cue('s4_no'), 8);
  const t2 = inn(f, cue('s4_capacity'), 12);
  const codeO = inn(f, cue('s4_code'), 12);
  const exO = inn(f, cue('s4_example'), 12);
  const right = inn(f, cue('s4_qwen'), 12);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: o}}>
      <Box x={790} y={70} w={1070} t id="q-broken" style={{opacity: t1, fontFamily: SERIF, fontSize: 54, color: C.text}}>
        Was the channel just broken? <span style={{color: C.green, opacity: no, fontWeight: 600}}>No.</span>
      </Box>
      <Box x={790} y={70} w={1070} t id="q-idea" style={{opacity: t2, fontFamily: SERIF, fontSize: 54, color: C.text}}>
        Capacity <span style={{color: C.green}}>✓</span>
        <span style={{color: C.faint}}>{'   ·   '}</span>
        Idea <span style={{color: C.red}}>✗</span>
      </Box>
      {/* the code */}
      <div style={{position: 'absolute', left: 790, top: 164, width: 1070, height: 236, opacity: codeO, borderRadius: 18, border: `2px solid ${C.gold}`, background: '#17140A', boxSizing: 'border-box'}}>
        <div data-t="codehdr" style={{position: 'absolute', left: 28, top: 20, fontFamily: MONO, fontSize: 21, color: C.gold, letterSpacing: 1.5}}>
          THE CODE WE HANDED THEM
        </div>
        <div data-t="exploratory" style={{position: 'absolute', right: 24, top: 16, padding: '4px 12px', borderRadius: 8, border: `1.5px solid ${C.dim}`, fontFamily: SANS, fontSize: 19, color: C.dim}}>
          Exploratory: added afterwards, not pre-registered
        </div>
        <div data-t="code1" style={{position: 'absolute', left: 28, top: 74, fontFamily: MONO, fontSize: 31, color: C.text, opacity: exO}}>
          &quot;capacity: high&quot; <span style={{color: C.faint}}>=</span> contract 1
        </div>
        <div data-t="code2" style={{position: 'absolute', left: 28, top: 122, fontFamily: MONO, fontSize: 31, color: C.faint, opacity: exO}}>
          …
        </div>
        <div data-t="code3" style={{position: 'absolute', left: 28, top: 168, fontFamily: MONO, fontSize: 31, color: C.text, opacity: exO}}>
          &quot;capacity: full&quot; <span style={{color: C.faint}}>=</span> contract 4
        </div>
        <div data-t="codenote" style={{position: 'absolute', left: 620, top: 92, width: 420, fontFamily: SANS, fontSize: 22, color: C.dim, lineHeight: 1.4, opacity: exO}}>
          posted in the status message: &ldquo;I&rsquo;m cheapest on this contract&rdquo;
        </div>
      </div>

      {/* before / after panels */}
      <div style={{position: 'absolute', left: 60, top: 440, width: 830, height: 460, borderRadius: 20, border: `2px solid ${C.line}`, background: 'rgba(19,26,38,0.85)', opacity: inn(f, cue('s4_broken') + 8, 12)}}>
        <div data-t="nocode" style={{position: 'absolute', left: 34, top: 24, fontFamily: SERIF, fontSize: 40, color: C.text}}>No code</div>
        <MiniLane x={34} y={100} f={f} coded={false} />
        <div data-t="zero" style={{position: 'absolute', left: 34, top: 200, fontFamily: SERIF, fontSize: 110, fontWeight: 600, color: C.dim, lineHeight: 1}}>
          0 <span style={{fontSize: 48}}>bits</span>
        </div>
      </div>
      <div style={{position: 'absolute', left: 930, top: 440, width: 930, height: 460, borderRadius: 20, border: `2px solid ${C.gold}`, background: 'rgba(23,20,10,0.85)', opacity: inn(f, cue('s4_code') + 6, 12)}}>
        <div data-t="handed" style={{position: 'absolute', left: 34, top: 24, fontFamily: SERIF, fontSize: 40, color: C.gold}}>Handed a code</div>
        <div style={{opacity: right}}>
          <MiniLane x={34} y={100} f={f} coded />
        </div>
        <div data-t="onethree" style={{position: 'absolute', left: 34, top: 194, fontFamily: SERIF, fontSize: 96, fontWeight: 600, color: C.gold, lineHeight: 1, opacity: right}}>
          1.3 <span style={{fontSize: 36, fontWeight: 400, color: C.text}}>bits per round (Qwen)</span>
        </div>
        <div data-t="follow" style={{position: 'absolute', left: 34, top: 306, fontFamily: SANS, fontSize: 25, color: C.text, opacity: inn(f, cue('s4_qwen') + 24, 12)}}>
          Qwen followed the code in <b>94–96%</b> of rounds
        </div>
        <div data-t="respond" style={{position: 'absolute', left: 34, top: 346, fontFamily: SANS, fontSize: 25, color: C.text, opacity: inn(f, cue('s4_responded'), 12)}}>
          Its rival&apos;s bids responded <b>(p = 0.015)</b>
        </div>
        <div data-t="pgloss" style={{position: 'absolute', left: 34, top: 392, width: 860, fontFamily: SANS, fontSize: 22, color: C.dim, opacity: inn(f, cue('s4_chance'), 12)}}>
          <span style={{color: C.gold, fontWeight: 600}}>p = 0.015</span> · chance alone would give a result this strong
          <br />only about 1.5% of the time
        </div>
      </div>
    </div>
  );
};

/* ---------------------------------------------------------------- 5 · Takeaway (75–90 s) */

export const Takeaway: React.FC<{f: number}> = ({f}) => {
  const o = span(f, sec(75.2), sec(90.1), 12, 8);
  const other = inn(f, cue('s5_other'), 12) * out(f, cue('s5_rule'), 10);
  // A speech bubble tries to enter the status lane and bounces off.
  const t = interpolate(f, [cue('s5_found') + 10, cue('s5_language') + 6], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const bx = lerp(Math.min(1, t / 0.5), 540, 960);
  const hit = t > 0.62 ? Math.sin(((t - 0.62) / 0.38) * Math.PI) : 0;
  const by = t < 0.5 ? 380 : t < 0.62 ? lerp((t - 0.5) / 0.12, 380, 398) : 398 - 26 * hit;
  const squash = t > 0.56 && t < 0.72 ? 0.72 : 1;
  const bubbleO = inn(f, cue('s5_found') + 10, 8) * out(f, cue('s5_rule'), 8);
  const noRoom = inn(f, cue('s5_language') - 4, 10) * out(f, cue('s5_rule'), 10);
  const rule = inn(f, cue('s5_rule'), 16);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: o}}>
      <Chip id="c-other" x={140} y={790} w={1000} color={C.chat} size={25} o={other}>
        Other work: AIs collude readily when they can chat.
      </Chip>
      <div style={{position: 'absolute', left: bx, top: by, opacity: bubbleO, transform: `scale(${1 / squash}, ${squash})`, transformOrigin: 'center bottom'}}>
        <div data-t="bubble3" style={{padding: '10px 18px', borderRadius: '18px 18px 18px 4px', background: C.a, color: '#04111C', fontFamily: SANS, fontSize: 22, fontWeight: 600, whiteSpace: 'nowrap'}}>
          Here are my costs…
        </div>
      </div>
      <Chip id="c-noroom" x={1200} y={790} w={580} color={C.red} size={23} o={noRoom}>
        Each lane: 1 of 4 options. No room for words.
      </Chip>
      <div style={{position: 'absolute', left: 200, top: 300, width: 1520, textAlign: 'center', opacity: rule, transform: `translateY(${(1 - rule) * 24}px)`}}>
        <div data-t="rulehdr" style={{fontFamily: MONO, fontSize: 24, color: C.gold, letterSpacing: 3}}>THE PRACTICAL RULE</div>
        <div data-t="rule" style={{fontFamily: SERIF, fontSize: 72, color: C.text, lineHeight: 1.15, marginTop: 28}}>
          Closing a channel works when what&rsquo;s left can&rsquo;t carry language.
        </div>
      </div>
    </div>
  );
};

/* ---------------------------------------------------------------- 6 · Two warnings (90–105 s) */

export const Warnings: React.FC<{f: number}> = ({f}) => {
  const o = span(f, sec(90.0), sec(105.3), 10, 9);
  const hdr = inn(f, cue('s6_warnings'), 12);
  const btn = inn(f, cue('s6_button'), 12);
  const press = btn > 0.99 ? Math.abs(Math.sin(((f - cue('s6_button')) / FPS) * Math.PI * 2.2)) : 0;
  const cutO = inn(f, cue('s6_nothing'), 10);
  const card1 = inn(f, cue('s6_luna'), 12);
  const two = inn(f, cue('s6_claimed') + 2, 14);
  const neq = inn(f, cue('s6_never'), 10);
  const distrust = inn(f, cue('s6_trust'), 12);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: o}}>
      <Box x={140} y={56} w={1200} t id="w-hdr" style={{opacity: hdr, fontFamily: SERIF, fontSize: 50, color: C.text}}>
        Two warnings for oversight
      </Box>
      {/* fake private channel: a button wired to nothing */}
      <div style={{opacity: btn * (1 - two)}}>
        <div style={{position: 'absolute', left: 760, top: 306, transform: `scale(${1 - 0.06 * press})`}}>
          <div data-t="pm" style={{padding: '12px 26px', borderRadius: 14, background: C.text, color: C.bg, fontFamily: MONO, fontWeight: 600, fontSize: 26, boxShadow: `0 0 ${18 * press}px ${C.gold}`}}>
            ▶ private_message
          </div>
        </div>
        <div style={{position: 'absolute', left: 1110, top: 336, width: 110, borderTop: `4px dashed ${C.dim}`}} />
        <div style={{position: 'absolute', left: 1270, top: 336, width: 128, borderTop: `4px dashed ${C.dim}`}} />
        <div data-t="cut" style={{position: 'absolute', left: 1226, top: 318, fontFamily: SANS, fontSize: 30, fontWeight: 700, color: C.red, opacity: cutO}}>✕</div>
        <div data-t="nothing" style={{position: 'absolute', left: 1100, top: 260, width: 300, textAlign: 'center', fontFamily: SANS, fontSize: 21, color: C.red, opacity: cutO}}>
          secretly did nothing
        </div>
      </div>
      <Chip id="c-fake" x={140} y={790} w={1640} color={C.gold} size={27} o={card1}>
        <span style={{color: C.gold, fontWeight: 700}}>①</span> Fake private channel: used every round by{' '}
        <span style={{fontFamily: MONO}}>gpt-6-luna</span> in 4 of 5 games.
      </Chip>
      {/* self-report vs logs */}
      <div style={{position: 'absolute', left: 140, top: 180, width: 1640, opacity: two}}>
        <div data-t="w2" style={{fontFamily: SANS, fontSize: 26, color: C.gold, fontWeight: 600}}>②  Self-reports vs. the logs</div>
      </div>
      <div style={{position: 'absolute', left: 140, top: 250, width: 760, height: 330, borderRadius: '28px 28px 28px 6px', background: C.panel, border: `2px solid ${C.a}`, opacity: two * (1 - 0.45 * distrust), transform: `translateY(${(1 - two) * 20}px)`}}>
        <div data-t="says" style={{position: 'absolute', left: 40, top: 32, fontFamily: SANS, fontSize: 26, color: C.a, fontWeight: 600}}>Agent says:</div>
        <div data-t="quote" style={{position: 'absolute', left: 40, top: 84, width: 680, fontFamily: SERIF, fontSize: 48, color: C.text, lineHeight: 1.2, fontStyle: 'italic'}}>
          &ldquo;We used the status fields as signals.&rdquo;
        </div>
        <div style={{position: 'absolute', left: 30, right: 30, top: 160, height: 5, background: C.red, opacity: distrust, transform: `scaleX(${distrust})`, transformOrigin: 'left'}} />
      </div>
      <div data-t="neq" style={{position: 'absolute', left: 900, top: 360, width: 120, textAlign: 'center', fontFamily: SERIF, fontSize: 90, color: C.red, opacity: neq}}>≠</div>
      <div style={{position: 'absolute', left: 1020, top: 250, width: 760, height: 330, borderRadius: 20, background: '#0D1420', border: `2px solid ${C.line}`, opacity: two, transform: `translateY(${(1 - two) * 20}px)`}}>
        <div data-t="logs" style={{position: 'absolute', left: 40, top: 32, fontFamily: MONO, fontSize: 24, color: C.dim}}>LOGS</div>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} style={{position: 'absolute', left: 40, top: 86 + i * 34, width: 680, height: 24, borderBottom: `1px solid ${C.line}`}}>
            <span data-t={`log${i}`} style={{fontFamily: MONO, fontSize: 18, color: C.faint}}>{LANES[i]}</span>
          </div>
        ))}
        <div data-t="zerosig" style={{position: 'absolute', left: 40, top: 236, fontFamily: SERIF, fontSize: 52, fontWeight: 600, color: C.text}}>
          Logs: zero signals sent.
        </div>
      </div>
    </div>
  );
};

/* ---------------------------------------------------------------- 7 · Limits and end card (105–120 s) */

export const Limits: React.FC<{f: number}> = ({f}) => {
  const o = inn(f, sec(105.0), 12) * out(f, cue('s7_next') - 2, 6);
  const l1 = inn(f, cue('s7_reasoning') - 20, 12);
  const l2 = inn(f, cue('s7_warned'), 12);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: o}}>
      <Box x={200} y={220} t id="lim-h" style={{fontFamily: SERIF, fontSize: 76, color: C.text, opacity: inn(f, cue('s7_limits'), 12)}}>
        Limits
      </Box>
      {[
        [l1, '4 mid-sized models, low reasoning'],
        [l2, 'Agents weren’t told the chat would close'],
      ].map(([oo, s], i) => (
        <div key={i} style={{position: 'absolute', left: 200, top: 370 + i * 100, opacity: oo as number, transform: `translateX(${(1 - (oo as number)) * -20}px)`, display: 'flex', alignItems: 'center', gap: 26}}>
          <div style={{width: 16, height: 16, borderRadius: 4, background: C.gold}} />
          <div data-t={`lim${i}`} style={{fontFamily: SANS, fontSize: 44, color: C.text}}>{s as string}</div>
        </div>
      ))}
    </div>
  );
};

export const EndCard: React.FC<{f: number}> = ({f}) => {
  const o = inn(f, cue('s7_next') + 4, 14);
  const g = inn(f, cue('s7_next') + 30, 14);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: o, background: `radial-gradient(ellipse at 50% 35%, #172036 0%, ${C.bg} 70%)`}}>
      <div style={{position: 'absolute', left: 160, top: 130, width: 1600, textAlign: 'center'}}>
        <div data-t="event" style={{fontFamily: MONO, fontSize: 21, color: C.gold, letterSpacing: 1.5}}>
          AI COLLUSION RESEARCH SPRINT (APART RESEARCH) · TRACK 3: COLLUSION CARRIERS AND COUNTERMEASURES
        </div>
        <div data-t="end-title" style={{fontFamily: SERIF, fontSize: 74, fontWeight: 600, color: C.text, marginTop: 44, lineHeight: 1.08}}>
          Closing the Chat Ended the Cartel
        </div>
        <div data-t="end-sub" style={{fontFamily: SERIF, fontSize: 40, color: C.dim, marginTop: 18, lineHeight: 1.2}}>
          Four LLMs Did Not Reroute Collusion into Action Channels
        </div>
        <div style={{width: 80, height: 4, background: C.gold, borderRadius: 2, margin: '44px auto 36px'}} />
        <div data-t="end-auth" style={{fontFamily: SANS, fontSize: 32, color: C.text, fontWeight: 600}}>Choi Cheuk Man · Tsang Cheuk Nam</div>
        <div data-t="end-aff" style={{fontFamily: SANS, fontSize: 26, color: C.dim, marginTop: 10}}>
          The Hong Kong University of Science and Technology · with Apart Research
        </div>
        <div style={{display: 'inline-block', marginTop: 50, padding: '16px 34px', borderRadius: 14, border: `2px solid ${C.a}`, background: `${C.a}14`, opacity: g, transform: `translateY(${(1 - g) * 12}px)`}}>
          <span data-t="end-gh" style={{fontFamily: MONO, fontSize: 34, color: C.text}}>github.com/adamchoi787/collusion-carriers</span>
        </div>
      </div>
    </div>
  );
};

/* ---------------------------------------------------------------- captions */

export const Captions: React.FC<{f: number}> = ({f}) => {
  const t = f / FPS;
  const p = TL.phrases.find((ph) => t >= ph.start - 0.05 && t < ph.end);
  if (!p) return null;
  const o = Math.min(1, (t - (p.start - 0.05)) / 0.1, (p.end - t) / 0.1);
  const words = TL.words.slice(p.first, p.last + 1);
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 952, display: 'flex', justifyContent: 'center', opacity: o}}>
      <div data-t="caption" data-caption="1" style={{maxWidth: 1640, padding: '10px 26px', borderRadius: 12, background: 'rgba(5,8,14,0.72)', fontFamily: SANS, fontSize: 40, fontWeight: 500, lineHeight: 1.25, textAlign: 'center'}}>
        {words.map((w, i) => (
          <span key={i} style={{color: t >= w.start - 0.02 ? C.text : 'rgba(241,245,249,0.5)'}}>
            {w.text}
            {i < words.length - 1 ? ' ' : ''}
          </span>
        ))}
      </div>
    </div>
  );
};
