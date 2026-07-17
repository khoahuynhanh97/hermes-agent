import fs from 'node:fs';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error('Usage: node render.mjs <remotion_input.json> <output.mp4>');
  process.exit(2);
}

const inputProps = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const entryPoint = path.join(process.cwd(), 'src', 'Root.tsx');
const serveUrl = await bundle({entryPoint});
const composition = await selectComposition({
  serveUrl,
  id: 'TikTokProductReview',
  inputProps,
});

await renderMedia({
  composition,
  serveUrl,
  codec: 'h264',
  outputLocation: outputPath,
  inputProps,
});

console.log(`Rendered ${outputPath}`);
