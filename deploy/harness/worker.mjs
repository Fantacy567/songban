// Copyright (c) 2026 2292576833. Songban integration; upstream keeps its MIT license.
// Container only: no host credentials, host mounts, outbound network or shell tools.
import { createServer } from 'node:http';
import { createInterface } from 'node:readline';
import { writeFile, readFile, mkdir, lstat } from 'node:fs/promises';
import { DeepSeekHarness } from './packages/sdk/client/lib/index.js';
import { studioPatch, studioOptions } from './profile.mjs';
const lines=createInterface({input:process.stdin});
const pending=new Map(); let startResolve;
const start=new Promise(resolve=>{startResolve=resolve;});
lines.on('line',line=>{
  try { const frame=JSON.parse(line);
    if(frame.type==='start') startResolve(frame);
    else if(frame.type==='model_response') { const next=pending.get(frame.id); pending.delete(frame.id); next?.(frame); }
  } catch { process.exit(2); }
});
// Await pipe flush before shutdown; process.exit can truncate a large project.
const emit=value=>new Promise((resolve,reject)=>process.stdout.write(JSON.stringify(value)+'\n',error=>error?reject(error):resolve()));
const server=createServer(async(req,res)=>{
  try {
    if(req.method!=='POST'||!['/v1/chat/completions','/chat/completions'].includes(req.url)) {res.writeHead(403).end();return;}
    let raw=''; for await(const chunk of req) {raw+=chunk; if(raw.length>180000) throw new Error('limit');}
    const id=crypto.randomUUID();
    const response=new Promise(resolve=>pending.set(id,resolve));
    await emit({type:'model_request',id,method:req.method,path:req.url,body:JSON.parse(raw)});
    const out=await response; res.writeHead(out.status,{'content-type':out.content_type});res.end(out.body);
  } catch {res.writeHead(502).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const port=server.address().port;
const input=await start;
const names=['index.html','style.css','script.js'];
let harness;
try {
  await mkdir('/tmp/dsh',{recursive:true});
  for(const file of input.input.files) {
    if(!names.includes(file.path)||typeof file.content!=='string'||file.content.length>18000) throw new Error('files');
    await writeFile('/work/'+file.path,file.content,{flag:'wx'});
  }
  // JSON is valid YAML, preventing interpolation of user or model names as code.
  await writeFile('/tmp/songban.patch.yml',JSON.stringify(studioPatch(input,port)));
  harness=new DeepSeekHarness(studioOptions(input,process.env));
  const result=await harness.run([{type:'text',text:JSON.stringify({idea:input.input.idea,history:input.input.history,
    request:input.input.text,curriculum:input.input.curriculum,workspace:'/work',allowed_files:names})}]);
  const files=[];
  for(const path of names) {
    try {const stat=await lstat('/work/'+path);if(!stat.isFile()||stat.isSymbolicLink()||stat.size>54000)throw new Error('file');
      files.push({path,content:await readFile('/work/'+path,'utf8')});
    } catch(e) {if(e.code!=='ENOENT')throw e;}
  }
  await emit({type:'result',files,text:result.finalResponse,finish_reason:result.finishReason});
} catch {await emit({type:'failure'});}
finally {await harness?.close();server.close();lines.close();process.exit(0);}
