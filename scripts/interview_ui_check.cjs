/* INTERVIEW-03 DOM-free logic check of static/core.js + static/interview.js.
   Not a browser test: no layout, real clicks, focus rings or CSS. A tiny fake DOM finds elements by id in the
   rendered HTML; fetch is a controllable substitute; responses are synthetic (protocol substitutes, not a model). */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),{webcrypto}=require('node:crypto');
const src=f=>fs.readFileSync(path.join(__dirname,'../static',f),'utf8');
const HOSTILE='<img src=x onerror="alert(1)"><script>alert(2)</script>';
const tick=()=>new Promise(r=>setImmediate(r));
async function settle(){for(let i=0;i<12;i++)await tick();}

function boot(stored={}){
  const store={...stored},sets=[],calls=[],pending=[],focus=[],toasts=[];let intervalFn=null,map=new Map(),tabs=new Map();
  const el=(id)=>({id,value:'',textContent:'',disabled:false,hidden:false,dataset:{},listeners:{},onclick:null,onchange:null,__inRoot:true,
    addEventListener(t,f){(this.listeners[t]=this.listeners[t]||[]).push(f);},
    fire(t,extra={}){const ev={type:t,target:this,preventDefault(){},...extra};if(t==='click'&&this.onclick)this.onclick(ev);if(t==='change'&&this.onchange)this.onchange(ev);for(const f of this.listeners[t]||[])f(ev);return settle();},
    focus(){focus.push(this.id);doc.activeElement=this;},select(){},querySelector:()=>null,querySelectorAll:()=>[],prepend(){},append(){},remove(){},setAttribute(){},matches:()=>false,contains:()=>false});
  let content=null;
  const makeContent=()=>{const c=el('content');let html='';Object.defineProperty(c,'innerHTML',{get:()=>html,set:v=>{html=v;for(const k of [...map.keys()])if(!rootHtml.includes(`id="${k}"`))map.delete(k);}});return c;};
  let rootHtml='';
  const root={addEventListener(){},contains:x=>Boolean(x&&x.__inRoot),
    get innerHTML(){return rootHtml;},set innerHTML(v){rootHtml=v;map=new Map();tabs=new Map();content=rootHtml.includes('id="content"')?makeContent():null;if(content)map.set('content',content);},
    querySelector(sel){const m=/^#([\w-]+)$/.exec(sel);if(!m)return null;const id=m[1];if(id==='content')return content;
      const html=rootHtml+(content?content.innerHTML:'');if(!html.includes(`id="${id}"`))return null;if(!map.has(id))map.set(id,el(id));return map.get(id);},
    querySelectorAll(sel){if(sel!=='[data-tab]')return [];return [...rootHtml.matchAll(/data-tab="(\w+)"/g)].map(m=>{if(!tabs.has(m[1])){const b=el('tab-'+m[1]);b.dataset.tab=m[1];tabs.set(m[1],b);}return tabs.get(m[1]);});}};
  const toastEl={textContent:'',hidden:true,set _t(v){}};
  const doc={activeElement:null,hidden:false,querySelector:s=>s==='#app'?root:s==='#toast'?toastEl:null,createElement:()=>el('created')};
  class FormData{constructor(f){this.f=f.__fields||{};}entries(){return Object.entries(this.f)[Symbol.iterator]();}}
  const ctx=vm.createContext({document:doc,FormData,console,crypto:webcrypto,location:{origin:'http://127.0.0.1'},window:{},navigator:{},Uint8Array,JSON,Map,Set,Promise,Error,Object,Array,Math,Date,Number,String,Boolean,
    localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{sets.push([k,String(v)]);store[k]=String(v);},removeItem:k=>{delete store[k];}},
    setInterval:f=>{intervalFn=f;},setTimeout:()=>0,clearTimeout(){},
    fetch:(p,o={})=>new Promise(res=>{const c={path:p,method:o.method||'GET',body:o.body?JSON.parse(o.body):null,auth:(o.headers||{}).Authorization||'',res};calls.push(c);pending.push(c);})});
  vm.runInContext(src('core.js'),ctx);vm.runInContext(src('interview.js'),ctx);
  const run=s=>vm.runInContext(s,ctx);
  const $=id=>root.querySelector('#'+id);
  const html=()=>rootHtml+(content?content.innerHTML:'');
  const find=(p,method)=>[...pending].reverse().find(c=>c.path===p&&(!method||c.method===method));
  const reply=async(c,status,body)=>{assert(c,'expected a pending request');pending.splice(pending.indexOf(c),1);c.res({ok:status<400,status,json:async()=>body});await settle();};
  const count=(p,method)=>calls.filter(c=>c.path===p&&(!method||c.method===method)).length;
  const tab=name=>{tabs.get(name).onclick();return settle();};
  return {run,$,html,find,reply,count,tab,calls,pending,sets,store,focus,content:()=>content,poll:()=>intervalFn&&intervalFn()};
}
const IV='/api/core/interview';
const msg=(n,role,text,extra={})=>({id:(role==='assistant'?'q':'u')+n,role,text,...extra});
const asking=(version,list,current)=>({status:'asking',version,asked_count:list.filter(m=>m.role==='assistant').length,max_questions:30,age_band:'undisclosed',stage:'job_seeking',messages:list,current_question:current,profile:null,source:{kind:'model',model:'substitute'},replayed:false});
const err=(code,message,details)=>({error:{code,message,...(details?{details}:{})}});
const result={};

(async()=>{
  /* 1. registration → intro → start → answers → finish → draft → later → back → confirm */
  {
    const t=boot();
    assert(t.html().includes('回到团队现场'));
    await t.$('toggle-auth').onclick();
    let h=t.html();
    assert(!/name="profile"|name="skills"|id="profile"|id="skills"/.test(h),'register form no longer asks for profile/skills');
    assert(h.includes('不用现在填写画像'));
    for(const id of ['phone','password','confirm-password','code','name'])assert(h.includes(`id="${id}"`),id);
    const form=t.$('auth-form');form.__fields={phone:'13800000001',password:'test-only-pass',code:'123456',name:'合成甲'};t.$('confirm-password').value='test-only-pass';
    await form.fire('submit');await settle();
    const reg=t.find('/api/studio/register','POST');
    assert.deepEqual(reg.body,{phone:'13800000001',password:'test-only-pass',code:'123456',name:'合成甲',onboarding:true});
    await t.reply(reg,200,{token:'tok-a',returning:false});
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[]});
    assert.equal(t.run('state.page'),'interview');
    assert.equal(t.count(IV+'/start'),0,'registration does not start the interview');
    await t.reply(t.find(IV),200,{status:'not_started'});
    h=t.html();
    for(const s of ['围绕你想做的事聊聊，最多30问，可提前结束；不是性格或天赋测验；完整对话默认仅本人可见','开始访谈','先跳过，去团队','不透露','就业探索','在职','大学'])assert(h.includes(s),s);
    assert.equal(t.count(IV+'/start'),0,'intro alone calls no model');
    result.register={no_profile_fields:true,onboarding_flag_sent:true,lands_on_intro:true,no_auto_start:true};

    const stage=t.$('iv-stage');stage.value='job_seeking';await stage.fire('change');
    const startForm=t.$('iv-start');await startForm.fire('submit');await startForm.fire('submit');
    assert.equal(t.count(IV+'/start'),1,'double start sends once');
    assert.deepEqual(t.find(IV+'/start').body,{age_band:'undisclosed',stage:'job_seeking'});
    const q1=msg(1,'assistant',HOSTILE+'你想做什么？',{number:1});
    await t.reply(t.find(IV+'/start'),200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    h=t.html();assert(h.includes('第 1 / 30 问'));assert(!/<img|<script/.test(h),'question escaped');assert(h.includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'));

    const text=t.$('iv-text');text.value='想做一个'+HOSTILE+'小游戏';await text.fire('input');
    let ans=t.$('iv-answer');await ans.fire('submit');await ans.fire('submit');
    assert.equal(t.count(IV+'/answer'),1,'double submit sends once');
    const a1=t.find(IV+'/answer');assert.equal(a1.body.version,1);assert.equal(a1.body.question_id,'q1');assert.match(a1.body.request_id,/^iv-[0-9a-f]{24}$/);assert.equal(a1.body.text,'想做一个'+HOSTILE+'小游戏');
    assert(t.html().includes('正在提交…')&&t.html().includes('<textarea id="iv-text" disabled'));
    await t.reply(a1,503,err('model_unavailable','连不上访谈模型；已有记录不变，可以重试。',{retryable:true,current_version:1}));
    h=t.html();assert(h.includes('连不上访谈模型')&&h.includes('不会重复计数'));assert(h.includes('想做一个&lt;img'),'input kept after failure');assert(h.includes('第 1 / 30 问'),'state kept');
    ans=t.$('iv-answer');await ans.fire('submit');const a2=t.find(IV+'/answer');assert.equal(a2.body.request_id,a1.body.request_id,'same answer retried with same request_id');
    await t.reply(a2,504,err('model_timeout','访谈模型超时；已有记录不变，可以重试。',{retryable:true,current_version:1}));
    const t2=t.$('iv-text');t2.value='改成：想做一个记账工具';await t2.fire('input');ans=t.$('iv-answer');await ans.fire('submit');
    const a3=t.find(IV+'/answer');assert.notEqual(a3.body.request_id,a1.body.request_id,'changed answer gets a new request_id');
    const u2=msg(2,'user','改成：想做一个记账工具'),q3=msg(3,'assistant','你会先让AI做哪一步？',{number:2});
    await t.reply(a3,200,asking(2,[q1,u2,q3],{id:'q3',text:q3.text,number:2}));
    h=t.html();assert(h.includes('第 2 / 30 问'));assert(h.includes('<textarea id="iv-text" >')&&h.includes('</textarea>')&&!h.includes('改成：想做一个记账工具</textarea>'),'input cleared after success');
    result.answer={double_submit_once:true,failure_keeps_input_and_state:true,retry_same_request_id:true,changed_answer_new_id:true};

    const t3=t.$('iv-text');t3.value='先让它写页面';await t3.fire('input');ans=t.$('iv-answer');await ans.fire('submit');
    const a4=t.find(IV+'/answer');assert.equal(a4.body.question_id,'q3');
    await t.reply(a4,409,err('version_conflict','访谈已经更新，请刷新后再操作。',{status:'asking',current_version:3}));
    assert.equal(t.count(IV+'/answer'),4,'409 does not resend');
    const u4=msg(4,'user','另一个标签页的回答'),q5=msg(5,'assistant','做完第一步你怎么检查？',{number:3});
    await t.reply(t.find(IV,'GET'),200,asking(3,[q1,u2,q3,u4,q5],{id:'q5',text:q5.text,number:3}));
    h=t.html();assert(h.includes('没有提交给新问题')&&h.includes('第 3 / 30 问'));assert(h.includes('>先让它写页面</textarea>'),'old answer stays in the box, not sent');
    assert.equal(t.count(IV+'/answer'),4,'nothing sent to the new question automatically');
    ans=t.$('iv-answer');await ans.fire('submit');const a5=t.find(IV+'/answer');
    assert.equal(a5.body.question_id,'q5');assert.equal(a5.body.version,3);assert.notEqual(a5.body.request_id,a4.body.request_id);
    await t.reply(a5,409,err('interview_busy','上一次操作还在处理中，请稍后刷新。',{retryable:true,current_version:3}));
    assert.equal(t.count(IV,'GET'),2,'busy does not reload');assert(t.html().includes('还在处理中'));
    ans=t.$('iv-answer');await ans.fire('submit');const a6=t.find(IV+'/answer');assert.equal(a6.body.request_id,a5.body.request_id);
    const u6=msg(6,'user','先让它写页面'),q7=msg(7,'assistant','你能花多少时间？',{number:4});
    const s4=asking(4,[q1,u2,q3,u4,q5,u6,q7],{id:'q7',text:q7.text,number:4});
    await t.reply(a6,200,s4);
    result.conflict={reload_on_409:true,no_silent_resend:true,new_question_new_id:true,busy_keeps_id:true};

    const before=t.count(IV+'/answer');
    let box=t.$('iv-text');box.value='   ';await box.fire('input');await t.$('iv-answer').fire('submit');
    assert(t.html().includes('回答是空的'));box=t.$('iv-text');box.value='长'.repeat(1001);await box.fire('input');await t.$('iv-answer').fire('submit');
    assert(t.html().includes('回答最多1000字，现在1001字'));
    assert.equal(t.count(IV+'/answer'),before,'empty/overlong not sent');
    box=t.$('iv-text');box.value='';await box.fire('input');
    result.input_checks={empty_visible:true,overlong_visible:true,not_sent:true};

    await t.$('iv-end').fire('click');assert(t.html().includes('确定结束'));assert.equal(t.count(IV+'/finish'),0,'first click only asks');
    await t.$('iv-end-yes').fire('click');const f=t.find(IV+'/finish');assert.equal(f.body.version,4);assert.match(f.body.request_id,/^iv-/);
    const draft={interests:[{text:'做小游戏'+HOSTILE,basis:'self_reported',evidence:['u2']}],goals:[{text:'做出能演示的作品',basis:'inferred',evidence:['u6']}],experiences:[],possible_strengths:[],roles_to_try:[],help_needed:[],time_available:null,next_practice:[],conflicts:[{text:'先说游戏后说记账',evidence:['u2','u4']}],unknowns:['可投入时间']};
    const pend={...s4,status:'pending_confirmation',version:5,current_question:null,profile:{status:'pending_confirmation',draft,missing_fields:['experiences','time_available'],reason:'user_finished',model:'substitute',confirmed_at:null}};
    await t.reply(f,200,pend);
    h=t.html();
    for(const s of ['画像草稿 · 等你确认','仅供本次协作参考，尚未证明实际能力','兴趣','想做成的事','本人自述','模型推测，待你核对','依据：你的第1个回答「改成：想做一个记账工具」','依据：你的第3个回答「先让它写页面」','前后说法不一致的地方','还不了解的方面','可投入时间','这次没有聊到：已有经历、可投入时间','你提前结束了访谈','确认这份画像','暂不确认，保留草稿'])assert(h.includes(s),s);
    assert(!/<img|<script/.test(h),'draft escaped');assert(!h.includes('purpose'));
    assert.equal(t.count(IV+'/confirm'),0,'no automatic confirm');
    result.draft={chinese_fields:true,basis_labels:true,evidence_to_own_answers:true,unknowns_conflicts_missing:true,disclaimer:true,no_auto_confirm:true};

    await t.$('iv-later').fire('click');await settle();
    assert.equal(t.run('state.page'),'overview');assert(t.html().includes('先把团队连起来'));assert.equal(t.count(IV+'/confirm'),0);
    assert.equal(t.run('iv.data.status'),'pending_confirmation','draft kept in memory too');
    await t.tab('interview');assert(t.html().includes('画像草稿 · 等你确认'),'cached draft shown while reloading');
    await t.reply(t.find(IV,'GET'),200,pend);assert(t.html().includes('确认这份画像'));
    const c=t.$('iv-confirm');await c.fire('click');await c.fire('click');assert.equal(t.count(IV+'/confirm'),1,'confirm once');
    const cf=t.find(IV+'/confirm');assert.equal(cf.body.version,5);
    await t.reply(cf,200,{...pend,status:'confirmed',version:6,profile:{...pend.profile,status:'confirmed',confirmed_at:'2026-10-30T02:00:00+00:00'}});
    h=t.html();assert(h.includes('已确认的个人画像')&&h.includes('回到团队')&&!h.includes('id="iv-confirm"'));
    const modelCalls=t.count(IV+'/start')+t.count(IV+'/answer')+t.count(IV+'/finish');
    await t.tab('interview');await t.reply(t.find(IV,'GET'),200,{...pend,status:'confirmed',version:6,profile:{...pend.profile,status:'confirmed',confirmed_at:'2026-10-30T02:00:00+00:00'}});
    assert.equal(t.count(IV+'/start')+t.count(IV+'/answer')+t.count(IV+'/finish'),modelCalls,'confirmed page triggers no model endpoint');
    result.confirm={later_keeps_draft:true,explicit_confirm_once:true,confirmed_view_no_model:true};

    const keys=new Set(t.sets.map(([k])=>k));assert.deepEqual([...keys].sort(),['studio-squad','studio-token']);
    for(const [,v] of t.sets)assert(!/小游戏|记账|先让它写页面|做出能演示/.test(v),'no interview text in localStorage');
    result.storage={only_token_and_team_keys:true};
  }
  /* 2. logout while an answer is in flight */
  {
    const t=boot({'studio-token':'tok-a'});
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[]});
    await t.tab('interview');const q1=msg(1,'assistant','甲的问题？',{number:1});
    await t.reply(t.find(IV),200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    const box=t.$('iv-text');box.value='甲的私人回答';await box.fire('input');await t.$('iv-answer').fire('submit');
    const a=t.find(IV+'/answer');await t.$('logout').onclick();await settle();
    assert(t.html().includes('回到团队现场'));
    await t.reply(a,200,asking(2,[q1,msg(2,'user','甲的私人回答'),msg(3,'assistant','甲的下一问？',{number:2})],{id:'q3',text:'甲的下一问？',number:2}));
    assert(!t.html().includes('甲的'),'late answer not drawn after logout');assert.equal(t.run('iv.data'),null);assert.equal(t.run('iv.text'),'');
    result.logout={late_answer_dropped:true,memory_cleared:true};
  }
  /* 3. account switch: A's late GET must not draw into B */
  {
    const t=boot({'studio-token':'tok-a'});
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[]});
    await t.tab('interview');const getA=t.find(IV);assert.equal(getA.auth,'Bearer tok-a');
    await t.$('logout').onclick();
    const form=t.$('auth-form');form.__fields={phone:'13800000002',password:'test-only-pass'};await form.fire('submit');
    await t.reply(t.find('/api/studio/login','POST'),200,{token:'tok-b'});
    await t.reply(t.find('/api/core/me'),200,{person:{id:'b',name:'合成乙'},teams:[]});
    const getB=t.find(IV);assert.equal(getB.auth,'Bearer tok-b');
    await t.reply(getA,200,asking(1,[msg(1,'assistant','甲的秘密问题？',{number:1})],{id:'q1',text:'甲的秘密问题？',number:1}));
    assert(!t.html().includes('甲的秘密问题'),'A response ignored for B');
    await t.reply(getB,200,{status:'not_started'});assert(t.html().includes('开始访谈'));assert.equal(t.run('iv.owner'),'tok-b');
    result.account_switch={old_get_dropped:true,new_owner:true};
  }
  /* 4. navigation away and stale GET order */
  {
    const t=boot({'studio-token':'tok-a'});
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[]});
    await t.tab('interview');const q1=msg(1,'assistant','第一问？',{number:1});
    await t.reply(t.find(IV),200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    const box=t.$('iv-text');box.value='离开前的回答';await box.fire('input');await t.$('iv-answer').fire('submit');
    const a=t.find(IV+'/answer');await t.$('iv-leave').fire('click');await settle();
    assert(t.html().includes('先把团队连起来'));
    await t.reply(a,200,asking(2,[q1,msg(2,'user','离开前的回答'),msg(3,'assistant','后来的问题？',{number:2})],{id:'q3',text:'后来的问题？',number:2}));
    assert(t.html().includes('先把团队连起来')&&!t.html().includes('后来的问题'),'late answer does not redraw another page');
    await t.tab('interview');const g1=t.find(IV);await t.tab('overview');await settle();await t.tab('interview');const g2=t.find(IV);
    assert.notEqual(g1,g2);
    await t.reply(g2,200,asking(2,[q1,msg(2,'user','离开前的回答'),msg(3,'assistant','最新的问题？',{number:2})],{id:'q3',text:'最新的问题？',number:2}));
    await t.reply(g1,200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    assert(t.html().includes('最新的问题')&&t.html().includes('第 2 / 30 问'),'older GET does not roll back');
    const box2=t.$('iv-text');box2.value='再离开一次';await box2.fire('input');await t.$('iv-answer').fire('submit');
    const late=t.find(IV+'/answer');await t.$('iv-leave').fire('click');const reads=t.count(IV,'GET');
    await t.reply(late,409,err('version_conflict','访谈已经更新，请刷新后再操作。',{status:'asking',current_version:3}));
    assert.equal(t.count(IV,'GET'),reads,'late 409 after leaving does not reload in the background');assert(t.html().includes('先把团队连起来'));
    result.navigation={late_answer_not_redrawn:true,older_get_ignored:true,late_conflict_no_background_reload:true};
  }
  /* 4a. R1: team-switch "＋ 创建或加入团队" while interview requests are in flight (page stays 'interview') */
  {
    const t=boot({'studio-token':'tok-a'});
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[]});
    const q1=msg(1,'assistant','想做什么？',{number:1}),u2=msg(2,'user','做游戏'),q3=msg(3,'assistant','想怎么玩？',{number:2});
    await t.tab('interview');await t.reply(t.find(IV),200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    const toNew=async()=>{const s=t.$('team-switch');s.value='__new';await s.fire('change');assert(t.html().includes('id="create-team"'),'create-team shown');assert.equal(t.run('state.page'),'interview');};
    let box=t.$('iv-text');box.value='做游戏';await box.fire('input');await t.$('iv-answer').fire('submit');
    const late=t.find(IV+'/answer');await toNew();let reads=t.count(IV,'GET');
    await t.reply(late,200,asking(2,[q1,u2,q3],{id:'q3',text:q3.text,number:2}));
    assert(t.html().includes('id="create-team"')&&!t.html().includes('id="iv-view"'),'late success does not overwrite create-team');
    assert.equal(t.count(IV,'GET'),reads,'no background request after late success');
    assert.equal(t.run('iv.data.version'),2,'saved progress kept in memory');assert.equal(t.run('iv.text'),'','accepted answer not left in the box');
    await t.tab('interview');assert.equal(t.count(IV,'GET'),reads+1,'returning reads the latest state');
    await t.reply(t.find(IV),200,asking(2,[q1,u2,q3],{id:'q3',text:q3.text,number:2}));
    assert(t.html().includes('第 2 / 30 问')&&t.html().includes('<textarea id="iv-text" >'),'latest question, empty box');
    box=t.$('iv-text');box.value='想做闯关';await box.fire('input');await t.$('iv-answer').fire('submit');
    const late409=t.find(IV+'/answer');await toNew();reads=t.count(IV,'GET');
    await t.reply(late409,409,err('version_conflict','访谈已经更新，请刷新后再操作。',{status:'asking',current_version:3}));
    assert(t.html().includes('id="create-team"')&&!t.html().includes('访谈已经更新'),'late 409 does not overwrite create-team');
    assert.equal(t.count(IV,'GET'),reads,'late 409 does not reload in the background');
    assert.equal(t.count(IV+'/answer'),2,'late 409 does not resend');assert.equal(t.run('iv.text'),'想做闯关','unsent answer kept for later');
    await t.tab('interview');const g=t.find(IV);await toNew();
    const q5=msg(5,'assistant','想先做哪一关？',{number:3}),latest=asking(3,[q1,u2,q3,msg(4,'user','别处的回答'),q5],{id:'q5',text:q5.text,number:3});
    await t.reply(g,200,latest);assert(t.html().includes('id="create-team"'),'late GET does not overwrite create-team');
    await t.tab('interview');await t.reply(t.find(IV),200,latest);
    assert(t.html().includes('第 3 / 30 问')&&t.html().includes('>想做闯关</textarea>'),'back on interview: latest state, unsent text still there');
    assert.equal(t.count(IV+'/answer'),2,'nothing was sent to the new question');
    result.team_new_page={late_success_no_overwrite:true,late_success_progress_kept:true,late_409_no_overwrite_no_reload:true,late_get_no_overwrite:true,return_reads_latest:true};
  }
  /* 4b. session expires (401 on a team poll) while an answer is in flight */
  {
    const t=boot({'studio-token':'tok-a','studio-squad':'t1'});t.run("state.page='interview'");
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[{id:'t1',name:'合成队'}]});
    await t.reply(t.find('/api/core/teams/t1'),200,{revision:1,proposal:null,review_running:false,last_error:null,members:[],me:{id:'a'}});
    const q1=msg(1,'assistant','过期前的问题？',{number:1});await t.reply(t.find(IV),200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    const box=t.$('iv-text');box.value='过期前的回答';await box.fire('input');await t.$('iv-answer').fire('submit');const a=t.find(IV+'/answer');
    t.poll();await settle();await t.reply(t.find('/api/core/teams/t1'),401,err('unauthorized','登录已失效，请重新登录。'));
    assert(t.html().includes('回到团队现场'),'401 shows login');
    await t.reply(a,200,asking(2,[q1,msg(2,'user','过期前的回答'),msg(3,'assistant','过期后的问题？',{number:2})],{id:'q3',text:'过期后的问题？',number:2}));
    assert.equal(t.run('iv.data.version'),1,'response for an expired session is not adopted');assert(!t.html().includes('过期后的问题'));
    result.session_expiry={late_answer_not_adopted:true};
  }
  /* 5. team polling while typing; team switch keeps typed text */
  {
    const t=boot({'studio-token':'tok-a','studio-squad':'t1'});t.run("state.page='interview'");
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[{id:'t1',name:'合成队'}]});
    await t.reply(t.find('/api/core/teams/t1'),200,{revision:1,proposal:null,review_running:false,last_error:null,members:[],me:{id:'a'}});
    await t.tab('interview');assert.equal(t.count('/api/core/teams/t1'),1,'interview tab does not refresh team');
    const q1=msg(1,'assistant','第一问？',{number:1});await t.reply(t.find(IV),200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    const box=t.$('iv-text');box.value='正在输入的回答';await box.fire('input');box.focus();
    const content=t.content(),before=content.innerHTML,focusCount=t.focus.length;
    t.poll();await settle();await t.reply(t.find('/api/core/teams/t1'),200,{revision:2,proposal:{id:'p'},review_running:true,last_error:null,members:[],me:{id:'a'}});
    assert.equal(t.content(),content,'content node not replaced');assert.equal(content.innerHTML,before,'interview not redrawn by poll');
    assert.equal(t.run('state.page'),'interview');assert.equal(t.$('iv-text'),box,'same textarea');assert.equal(t.focus.length,focusCount,'poll does not move focus');
    t.run('refresh(true)');await settle();await t.reply(t.find('/api/core/teams/t1'),200,{revision:3,proposal:null,review_running:false,last_error:null,members:[],me:{id:'a'}});
    await t.reply(t.find(IV),200,asking(1,[q1],{id:'q1',text:q1.text,number:1}));
    assert(t.html().includes('>正在输入的回答</textarea>'),'forced team redraw keeps typed answer');
    result.polling={no_redraw:true,no_page_change:true,no_focus_steal:true,typed_text_survives_forced_render:true};
  }
  /* 6. 30th question → draft only; 503 on start keeps intro */
  {
    const t=boot({'studio-token':'tok-a'});
    await t.reply(t.find('/api/core/me'),200,{person:{id:'a',name:'合成甲'},teams:[]});
    await t.tab('interview');await t.reply(t.find(IV),200,{status:'not_started'});
    await t.$('iv-start').fire('submit');await t.reply(t.find(IV+'/start'),503,err('model_not_configured','访谈模型尚未配置，本次没有生成问题；已有记录不变，配置后可以重试。',{retryable:true,current_version:null}));
    assert(t.html().includes('访谈模型尚未配置')&&t.html().includes('开始访谈'),'503 keeps intro with message');
    const list=[];for(let i=1;i<=30;i++){list.push(msg(2*i-1,'assistant',`问题${i}？`,{number:i}));if(i<30)list.push(msg(2*i,'user',`回答${i}`));}
    await t.$('iv-start').fire('submit');await t.reply(t.find(IV+'/start'),200,asking(30,list,{id:'q59',text:'问题30？',number:30}));
    assert(t.html().includes('第 30 / 30 问'));
    const box=t.$('iv-text');box.value='最后一个回答';await box.fire('input');await t.$('iv-answer').fire('submit');
    const done={...asking(31,[...list,msg(60,'user','最后一个回答')],null),status:'pending_confirmation',current_question:null,profile:{status:'pending_confirmation',draft:{interests:[],goals:[],experiences:[],possible_strengths:[],roles_to_try:[],help_needed:[],time_available:null,next_practice:[],conflicts:[],unknowns:[]},missing_fields:[],reason:'limit_reached',model:'substitute',confirmed_at:null}};
    await t.reply(t.find(IV+'/answer'),200,done);
    assert(t.html().includes('已经问满上限')&&!t.html().includes('第 31')&&!t.html().includes('id="iv-text"'));
    result.limits={start_503_visible:true,thirty_then_draft_only:true};
  }
  console.log(JSON.stringify(result,null,1));
})().catch(e=>{console.error(e);process.exit(1);});
process.on('beforeExit',()=>{if(!Object.keys(result).includes('limits')){console.error('stalled: a scenario never finished');process.exit(1);}});
