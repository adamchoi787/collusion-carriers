import React, {useEffect} from 'react';
import {AbsoluteFill, Audio, continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';
import {C, cue, inn, out, sec} from './lib';
import {Stage} from './Stage';
import {Captions, Control, EndCard, Hook, Limits, Result, Takeaway, Warnings} from './Scenes';

/** Layout checker (debug renders only): logs text that overflows its box, leaves the frame,
 *  enters the caption band, or overlaps other visible text. */
const Checker: React.FC<{frame: number}> = ({frame}) => {
  useEffect(() => {
    const handle = delayRender('layout check');
    requestAnimationFrame(() => requestAnimationFrame(() => {
      measure();
      continueRender(handle);
    }));
  }, [frame]);
  const measure = () => {
    const opacity = (el: Element | null): number => {
      let o = 1;
      for (let e = el; e && e instanceof HTMLElement; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity || '1');
      return o;
    };
    const rootEl = Array.from(document.querySelectorAll('[data-root]')).find((r) => r.getBoundingClientRect().width > 0);
    if (!rootEl) {
      console.log(`CHECK ${frame} no-root`);
      return;
    }
    const root = rootEl.getBoundingClientRect();
    const k = 1920 / root.width;
    const norm = (r: DOMRect) => ({left: (r.left - root.left) * k, right: (r.right - root.left) * k, top: (r.top - root.top) * k, bottom: (r.bottom - root.top) * k, width: r.width * k});
    const items = Array.from(rootEl.querySelectorAll('[data-t]')).map((el) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      return {el, id: el.getAttribute('data-t') || '?', box: norm(el.getBoundingClientRect()), ink: norm(range.getBoundingClientRect()), o: opacity(el), cap: el.hasAttribute('data-caption')};
    }).filter((x) => x.o > 0.35 && x.ink.width > 0 && (x.el.textContent || '').trim());
    const issues: string[] = [];
    for (const x of items) {
      const {ink, box} = x;
      if (ink.left < 20 || ink.top < 20 || ink.right > 1900 || ink.bottom > 1060) issues.push(`offframe ${x.id}`);
      if ((x.el as HTMLElement).style.width && ink.right > box.right + 2) issues.push(`overflow ${x.id} (${Math.round(ink.right - box.right)}px)`);
      if (!x.cap && ink.bottom > 935) issues.push(`captionband ${x.id}`);
    }
    for (let i = 0; i < items.length; i++)
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j];
        if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const w = Math.min(a.ink.right, b.ink.right) - Math.max(a.ink.left, b.ink.left);
        const h = Math.min(a.ink.bottom, b.ink.bottom) - Math.max(a.ink.top, b.ink.top);
        if (w > 3 && h > 3) issues.push(`overlap ${a.id} × ${b.id} (${Math.round(w)}×${Math.round(h)})`);
      }
    console.log(`CHECK ${frame} ${issues.length ? issues.join(' | ') : 'ok'}`);
  };
  return null;
};

export const Explainer: React.FC<{debug?: boolean}> = ({debug}) => {
  const f = useCurrentFrame();
  const dock = inn(f, sec(35.0), 22) * out(f, sec(75.0), 22);
  // The diagram fades back while a full-screen statement sits over it.
  const dim = Math.max(
    0.95 * inn(f, cue('s5_rule'), 16) * out(f, sec(90.0), 10),
    0.95 * inn(f, cue('s6_claimed') - 2, 8),
    0.95 * inn(f, sec(105.0), 12),
    inn(f, cue('s7_next') + 4, 14),
  );
  return (
    <AbsoluteFill data-root style={{background: `radial-gradient(ellipse at 50% 40%, ${C.bg2} 0%, ${C.bg} 75%)`}}>
      <AbsoluteFill style={{backgroundImage: 'linear-gradient(rgba(148,163,184,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.045) 1px, transparent 1px)', backgroundSize: '60px 60px'}} />
      <Audio src={staticFile('mix.wav')} />
      {f < sec(12.4) && <Hook f={f} />}
      {f >= sec(11.8) && <Stage f={f} dock={dock} dim={dim} mode="build" />}
      {f >= sec(35) && f < sec(55.4) && <Result f={f} />}
      {f >= sec(55) && f < sec(75.4) && <Control f={f} />}
      {f >= sec(75) && f < sec(90.2) && <Takeaway f={f} />}
      {f >= sec(90) && f < sec(105.4) && <Warnings f={f} />}
      {f >= sec(105) && <Limits f={f} />}
      {f >= sec(113) && <EndCard f={f} />}
      <Captions f={f} />
      {debug && <Checker frame={f} />}
    </AbsoluteFill>
  );
};
