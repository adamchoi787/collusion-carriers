// Render selected frames to PNG for review: node stills.mjs <outdir> <seconds...>
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'node:path';

const [outDir, ...secs] = process.argv.slice(2);
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const composition = await selectComposition({serveUrl, id: 'Explainer'});
for (const s of secs) {
  const frame = Math.round(Number(s) * composition.fps);
  const output = path.join(outDir, `t${String(s).padStart(6, '0')}.png`);
  await renderStill({serveUrl, composition, frame, output, scale: 0.5});
  console.log(output);
}
