// Start each legacy core acceptance script against its own disposable local service.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net');
const {spawn,spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const python=process.env.SONGBAN_QA_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
async function freePort(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p;}
function stop(child){if(!child||child.exitCode!==null)return;if(process.platform==='win32')spawnSync('taskkill',['/pid',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});else child.kill('SIGTERM');}
async function run(script){
 const output=path.resolve(process.env.SONGBAN_E2E_OUTPUT||path.join(root,'.browser-cache','core-fix'));
 fs.mkdirSync(output,{recursive:true});
 const folder=fs.mkdtempSync(path.join(output,path.basename(script,'.cjs')+'-')),port=await freePort(),base='http://127.0.0.1:'+port;
 const env={...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',SONGBAN_QA_DIR:folder,CORE_TEST_BASE:base,SONGBAN_QA_PYTHON:python,SONGBAN_E2E_OUTPUT:folder};
 const log=fs.openSync(path.join(folder,'server.log'),'w');
 const server=spawn(python,[path.join(__dirname,'core_acceptance_server.py'),'--dir',folder,'--port',String(port),'--plugin-home',path.join(folder,'plugin-home'),'--skill-home',path.join(folder,'skill-home')],{cwd:root,env,stdio:['ignore',log,log],windowsHide:true});
 let child;
 try{
  let ready=false;
  for(let i=0;i<100;i++){
   if(server.exitCode!==null)throw Error('QA service exited; see '+path.join(folder,'server.log'));
   try{const marker=await fetch(base+'/api/core-audit-fixture').then(r=>r.json());if(marker.isolated){ready=true;break;}}catch{}
   await new Promise(r=>setTimeout(r,200));
  }
  if(!ready)throw Error('QA service did not become ready');
  child=spawn(process.execPath,[script],{cwd:root,env,stdio:'inherit',windowsHide:true});
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
  if(code!==0)throw Error(path.basename(script)+' failed ('+code+'); evidence: '+folder);
  console.log('Evidence: '+folder);
 }finally{stop(child);stop(server);fs.closeSync(log);}
}
module.exports={run,python};
if(require.main===module)run(path.resolve(process.argv[2]||path.join(__dirname,'core_e2e.cjs'))).catch(e=>{console.error(e.message);process.exitCode=1;});
