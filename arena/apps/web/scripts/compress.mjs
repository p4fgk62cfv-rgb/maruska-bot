// Brotli and gzip copies of the text files in dist, made once at build time: the server sends
// the smallest one the browser accepts and never compresses on the fly.
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { brotliCompressSync, constants, gzipSync } from 'node:zlib';

const dist = new URL('../dist/', import.meta.url).pathname;
const TEXT = /\.(js|css|html|svg|json|webmanifest|txt)$/;
let before = 0;
let after = 0;

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (TEXT.test(name)) compress(path);
  }
}

function compress(path) {
  const raw = readFileSync(path);
  if (raw.length < 1024) return;
  const br = brotliCompressSync(raw, { params: { [constants.BROTLI_PARAM_QUALITY]: 11, [constants.BROTLI_PARAM_SIZE_HINT]: raw.length } });
  const gz = gzipSync(raw, { level: 9 });
  // A copy that is not smaller only costs a lookup.
  if (br.length < raw.length) writeFileSync(`${path}.br`, br);
  if (gz.length < raw.length) writeFileSync(`${path}.gz`, gz);
  before += raw.length;
  after += Math.min(br.length, raw.length);
}

walk(dist);
console.log(`compressed: ${(before / 1024).toFixed(0)} KB → ${(after / 1024).toFixed(0)} KB (brotli)`);
