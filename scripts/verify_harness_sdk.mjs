// Copyright (c) 2026 2292576833. Upstream source retains its own MIT license.
// Offline, real pinned SDK client + upstream scripted server. NOT a container
// or real model acceptance test; no project/child/credential data is loaded.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { studioOptions } from '../deploy/harness/profile.mjs';

const revision='ce7073d51254c26cd63b22a60835b8f948deb447';
const [sourceArg, outputArg]=process.argv.slice(2);
if (!sourceArg || !outputArg) throw new Error('Usage: node scripts/verify_harness_sdk.mjs <pinned-source> <evidence-directory>');
const source=resolve(sourceArg), output=resolve(outputArg);
assert.equal(execFileSync('git',['rev-parse','HEAD'],{cwd:source,encoding:'utf8'}).trim(),revision);
execFileSync('git',['diff','--exit-code','HEAD'],{cwd:source,stdio:'pipe'});
await mkdir(output,{recursive:true});
await writeFile(join(output,'UPSTREAM-LICENSE'),await readFile(join(source,'LICENSE')));
// Import the precise public value providers used by SDK client. Session's
// public index re-exports these symbols; avoiding its unrelated service tree
// means no upstream dependency install or package lifecycle script is run.
const values={
  '@deepseek-ai/dsh-sdk-protocol':'packages/sdk/protocol/src/index.ts',
  '@deepseek-ai/dsh-session':'packages/core/session/src/types.ts',
  '@deepseek-ai/dsh-brand':'packages/util/brand/src/index.ts',
};
const sdkBundle=join(output,'pinned-sdk-client.mjs');
await build({entryPoints:[join(source,'packages/sdk/client/src/index.ts')],outfile:sdkBundle,
  platform:'node',format:'esm',bundle:true,target:'node24',plugins:[{name:'pinned-source-values',setup(b){
    b.onResolve({filter:/^@deepseek-ai\//},args=>{
      const file=values[args.path];
      if(!file) throw new Error('Unexpected upstream dependency: '+args.path);
      return {path:join(source,file)};
    });
  }}]});
const fixture=join(output,'upstream-scripted-server.mjs');
await build({entryPoints:[join(source,'packages/sdk/client/tests/fake-runtime.ts')],outfile:fixture,
  platform:'node',format:'esm',bundle:true,target:'node24'});
const {DeepSeekHarness}=await import(pathToFileURL(sdkBundle));
const outcomes=[];
const baseEnv={SystemRoot:process.env.SystemRoot,WINDIR:process.env.WINDIR,PATH:process.env.PATH};
async function probe(name,env,verify){
  const initFile=join(output,name+'-initialize.jsonl');
  await writeFile(initFile,'');
  const options=studioOptions({model:'synthetic-model',max_tokens:800},baseEnv);
  const harness=new DeepSeekHarness({...options,dshBin:fixture,dshHome:join(output,'home'),patches:[],
    processCwd:output,cwd:output,provider:'songban-server',model:'synthetic-model',maxTokens:800,
    env:{...baseEnv,...env,FAKE_RECORD_INIT:initFile},initializeTimeoutMs:1500,requestTimeoutMs:1500,
    shutdownTimeoutMs:500,disposeEofGraceMs:500,disposeGraceMs:500});
  let value,error;
  try { value=await harness.run([{type:'text',text:'虚构课程：请解释按钮事件。'}]); }
  catch(e){error=e;}
  finally{await harness.close();}
  await verify(value,error);
  const init=JSON.parse((await readFile(initFile,'utf8')).trim().split('\n').at(-1));
  assert.equal(init.provider,'songban-server');assert.equal(init.model,'synthetic-model');assert.equal(init.maxTokens,800);
  outcomes.push({name,passed:true,finish_reason:value?.finishReason??null,error_type:error?.name??null});
}
await probe('completed',{FAKE_TEXT:'点击后，事件处理函数会运行。'},(v,e)=>{
  assert.ifError(e);assert.equal(v.finishReason,'completed');assert.equal(v.finalResponse,'点击后，事件处理函数会运行。');
  assert.ok(v.events.some(event=>event.type==='assistant/message'));
});
for(const reason of ['max-tokens','blocked','interrupted','forked','aborted','error']){
  await probe(reason,{FAKE_TEXT:'未完成的回应',FAKE_REASON_KIND:reason},(v,e)=>{assert.ifError(e);assert.equal(v.finishReason,reason);});
}
await probe('malformed',{FAKE_MALFORMED:'initialize'},(v,e)=>{assert.ok(e);assert.equal(v,undefined);});
await probe('timeout',{FAKE_HANG_PROMPT:'1'},(v,e)=>{assert.ok(e);assert.equal(v,undefined);});
await probe('missing-reason',{FAKE_REASON_KIND:'none'},(v,e)=>{assert.ifError(e);assert.equal(v.finishReason,null);});
await probe('malformed-prompt',{FAKE_MALFORMED_PROMPT:'1'},(v,e)=>{assert.ok(e);assert.equal(v,undefined);});
await probe('malformed-event',{FAKE_MALFORMED_EVENT:'1'},(v,e)=>{assert.ok(e);assert.equal(v,undefined);});
await probe('runtime-exit',{FAKE_EXIT_DURING_PROMPT:'1'},(v,e)=>{assert.ok(e);assert.equal(v,undefined);});
const report={revision,checked_at:new Date().toISOString(),kind:'actual-sdk-client-with-upstream-scripted-server',
  source_build:'SDK client and its precise value dependencies bundled from unchanged pinned TypeScript source',
  real_container:false,real_agent_runtime:false,real_model_calls:0,real_child_data:false,checks:outcomes};
await writeFile(join(output,'results.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
