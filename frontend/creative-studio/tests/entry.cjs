/* New-route and entry compatibility fixtures; no real users or services. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const esbuild=require('esbuild'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../../..'),out=fs.mkdtempSync(path.join(os.tmpdir(),'songban-creative-entry-'));
const results=[];let browser;
async function check(name,action){await action();results.push({name,passed:true});console.log('PASS '+name);}
const fixture=`
import React,{useCallback} from 'react';import{createRoot}from'react-dom/client';
import{FirstWorkPage}from'./frontend/learning/FirstWorkPage';import{ApiError}from'./frontend/learning/api';
const params=new URLSearchParams(location.search),mode=params.get('mode');window.nav=[];window.writes=[];window.guard=false;window.receipt=false;
let entry={id:'e',learner_id:'child',revision:1,status:mode==='offer'?'offered':'confirmed',goals:['做一个能点的小网页'],experiences:['用过电脑'],source_version:1,candidate:null};
const home={learner_id:'child',revision:1,run_id:mode==='old'?'old-invitation-run':null,entitlements:[{id:'enrollment',status:'active',course_version_id:'invitation-course@0.1.0'}],allowed_actions:['createRun']};
const api={async request(p,method='GET',body){if(method!=='GET'){window.writes.push(p);await new Promise(r=>setTimeout(r,80));if(p.endsWith('/entry/confirm'))entry={...entry,revision:2,status:body.decision==='accept'?'confirmed':'declined'};window.receipt=true;return structuredClone(entry);}if(p.endsWith('/home'))return structuredClone(home);if(p.endsWith('/entry')){if(window.receipt)await new Promise(r=>setTimeout(r,80));return structuredClone(entry);}if(p==='/courses'){if(mode==='catalog-down')throw new ApiError(503,'course_unavailable','no catalogue');return{items:[{id:'invitation-course@0.1.0',state:'published',title:'原邀请卡'}],next_cursor:null};}throw new Error(p);}};
function App(){const guard=useCallback(g=>{window.guard=g.dirty;},[]);const navigate=useCallback(async route=>{window.nav.push({route,dirty:window.guard,receipt:window.receipt});return true;},[]);return <FirstWorkPage api={api} learnerId="child" config={{learning_enabled:true,studio_enabled:true}} setGuard={guard} navigate={navigate} creativeEnabled={mode!=='disabled'}/>;}
createRoot(document.getElementById('host')).render(<App/>);
`;
(async()=>{try{
 await esbuild.build({entryPoints:[path.join(root,'frontend/learning/routes.ts')],bundle:true,platform:'node',format:'cjs',outfile:path.join(out,'routes.cjs'),logLevel:'silent'});
 const {parseRoute}=require(path.join(out,'routes.cjs'));
 await check('creative-bookmark-allows-only-optional-project-id',async()=>{for(const value of ['#/learn/create','#/learn/create?id=cs_abc'])assert.ok(parseRoute(value));for(const value of ['#/learn/create?id=one&id=two','#/learn/create?id=','#/learn/create?version=one','#/learn/create?id=%2F%2Fevil.invalid','#/learn/create?role=admin'])assert.equal(parseRoute(value),null);});
 await esbuild.build({stdin:{contents:fixture,resolveDir:root,loader:'jsx'},bundle:true,jsx:'automatic',outfile:path.join(out,'fixture.js'),logLevel:'silent'});
 browser=await chromium.launch({headless:true,channel:'msedge'});const page=await browser.newPage();page.setDefaultTimeout(7000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://127.0.0.1/fixture*',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><meta charset="utf-8"><div id="host"></div>'}));
 const open=async mode=>{await page.goto('http://127.0.0.1/fixture?mode='+mode);await page.addScriptTag({path:path.join(out,'fixture.js')});};const button=name=>page.getByRole('button',{name,exact:true});
 await check('feature-off-preserves-original-invitation-entry',async()=>{await open('disabled');await button('开始我的第一个作品').waitFor();assert.equal(await button('从我的想法开始').count(),0);assert.deepEqual(await page.evaluate(()=>window.writes),[]);});
 await check('feature-on-idea-first-still-offers-original-course',async()=>{await open('new');await button('从我的想法开始').waitFor();await button('跟着邀请卡课程练习').waitFor();await button('从我的想法开始').click();assert.deepEqual(await page.evaluate(()=>window.nav.map(x=>x.route)),['#/learn/create']);assert.deepEqual(await page.evaluate(()=>window.writes),[]);});
 await check('existing-invitation-run-remains-original-resume',async()=>{await open('old');await page.waitForFunction(()=>window.nav.length>0);assert.equal(await page.evaluate(()=>window.nav.at(-1).route),'#/learn/run?id=old-invitation-run');assert.deepEqual(await page.evaluate(()=>window.writes),[]);});
 await check('offered-interview-navigates-only-after-confirmation-settles',async()=>{await open('offer');await button('这是我的想法，继续').click();await page.waitForFunction(()=>window.nav.length>0);const nav=await page.evaluate(()=>window.nav.at(-1));assert.deepEqual(nav,{route:'#/learn/create',dirty:false,receipt:true});assert.deepEqual(await page.evaluate(()=>window.writes),['/learners/child/entry/confirm']);});
 await check('declined-summary-can-start-without-fabricating-a-course-run',async()=>{await open('offer');await button('暂不采用，从简单提示开始').click();await page.waitForFunction(()=>window.nav.length>0);assert.equal(await page.evaluate(()=>window.nav.at(-1).route),'#/learn/create');assert.deepEqual(await page.evaluate(()=>window.writes),['/learners/child/entry/confirm']);});
 await check('old-catalog-outage-does-not-block-independent-creative-entry',async()=>{await open('catalog-down');await page.getByText('邀请卡课程列表暂时没有读到，可以先从自己的想法开始。').waitFor();assert.equal(await button('从我的想法开始').isDisabled(),false);await button('从我的想法开始').click();assert.equal(await page.evaluate(()=>window.nav.at(-1).route),'#/learn/create');});
 await check('no-component-errors',async()=>assert.deepEqual(errors,[]));
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({scope:'isolated entry fixture',results},null,2));console.log(JSON.stringify({passed:results.length,out}));
}finally{await browser?.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
