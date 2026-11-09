import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
for (const name of ['halls', 'companion']) await build({absWorkingDir:root, entryPoints:[`frontend/platform/${name}/index.tsx`],
  outfile:resolve(root,`static/platform/${name}.js`), bundle:true, format:'iife', platform:'browser',
  target:['es2022'], minify:true, jsx:'automatic', define:{'process.env.NODE_ENV':'"production"'},
  charset:'utf8',legalComments:'eof',logLevel:'info'});
