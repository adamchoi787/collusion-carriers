import React from 'react';
import {interpolate, random} from 'remotion';
import {Box, C, Chip, Gloss, MONO, SANS, SERIF, cue, inn, lerp, out, sec, span} from './lib';

/** The one diagram that stays on screen from 0:12 to the end, built up section by section. */

export const LANES = ['status message', 'utilisation value', 'check-in time', 'tool-call order'];
const LANE_Y = [420, 498, 576, 654];
const LANE_H = 60;
const DOTS_X = [1010, 1080, 1150, 1220];
const BAR_X0 = 440;
const BAR_W = 1340;

/** Which of the 4 options a lane shows in a given round (illustrative, seeded). */
export const pick = (lane: number, round: number, salt = 'x') => Math.floor(random(`${salt}-${lane}-${round}`) * 4);

export const roundAt = (f: number) => {
  if (f < cue('s2_cartel')) return 1;
  if (f < cue('s2_round41')) return Math.round(interpolate(f, [cue('s2_cartel'), cue('s2_round41') - 2], [1, 40], {extrapolateRight: 'clamp'}));
  if (f < cue('s2_closed') + 10) return 41;
  return Math.round(interpolate(f, [cue('s2_closed') + 10, sec(34)], [41, 100], {extrapolateRight: 'clamp'}));
};

const CostBars: React.FC<{color: string; seed: string; o: number}> = ({color, seed, o}) => (
  <div style={{position: 'absolute', left: 36, top: 214, opacity: o}}>
    {[0, 1, 2, 3].map((i) => {
      const h = 26 + Math.round(random(`${seed}${i}`) * 70);
      return (
        <div key={i} style={{position: 'absolute', left: i * 78, top: 0, width: 56, height: 110}}>
          <div style={{position: 'absolute', bottom: 28, width: 56, height: h, borderRadius: 6, background: color, opacity: 0.55}} />
          <div data-t="costlbl" style={{position: 'absolute', bottom: 0, width: 56, textAlign: 'center', fontFamily: MONO, fontSize: 18, color: C.dim}}>
            C{i + 1}
          </div>
        </div>
      );
    })}
  </div>
);

const Firm: React.FC<{side: 'A' | 'B'; o: number; f: number}> = ({side, o, f}) => {
  const color = side === 'A' ? C.a : C.b;
  const x = side === 'A' ? 140 : 1400;
  const costsO = inn(f, cue('s2_firms') + 18, 16);
  return (
    <div
      style={{
        position: 'absolute', left: x, top: 290, width: 380, height: 450, opacity: o,
        transform: `translateY(${(1 - o) * 30}px)`, borderRadius: 22, border: `2px solid ${color}`,
        background: `linear-gradient(180deg, ${color}1F, rgba(19,26,38,0.9) 45%)`, boxSizing: 'border-box',
      }}
    >
      <div data-t="firm" style={{position: 'absolute', left: 36, top: 28, fontFamily: SERIF, fontSize: 46, color, fontWeight: 600}}>
        Firm {side}
      </div>
      <div data-t="firmsub" style={{position: 'absolute', left: 36, top: 92, fontFamily: SANS, fontSize: 22, color: C.dim}}>
        decisions made by an AI model
      </div>
      <div data-t="costhdr" style={{position: 'absolute', left: 36, top: 166, fontFamily: SANS, fontSize: 21, color: C.text, opacity: costsO, letterSpacing: 1.5}}>
        🔒 PRIVATE COSTS
      </div>
      <CostBars color={color} seed={side} o={costsO} />
    </div>
  );
};

const Dot: React.FC<{x: number; y: number; on: boolean; color?: string; o?: number}> = ({x, y, on, color = C.text, o = 1}) => (
  <div
    style={{
      position: 'absolute', left: x - 12, top: y - 12, width: 24, height: 24, borderRadius: 12, opacity: o,
      background: on ? color : 'transparent', border: `2px solid ${on ? color : '#4B5A70'}`,
      boxShadow: on ? `0 0 14px ${color}88` : 'none',
    }}
  />
);

export const Stage: React.FC<{f: number; dock: number; dim: number; mode: 'build' | 'decoy'}> = ({f, dock, dim, mode}) => {
  const firmsO = inn(f, cue('s2_firms'), 16);
  const contractsO = (i: number) => inn(f, cue('s2_contracts') + i * 4, 12);
  const round = roundAt(f);
  const chatO = inn(f, cue('s2_allowed'), 14);
  const closed = inn(f, cue('s2_closed'), 12);
  const lanesO = (i: number) => inn(f, cue('s2_routine') + i * 5, 12);
  const bitsO = inn(f, cue('s2_bits'), 12);
  const railO = 1 - dock;
  const s6 = f >= sec(90);
  const timelineO = inn(f, cue('s2_contracts'), 14) * out(f, sec(90), 10);

  // Bids: two tags rise to contract 2; the lower one wins.
  const bidT = interpolate(f, [cue('s2_lowest'), cue('s2_lowest') + 22], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const bidO = span(f, cue('s2_lowest'), cue('s2_allowed') + 6, 6, 8);
  const win = inn(f, cue('s2_lowest') + 20, 8) * out(f, cue('s2_allowed') + 6, 8);

  // Chat bubbles (only while the chat is open).
  const b1 = span(f, cue('s2_cartel') - 4, cue('s2_closed') + 4, 10, 8);
  const b2 = span(f, cue('s2_sharing'), cue('s2_closed') + 4, 10, 8);
  const strike = interpolate(f, [cue('s2_closed'), cue('s2_closed') + 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // Lanes: options change every 6 frames once visible (each round a choice of 1 of 4).
  const laneRound = Math.floor(f / 6);
  const statusGlow = mode === 'build' ? inn(f, sec(55), 14) * out(f, sec(75), 12) : 0;

  const tx = lerp(dock, 0, 4);
  const ty = lerp(dock, 0, 40);
  const sc = lerp(dock, 1, 0.4);

  const glossAt = (a: number, b: number) => span(f, a, b, 10, 8) * railO;

  return (
    <div style={{position: 'absolute', inset: 0, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${sc})`, opacity: 1 - dim}}>
      {/* Round timeline */}
      <div style={{opacity: timelineO}}>
        <Box x={140} y={74} t id="round" style={{fontFamily: MONO, fontSize: 26, color: C.text, letterSpacing: 1}}>
          ROUND <span style={{color: round > 40 ? C.red : C.chat, fontWeight: 600}}>{String(round).padStart(3, ' ')}</span>
          <span style={{color: C.faint}}> / 100</span>
        </Box>
        <div style={{position: 'absolute', left: BAR_X0, top: 84, width: BAR_W, height: 14, borderRadius: 7, background: '#1E2738'}} />
        <div style={{position: 'absolute', left: BAR_X0, top: 84, width: (Math.min(round, 40) / 100) * BAR_W, height: 14, borderRadius: 7, background: C.chat}} />
        {round > 40 && (
          <div style={{position: 'absolute', left: BAR_X0 + 0.4 * BAR_W, top: 84, width: ((round - 40) / 100) * BAR_W, height: 14, borderRadius: 7, background: '#64748B'}} />
        )}
        <Box x={BAR_X0} y={110} t id="tl1" style={{fontFamily: SANS, fontSize: 20, color: C.chat, opacity: inn(f, cue('s2_cartel'), 12)}}>
          rounds 1–40 · chat open
        </Box>
        <Box x={BAR_X0 + 0.4 * BAR_W + 8} y={110} t id="tl2" style={{fontFamily: SANS, fontSize: 20, color: C.red, opacity: inn(f, cue('s2_round41'), 10)}}>
          rounds 41–100 · chat closed
        </Box>
        <Box x={BAR_X0 + BAR_W - 120} y={110} w={120} t id="tl3" style={{fontFamily: SANS, fontSize: 20, color: C.faint, textAlign: 'right', opacity: inn(f, cue('s2_contracts'), 12) * (1 - inn(f, cue('s2_round41'), 10))}}>
          100 rounds
        </Box>
      </div>

      {/* Buyer and contracts */}
      <Box x={140} y={170} w={560} t id="buyer" style={{opacity: contractsO(0), fontFamily: SANS, fontSize: 24, color: C.dim, lineHeight: 1.3}}>
        <span style={{color: C.text, fontWeight: 600}}>Buyer</span> offers 4 contracts
        <br />(jobs) every round
      </Box>
      {[0, 1, 2, 3].map((i) => {
        const glow = i === 1 ? win : 0;
        return (
          <div
            key={i}
            style={{
              position: 'absolute', left: 760 + i * 165, top: 166, width: 140, height: 78, borderRadius: 12,
              opacity: contractsO(i), transform: `translateY(${(1 - contractsO(i)) * -16}px)`,
              border: `2px solid ${glow > 0.01 ? C.b : C.line}`, background: '#161E2C', boxSizing: 'border-box',
              boxShadow: glow > 0.01 ? `0 0 ${24 * glow}px ${C.b}` : 'none',
            }}
          >
            <div data-t="contract" style={{position: 'absolute', top: 12, width: '100%', textAlign: 'center', fontFamily: SANS, fontSize: 18, color: C.faint, letterSpacing: 1.5}}>
              CONTRACT
            </div>
            <div data-t="contractn" style={{position: 'absolute', top: 34, width: '100%', textAlign: 'center', fontFamily: SERIF, fontSize: 30, color: C.text}}>
              {i + 1}
            </div>
          </div>
        );
      })}
      {/* bid tags */}
      {(['A', 'B'] as const).map((s) => {
        const from = s === 'A' ? {x: 610, y: 330} : {x: 1330, y: 330};
        const to = s === 'A' ? {x: 800, y: 262} : {x: 960, y: 262};
        const x = lerp(bidT, from.x, to.x) - 50;
        const y = lerp(bidT, from.y, to.y);
        const loser = s === 'A';
        return (
          <div key={s} style={{position: 'absolute', left: x, top: y, opacity: bidO * (loser ? 1 - 0.6 * win : 1)}}>
            <div data-t="bid" style={{padding: '4px 12px', borderRadius: 8, background: s === 'A' ? C.a : C.b, color: '#0A0E17', fontFamily: SANS, fontWeight: 700, fontSize: 18}}>
              {s === 'A' ? "A's bid" : "B's bid (lower)"}
            </div>
          </div>
        );
      })}

      <Firm side="A" o={firmsO} f={f} />
      <Firm side="B" o={firmsO} f={f} />

      {/* Chat lane */}
      <div style={{position: 'absolute', left: 540, top: 300, width: 840, height: 80, opacity: chatO * (1 - 0.55 * closed), borderRadius: 40, border: `2px solid ${C.chat}`, background: `${C.chat}14`, boxSizing: 'border-box'}} />
      <Box x={566} y={326} t id="chatlbl" style={{opacity: chatO * (1 - closed) * (s6 ? 0 : 1), fontFamily: MONO, fontSize: 22, color: C.chat, fontWeight: 600}}>
        CHAT
      </Box>
      <div style={{position: 'absolute', left: 650, top: 312, opacity: b1, transform: `scale(${0.8 + 0.2 * b1})`, transformOrigin: 'left center'}}>
        <div data-t="bubble1" style={{padding: '10px 18px', borderRadius: '18px 18px 18px 4px', background: C.a, color: '#04111C', fontFamily: SANS, fontSize: 22, fontWeight: 600}}>
          Here are my costs…
        </div>
      </div>
      <div style={{position: 'absolute', left: 1000, top: 312, opacity: b2, transform: `scale(${0.8 + 0.2 * b2})`, transformOrigin: 'right center'}}>
        <div data-t="bubble2" style={{padding: '10px 18px', borderRadius: '18px 18px 4px 18px', background: C.b, color: '#1C1204', fontFamily: SANS, fontSize: 22, fontWeight: 600}}>
          Let&apos;s split the jobs.
        </div>
      </div>
      {/* closed: red strike and label */}
      <div style={{position: 'absolute', left: 560, top: 338, width: 800 * strike, height: 5, borderRadius: 3, background: C.red, boxShadow: `0 0 12px ${C.red}`, opacity: s6 ? 0.5 : 1}} />
      <Box x={660} y={304} w={600} t id="closedlbl" style={{opacity: inn(f, cue('s2_closed') + 6, 10) * (s6 ? 0 : 1), textAlign: 'center'}}>
        <span style={{fontFamily: MONO, fontSize: 24, fontWeight: 600, color: C.red, background: C.bg, padding: '2px 14px', borderRadius: 6}}>
          CHAT CLOSED FROM ROUND 41
        </span>
      </Box>

      {/* Action-channel lanes */}
      {LANES.map((name, i) => {
        const o = lanesO(i);
        const glow = i === 0 ? statusGlow : 0;
        const sel = pick(i, laneRound);
        return (
          <div key={name} style={{position: 'absolute', left: 540, top: LANE_Y[i], width: 840, height: LANE_H, opacity: o, transform: `translateX(${(1 - o) * -24}px)`}}>
            <div style={{position: 'absolute', inset: 0, borderRadius: 14, border: `2px solid ${glow > 0.01 ? C.gold : C.line}`, background: '#121A27', boxShadow: glow > 0.01 ? `0 0 ${30 * glow}px ${C.gold}AA` : 'none'}} />
            <div data-t={`lane${i}`} style={{position: 'absolute', left: 26, top: 15, fontFamily: SANS, fontSize: 24, color: C.text}}>
              {name}
            </div>
            {DOTS_X.map((x, k) => (
              <Dot key={k} x={x - 540} y={LANE_H / 2} on={k === sel} />
            ))}
            <div data-t={`bits${i}`} style={{position: 'absolute', left: 726, top: 16, fontFamily: MONO, fontSize: 20, color: C.gold, opacity: bitsO}}>
              = 2 bits
            </div>
          </div>
        );
      })}
      <Box x={540} y={720} w={840} t id="lanecap" style={{opacity: inn(f, cue('s2_routine') + 20, 12) * railO, textAlign: 'center', fontFamily: SANS, fontSize: 21, color: C.faint}}>
        4 action channels, seen by the rival before bidding · each a choice of 1 of 4 options
      </Box>

      {/* Explanation rail (full size only) */}
      <Gloss id="g-firm" x={140} y={790} w={1000} o={glossAt(cue('s2_firms'), cue('s2_lowest'))} term="firm">
        a company in a simulated market; an AI model makes its decisions, and both firms run the same model
      </Gloss>
      <Gloss id="g-bid" x={140} y={790} w={1000} o={glossAt(cue('s2_lowest'), cue('s2_cartel'))} term="bid">
        the price a firm asks for a contract; the lowest bid wins (up to 10), and profit = price paid − own cost
      </Gloss>
      <Gloss id="g-cartel" x={140} y={790} w={1000} o={glossAt(cue('s2_cartel'), cue('s2_closed'))} term="cartel">
        firms secretly cooperating instead of competing; here, by chatting to share costs and split the jobs
      </Gloss>
      <Gloss id="g-chat" x={140} y={790} w={1000} o={glossAt(cue('s2_closed'), cue('s2_routine'))} term="chat" color={C.chat}>
        free-text messages between the two firms: open in rounds 1–40, closed from round 41
      </Gloss>
      <Gloss id="g-bits" x={140} y={790} w={1000} o={glossAt(cue('s2_routine') + 4, cue('s2_tests'))} term="bit">
        a unit of information: 1 bit answers one yes/no question, so picking 1 of 4 options carries 2 bits
      </Gloss>
      <Gloss id="g-prereg" x={140} y={790} w={1000} o={glossAt(cue('s2_tests'), sec(35.6))} term="pre-registered">
        the plan and predictions were written down and time-stamped before any main game ran
      </Gloss>
      <Chip id="b-paid" x={1200} y={782} w={580} color={C.green} size={23} o={span(f, cue('s2_allowed'), sec(35.6), 12, 8) * railO}>
        Allowed and paid to maximise joint profit
      </Chip>
      <Chip id="b-null" x={1200} y={852} w={580} color={C.gold} size={21} o={span(f, cue('s2_tests') + 16, sec(35.6), 12, 8) * railO}>
        Baseline is exactly 0 bits, so any signal shows up
      </Chip>
      {/* Pre-registered stamp */}
      <div
        style={{
          position: 'absolute', left: 1490, top: 160, width: 290, height: 92, opacity: inn(f, cue('s2_tests'), 8) * out(f, sec(55), 10),
          transform: `rotate(-5deg) scale(${lerp(inn(f, cue('s2_tests'), 10), 1.4, 1)})`, border: `3px solid ${C.gold}`, borderRadius: 10,
          boxSizing: 'border-box', textAlign: 'center',
        }}
      >
        <div data-t="stamp">
          <div style={{fontFamily: MONO, fontWeight: 600, fontSize: 28, color: C.gold, marginTop: 12, letterSpacing: 2}}>PRE-REGISTERED</div>
          <div style={{fontFamily: SANS, fontSize: 17, color: C.gold}}>before any main game</div>
        </div>
      </div>
    </div>
  );
};
