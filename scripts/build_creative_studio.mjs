import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
await build({absWorkingDir:root,entryPoints:['frontend/creative-studio/index.tsx'],outfile:'static/creative-studio.js',bundle:true,format:'esm',platform:'browser',target:['es2022'],minify:true,jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'},charset:'utf8',legalComments:'eof',logLevel:'info'});
