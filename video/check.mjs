// Render stills with the layout checker on, and collect its reports.
//   node check.mjs <outdir> [step-frames=15] [scale=0.25] [from=0] [to=3599]
// Writes <outdir>/f<frame>.jpg and <outdir>/layout.txt (one CHECK line per frame).
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition, openBrowser} from '@remotion/renderer';
import fs from 'node:fs';
import path from 'node:path';

const [outDir, step = '15', scale = '0.25', from = '0', to = '3599'] = process.argv.slice(2);
fs.mkdirSync(outDir, {recursive: true});
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const inputProps = {debug: true};
const browser = await openBrowser('chrome');
const composition = await selectComposition({serveUrl, id: 'Explainer', inputProps, puppeteerInstance: browser});
const lines = [];
for (let frame = Number(from); frame <= Number(to); frame += Number(step)) {
  await renderStill({
    serveUrl, composition, frame, inputProps, puppeteerInstance: browser, scale: Number(scale),
    imageFormat: 'jpeg', jpegQuality: 85, output: path.join(outDir, `f${String(frame).padStart(4, '0')}.jpg`),
    onBrowserLog: (log) => {
      if (log.text.startsWith('CHECK')) lines.push(log.text);
    },
  });
}
await browser.close({silent: true});
fs.writeFileSync(path.join(outDir, 'layout.txt'), lines.join('\n') + '\n');
const bad = lines.filter((l) => !l.endsWith(' ok'));
console.log(`${lines.length} frames checked, ${bad.length} with issues`);
for (const l of bad) console.log(l);
