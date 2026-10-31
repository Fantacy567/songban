import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
await build({
  absWorkingDir: root, entryPoints: ['frontend/workbench/index.tsx'],
  outfile: resolve(root, 'static/workbench/workbench.js'), bundle: true,
  format: 'iife', platform: 'browser', target: ['es2022'], minify: true,
  jsx: 'automatic', define: { 'process.env.NODE_ENV': '"production"' },
  legalComments: 'eof', charset: 'utf8', logLevel: 'info'
});
