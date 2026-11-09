// Copyright (c) 2026 2292576833. Upstream retains its MIT license.
// Offline source contracts, NOT a full upstream build, agent or container test.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import vm from 'node:vm';
import ts from 'typescript';
import { studioPatch, studioOptions } from '../deploy/harness/profile.mjs';
import { fileDenial, apply } from '../deploy/harness/file-guard.mjs';

const [sourceArg, outputArg, python] = process.argv.slice(2);
if (!sourceArg || !outputArg || !python) throw new Error('Usage: node scripts/verify_harness_contracts.mjs <source> <evidence-dir> <python-with-PyYAML>');
const source = resolve(sourceArg), output = resolve(outputArg);
const revision = 'ce7073d51254c26cd63b22a60835b8f948deb447';
assert.equal(execFileSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' }).trim(), revision);
execFileSync('git', ['diff', '--exit-code', 'HEAD'], { cwd: source, stdio: 'pipe' });
await mkdir(output, { recursive: true });
const evidence = [], checks = [];
async function ast(path) {
  const body = await readFile(join(source, path), 'utf8');
  evidence.push({ path, sha256: createHash('sha256').update(body).digest('hex') });
  return ts.createSourceFile(path, body, ts.ScriptTarget.Latest, true);
}
function declaration(file, name) {
  const node = file.statements.find(node => node.name?.getText(file) === name);
  assert.ok(node, `Missing pinned declaration ${name}`);
  return node;
}
function members(file, name, keys) {
  const declarationNode = declaration(file, name);
  return keys.map(key => {
    const member = declarationNode.members.find(member => member.name?.getText(file) === key);
    assert.ok(member, `Missing pinned field ${name}.${key}`);
    return member.getText(file);
  }).join('\n');
}
function passed(name) { checks.push({ name, passed: true }); }

// Compile and invoke only the unmodified pure patch composer. Do not import
// app-boot or include's module side effects, evaluate !!js, or start the CLI.
const include = await ast('vendor/include/src/index.ts');
const composer = declaration(include, 'applyEntryPatches').getText(include);
const composerPath = join(output, 'pinned-patch-composer.mjs');
await writeFile(composerPath, ts.transpileModule(composer, { compilerOptions: {
  target: ts.ScriptTarget.ES2024, module: ts.ModuleKind.ESNext,
} }).outputText);
const { applyEntryPatches } = await import(pathToFileURL(composerPath));
const profilePath = 'packages/bundle/sdk-minimal/cordis.patch.yml';
const profileText = await readFile(join(source, profilePath), 'utf8');
evidence.push({ path: profilePath, sha256: createHash('sha256').update(profileText).digest('hex') });
const parseYaml = `import json,sys,yaml
class InertLoader(yaml.SafeLoader): pass
InertLoader.add_constructor('tag:yaml.org,2002:js', lambda loader,node: {'__jsExpr':loader.construct_scalar(node)})
with open(sys.argv[1],encoding='utf-8') as f: print(json.dumps(yaml.load(f,Loader=InertLoader)))`;
const base = JSON.parse(execFileSync(python, ['-c', parseYaml, join(source, profilePath)], { encoding: 'utf8' }));
const input = { model: 'synthetic-model', max_tokens: 800, input: { teaching: '虚构离线教学，不含孩子信息。' } };
const patch = studioPatch(input, 8906), warnings = [];
const rows = applyEntryPatches([], [...base, ...patch], (...args) => warnings.push(args));
assert.deepEqual(warnings, []);
const row = id => { const value = rows.find(row => row.id === id); assert.ok(value, id); return value; };
for (const id of ['llm-deepseek','persistent-bash','persistent-pwsh','terminal-bash','terminal-pwsh','tool-working-directory','compaction-basic','image-offload']) assert.equal(row(id).disabled, true);
assert.deepEqual(row('tool-fs').config, { read: true, readImage: false, write: true, edit: true, applyPatch: false });
assert.ok(row('sdk-jsonrpc-server').inject.includes('songbanFileGuard'));
assert.equal(row('sdk-jsonrpc-server').config.maxTokensAsSuccess, false);
assert.equal(row('songban-file-guard').name, '/opt/harness/file-guard.mjs');
const provider = row('songban-model').config.providers['songban-server'];
assert.equal(provider.baseURL, 'http://127.0.0.1:8906/v1');
assert.equal(provider.retryPolicy.maxRetries, 0);
assert.deepEqual(JSON.parse(JSON.stringify(patch)), patch);
passed('actual-upstream-pure-patch-composer-with-inert-sdk-minimal-yaml');

// Compile exact upstream members used at the integration seam. Dependencies
// outside these selected fields are deliberately excluded, not declared as any.
const sdk = await ast('packages/sdk/client/src/types.ts');
const config = await ast('packages/llm/llm-pi-ai/src/config.ts');
const catalog = await ast('packages/llm/llm-pi-ai/src/catalog.ts');
const retry = await ast('packages/llm/llm/src/retry-policy.ts');
const tool = await ast('packages/core/tools/src/contracts.ts');
const options = studioOptions(input, { PATH: '/synthetic/bin', PRIVATE_SENTINEL: 'not-inherited' });
assert.deepEqual(Object.keys(options.env).sort(), ['DSH_HOME','HOME','PATH','SONGBAN_RELAY_TOKEN']);
assert.deepEqual(await options.onUserQuestion(), { cancelled: true });
const { env, onUserQuestion, ...scalarOptions } = options;
const { models, compat, retryPolicy, ...scalarProvider } = provider;
const model = { ...models[0] }; delete model.reasoningEfforts;
const thinkingGate = catalog.statements.find(node => ts.isVariableStatement(node) && node.declarationList.declarations.some(d => d.name.getText(catalog) === 'THINKING_FORMAT_GATE'));
assert.ok(thinkingGate?.getText(catalog).includes("'deepseek': true"));
assert.ok(members(catalog, 'PiAiModelProfile', ['reasoningEfforts']).includes('false | PiAiReasoningEfforts'));
assert.equal(models[0].reasoningEfforts, false);
assert.equal(compat.thinkingFormat, 'deepseek');
const contractText = `// Exact selected members from pinned source; NOT full upstream typecheck.
interface LaunchOptions {
${members(sdk, 'HarnessClientOptions', ['profile','patches','dshHome','processCwd','initializeTimeoutMs','requestTimeoutMs'])}
${members(sdk, 'DeepSeekHarnessOptions', ['cwd','provider','model','maxTokens'])}
}
interface Result { ${members(sdk, 'RunResult', ['finalResponse','finishReason'])} }
interface Provider { ${members(config, 'PiAiProviderProfile', ['apiKeyEnv','api','baseURL','defaultContextWindow','defaultMaxTokens'])} }
interface Model { ${members(catalog, 'PiAiModelProfile', ['id','name','contextWindow'])} }
${declaration(retry, 'BackoffConfig').getText(retry)}
${declaration(retry, 'NormalRetryPolicyConfig').getText(retry)}
interface Invocation { ${members(tool, 'ToolExecutionInput', ['name','arguments'])} }
const options: LaunchOptions = ${JSON.stringify(scalarOptions)};
const provider: Provider = ${JSON.stringify(scalarProvider)};
const model: Model = ${JSON.stringify(model)};
const retry: NormalRetryPolicyConfig = ${JSON.stringify(retryPolicy)};
const invocation: Invocation = {name:'read',arguments:{file_path:'index.html'}};
declare const result: Result;
const text: string = result.finalResponse;
const completed: boolean = result.finishReason === 'completed';
// Negative sentinels make a weakened contract fail rather than silently pass.
// @ts-expect-error SDK maxTokens must remain numeric
const invalid: LaunchOptions = {maxTokens:'800'};
// @ts-expect-error old unpinned result field must not be accepted
const obsolete: string = result.text;
`;
const contractFile = join(output, 'selected-source-contracts.ts');
await writeFile(contractFile, contractText);
const program = ts.createProgram([contractFile], { noEmit: true, strict: true, types: [], target: ts.ScriptTarget.ES2024, module: ts.ModuleKind.ESNext });
const diagnostics = ts.getPreEmitDiagnostics(program);
await writeFile(join(output, 'typecheck.log'), ts.formatDiagnosticsWithColorAndContext(diagnostics, {
  getCanonicalFileName: f => f, getCurrentDirectory: () => output, getNewLine: () => '\n',
}) || 'Selected pinned-source contract typecheck: 0 diagnostics\n');
assert.equal(diagnostics.length, 0, 'See typecheck.log');
passed('selected-sdk-provider-retry-and-guard-member-types-zero-diagnostics');
passed('isolated-child-environment-and-question-dismissal');

// Assert the new plugin uses the real guard registration contract, with no
// filesystem operation or arbitrary model-generated command on this host.
const tools = await ast('packages/core/tools/src/index.ts');
const guard = declaration(tools, 'ToolsService').members.find(m => m.name?.getText(tools) === 'guard');
assert.ok(guard?.getText(tools).includes('guard: ToolGuard'));
const pipeline = await readFile(join(source, 'packages/core/tools/src/pipeline.ts'), 'utf8');
evidence.push({ path:'packages/core/tools/src/pipeline.ts', sha256:createHash('sha256').update(pipeline).digest('hex') });
assert.ok(pipeline.includes('this.tools.checkGuards(exec)'));
let registered, ready;
apply({ tools: { guard: callback => { registered = callback; } }, provide: (name, value) => { ready = {name,...value}; } });
assert.equal(typeof registered, 'function');
assert.deepEqual(ready, {name:'songbanFileGuard',ready:true});
const regular = () => ({ isSymbolicLink: () => false, isFile: () => true, size: 100 });
for (const name of ['read','write','edit']) for (const file_path of ['index.html','./style.css','/work/script.js']) {
  assert.equal(fileDenial({name,arguments:{file_path}}, regular), undefined);
}
for (const file_path of ['../tmp/songban.patch.yml','/tmp/dsh/profiles/sdk-minimal/cordis.patch.yml','/etc/passwd','/work/../tmp/x','/work/a.js','/work','index.html/','C:\\work\\index.html','/work//index.html','~/index.html','././index.html']) {
  assert.equal(typeof fileDenial({name:'read',arguments:{file_path}}, () => {throw new Error('must not touch disk');}), 'string');
}
for (const name of ['bash','pwsh','run_code','apply_patch','read_image','change_directory']) assert.equal(typeof fileDenial({name,arguments:{file_path:'index.html'}},regular),'string');
assert.ok(fileDenial({name:'write',arguments:{file_path:'index.html',content:'x'.repeat(18001)}},regular));
assert.ok(fileDenial({name:'read',arguments:{file_path:'index.html'}},() => ({isSymbolicLink:()=>true})));
assert.ok(fileDenial({name:'write',arguments:{file_path:'index.html',sandbox_permissions:'require_escalated'}},regular));
const missing = () => { throw Object.assign(new Error(),{code:'ENOENT'}); };
assert.equal(fileDenial({name:'write',arguments:{file_path:'index.html',content:''}},missing),undefined);
assert.ok(fileDenial({name:'read',arguments:{file_path:'index.html'}},missing));
passed('file-guard-allowlist-traversal-symlink-tool-escalation-size-and-missing-file');
const workerText = await readFile(new URL('../deploy/harness/worker.mjs',import.meta.url),'utf8');
const workerAst = ts.createSourceFile('worker.mjs',workerText,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
const emitNode = workerAst.statements.filter(ts.isVariableStatement).flatMap(s => [...s.declarationList.declarations]).find(d => d.name.getText(workerAst)==='emit');
assert.ok(emitNode);
let flush, wire, settled=false;
// Only the exact trusted emit function runs; this never imports the worker,
// starts its HTTP listener, writes project files, or launches an SDK runtime.
const emit = vm.runInNewContext('('+emitNode.initializer.getText(workerAst)+')', {
  process:{stdout:{write:(line,callback)=>{wire=line;flush=callback;return false;}}},
});
const largeFrame = {type:'result',files:[{path:'index.html',content:'字'.repeat(18000)}]};
const flushing = emit(largeFrame).then(()=>{settled=true;});
await Promise.resolve(); assert.equal(settled,false);
assert.deepEqual(JSON.parse(wire),largeFrame);
flush(); await flushing; assert.equal(settled,true);
const failedFlush=emit({type:'failure'});flush(new Error('synthetic pipe failure'));
await assert.rejects(failedFlush,/synthetic pipe failure/);
passed('actual-worker-emitter-waits-for-large-frame-pipe-flush');
await writeFile(join(output, 'composed-profile.json'), JSON.stringify(rows,null,2)+'\n');
await writeFile(join(output, 'UPSTREAM-LICENSE'), await readFile(join(source,'LICENSE')));
const report = { revision, checked_at:new Date().toISOString(), kind:'offline-selected-source-contracts',
  full_upstream_build:false, full_upstream_typecheck:false, real_agent_runtime:false, real_container:false,
  real_model_calls:0, checks, source_files:evidence };
await writeFile(join(output,'results.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
