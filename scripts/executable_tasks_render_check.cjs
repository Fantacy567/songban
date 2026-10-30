/* CORE-02 DOM-free render check of static/core.js task cards. Not a browser test: no layout, clicks or clipboard. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const el={innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){},contains:()=>false,prepend(){},append(){}};
const context=vm.createContext({document:{querySelector:()=>el},localStorage:{getItem:()=>'',setItem(){},removeItem(){}},setInterval(){},setTimeout(){},clearTimeout(){},console,crypto:{randomUUID:()=>'x'},location:{origin:'http://127.0.0.1'},window:{}});
try{vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/core.js'),'utf8'),context);}catch{/* login screen wiring needs a real DOM; card renderers are already defined */}
const hostile='<img src=x onerror="alert(1)"></textarea><script>alert(2)</script>';
const base={key:'T1',title:'验证姓名接口',owner_id:'a',acceptance:'正常与空输入各一次',depends_on:['T0'],source_ids:['direction','note-1']};
const cases={
 full:{...base,execution:{tool:'终端',steps:['按团队已有启动说明启动','发正常姓名请求','发空姓名请求','保存实际返回'],ai_prompt:'目标：验证姓名接口。\n边界：接口地址缺失先问队长。',deliverable:'两次请求的实际返回',help_hint:'贴出报错原文，向队长求助'}},
 noAi:{...base,key:'T2',execution:{tool:'浏览器',steps:['录一段30秒演示'],ai_prompt:'',deliverable:'一段录屏',help_hint:'说明卡在哪一步'}},
 legacy:{...base,key:'T3'},
 hostile:{...base,key:'T4',title:hostile,acceptance:hostile,execution:{tool:hostile,steps:[hostile],ai_prompt:hostile,deliverable:hostile,help_hint:hostile}},
};
vm.runInContext(`state.data={me:{id:'a',captain:true},members:[{id:'a',name:'甲'}],plan_version:1};`,context);
const render=(task,official)=>vm.runInContext('tasks(__list,__official)',Object.assign(context,{__list:[task],__official:official}));
const result={};
for(const official of [false,true]){
 const full=render(cases.full,official),noAi=render(cases.noAi,official),legacy=render(cases.legacy,official),bad=render(cases.hostile,official);
 assert.match(full,/<summary>照做说明 · 终端<\/summary>/);assert.equal((full.match(/<li class="wrap">/g)||[]).length,4);
 assert.match(full,/<textarea class="ai-prompt" readonly[^>]*>目标：验证姓名接口。\n边界：接口地址缺失先问队长。<\/textarea><button type="button" data-copy-prompt>/);
 for(const s of ['要交的成果：</strong>两次请求的实际返回','卡住时：</strong>贴出报错原文','检查方法：</strong>正常与空输入各一次','依据：direction、note-1','前置任务：T0'])assert(full.includes(s),s);
 assert(noAi.includes('不需要AI指令')&&!noAi.includes('<textarea'));
 assert(legacy.includes('<summary>旧任务尚无操作说明</summary>')&&!legacy.includes('<ol>')&&!legacy.includes('<textarea'));
 assert(!/<img|<script|<\/textarea><script/.test(bad),'hostile text rendered as markup');assert(bad.includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&lt;/textarea&gt;'));
 assert.equal((bad.match(/<textarea/g)||[]).length,1);assert.equal((bad.match(/<\/textarea>/g)||[]).length,1);
 result[official?'confirmed_task':'draft_task']={full_details:true,steps_ordered:4,prompt_in_readonly_textarea:true,no_ai_label:true,legacy_label:true,hostile_escaped:true};
}
/* Open-state retention across re-renders. Simulates <details> toggles with plain objects; still not a browser test. */
const run=src=>vm.runInContext(src,context);
const keepIds=html=>[...html.matchAll(/<details class="execution" data-keep="([^"]+)"( open)?>/g)].map(m=>({id:m[1].replace(/&#39;/g,"'").replace(/&quot;/g,'"').replace(/&amp;/g,'&'),open:Boolean(m[2])}));
const toggle=(id,open)=>{const fake={dataset:{keep:id},open:!open,addEventListener(type,fn){this.fn=fn;}};el.querySelectorAll=()=>[fake];run('bindKeepOpen()');fake.open=open;fake.fn();el.querySelectorAll=()=>[];};
const live=(task,official)=>{const html=render(task,official),ids=keepIds(html);assert.equal(ids.length,1);return {html,...ids[0]};};
run(`state.team='team-a';state.data={me:{id:'a',captain:true},members:[{id:'a',name:'甲'}],plan_version:1,revision:10,proposal:{id:'p1'},reports:[]};`);
const keep={};
let card=live(cases.full,true);assert(!card.open,'closed by default');
toggle(card.id,true);
run(`state.data={...state.data,revision:11,reports:[{id:'r-unrelated'}]};`);
card=live({...cases.full,status:'in_progress'},true);assert(card.open,'unrelated revision keeps it open');assert(card.html.includes('进行中'),'latest status shown');keep.unrelated_revision_keeps_open=true;
toggle(card.id,false);run(`state.data={...state.data,revision:12};`);
assert(!live(cases.full,true).open,'explicit collapse survives refresh');keep.user_collapse_respected=true;
toggle(card.id,true);
const changed={...cases.full,execution:{...cases.full.execution,steps:['新步骤：先向队长确认接口地址']}};
card=live(changed,true);assert(!card.open,'changed instructions start closed');assert(card.html.includes('新步骤：先向队长确认接口地址')&&!card.html.includes('发空姓名请求'),'new text rendered, old text gone');keep.changed_instructions_reset=true;keep.new_text_rendered=true;
toggle(live(cases.full,true).id,true);run(`state.data={...state.data,plan_version:2};`);
assert(!live(cases.full,true).open,'new plan version starts closed');keep.new_plan_version_reset=true;
const draft=live(cases.full,false);assert(!draft.open,'draft does not inherit confirmed-task state');toggle(draft.id,true);assert(live(cases.full,false).open);
run(`state.data={...state.data,proposal:{id:'p2'}};`);assert(!live(cases.full,false).open,'new draft starts closed');keep.new_draft_reset=true;
toggle(live(cases.full,true).id,true);run(`state.team='team-b';`);assert(!live(cases.full,true).open,'other team starts closed');
run(`state.team='team-a';`);assert(!live(cases.full,true).open,'switching back does not resurrect old state');keep.team_switch_reset=true;
toggle(live(cases.full,true).id,true);el.querySelectorAll=()=>[];run('bindKeepOpen()');assert.equal(run('opened.ids.size'),0,'ids for tasks no longer shown are dropped');keep.stale_ids_pruned=true;
const bad=render(cases.hostile,true);assert(!/<img|<script/.test(bad)&&/data-keep="[^"<>]*"/.test(bad),'hostile key escaped in data-keep');keep.hostile_still_escaped=true;
/* Real refresh() with a stubbed network. overview()/libraryView() and render() are counted separately, so a manual render cannot pass for a poll redraw. */
const guard={},draws=[],calls=[];let renders=0,serve;
context.__api=(...a)=>{calls.push(a);return serve(...a);};
context.__draw=page=>draws.push({page,team:run('state.team'),revision:run('state.data.revision')});
context.__render=()=>renders++;
run(`__realApi=api;state.token='t';state.team='team-a';state.page='overview';state.busy=false;state.pending=false;api=(...a)=>__api(...a);overview=()=>__draw('overview');libraryView=()=>__draw('library');render=()=>__render();`);
const focus=on=>{el.contains=()=>on;context.document.activeElement={matches:s=>on&&s==='input,textarea,select'};};
let dirty=false;el.querySelector=s=>s==='form[data-dirty=true]'&&dirty?{}:null;
const answer=rev=>{const d={...run('state.data'),revision:rev};serve=async()=>d;};
const slow=rev=>{const d={...run('state.data'),revision:rev};let release;serve=()=>new Promise(r=>release=()=>r(d));return ()=>release();};
const poll=()=>run('refresh()');
let finished=false;process.on('beforeExit',()=>{if(!finished){console.error('AssertionError: check stalled, an awaited request never settled');process.exitCode=1;}});
(async()=>{
 focus(true);answer(200);await poll();assert.equal(draws.length,0,'no redraw while the AI prompt box has focus');assert.equal(run('state.data.revision'),200,'sync itself keeps running');guard.no_redraw_while_focused=true;
 answer(201);await poll();assert.equal(draws.length,0,'second update while focused still waits');
 focus(false);await poll();assert.equal(draws.length,1,'same revision, focus gone: catch-up redraw');assert.equal(draws[0].revision,201,'catch-up uses the latest data only');guard.catch_up_on_same_revision=true;guard.latest_only=true;
 await poll();assert.equal(draws.length,1,'no repeated redraw once caught up');guard.no_duplicate_redraw=true;
 dirty=true;answer(202);await poll();assert.equal(draws.length,1,'dirty form protected');dirty=false;await poll();assert.equal(draws.at(-1).revision,202);assert.equal(draws.length,2);guard.dirty_form_catch_up=true;
 run('state.busy=true');answer(203);await poll();assert.equal(draws.length,2,'busy protected');run('state.busy=false');await poll();assert.equal(draws.at(-1).revision,203);guard.busy_catch_up=true;
 run(`state.page='library'`);focus(true);answer(204);await poll();assert.equal(draws.length,3,'library page protected too');focus(false);await poll();assert.deepEqual(draws.at(-1),{page:'library',team:'team-a',revision:204});guard.library_catch_up=true;
 run(`state.page='overview'`);focus(true);answer(205);await poll();assert.equal(run('state.pending'),true);
 let release=slow(206);let pending=poll();run(`state.team='team-b'`);release();await pending;
 assert.equal(run('state.data.revision'),205,'response for the old team is discarded');assert.equal(draws.length,4,'nothing drawn for the old team');
 focus(false);answer(1);await run('refresh(true)');assert.equal(renders,1,'team switch draws once via render()');assert.equal(run('state.pending'),false,'old pending redraw cleared');
 await poll();assert.equal(draws.length,4,'no leftover catch-up of old-team data');assert.match(calls.at(-1)[0],/teams\/team-b$/);guard.team_switch_no_old_data=true;
 release=slow(2);pending=poll();run(`state.token=''`);release();await pending;assert.equal(run('state.data.revision'),1,'response after logout is discarded');assert.equal(draws.length,4);
 const before=calls.length;await poll();assert.equal(calls.length,before,'no request after logout');guard.logout_no_old_data=true;
 assert(calls.every(a=>a.length===1),'polling only reads (GET), never writes');guard.polling_read_only=true;
 assert.equal(renders,1,'only the explicit force refresh used render()');guard.poll_path_never_full_render=true;
 /* R3: out-of-order responses inside one team context, still through the real refresh(). */
 const order={},inflight=[];serve=()=>new Promise(r=>inflight.push(r));
 const reply=(i,rev)=>{inflight[i]({...run('state.data'),revision:rev});return new Promise(r=>setTimeout(r,0));};
 const reset=()=>{inflight.length=0;};
 run(`state.token='t2';state.team='team-a';state.page='overview';state.busy=false;`);focus(false);
 answer(300);await run('refresh(true)');const r0=renders,d0=draws.length;serve=()=>new Promise(r=>inflight.push(r));reset();
 let a=poll(),b=poll();await reply(1,302);await b;assert.equal(run('state.data.revision'),302);await reply(0,301);await a;
 assert.equal(run('state.data.revision'),302,'earlier request answering late must not roll back');assert.deepEqual(draws.slice(d0).map(x=>x.revision),[302],'drawn once with 302, never 301');order.late_old_response_ignored=true;
 reset();focus(true);a=poll();b=poll();await reply(1,304);await b;await reply(0,303);await a;
 assert.equal(run('state.data.revision'),304,'protected: keep the newer of two out-of-order responses');assert.equal(draws.length,d0+1,'still no redraw while focused');assert.equal(run('state.pending'),true);
 focus(false);answer(304);await poll();assert.deepEqual(draws.at(-1),{page:'overview',team:'team-a',revision:304},'same-revision catch-up after blur');assert.equal(draws.length,d0+2);
 await poll();assert.equal(draws.length,d0+2,'no duplicate catch-up');order.protected_out_of_order_then_catch_up=true;
 answer(304);await run('refresh(true)');assert.equal(renders,r0+1,'same-revision force refresh still renders');assert.equal(run('state.data.revision'),304);order.same_revision_force_ok=true;
 serve=()=>new Promise(r=>inflight.push(r));reset();a=poll();answer(305);await run('refresh(true)');assert.equal(renders,r0+2);await reply(0,304);await a;
 assert.equal(run('state.data.revision'),305,'poll sent before a force refresh cannot overwrite it');assert.equal(draws.length,d0+2);order.force_beats_older_poll=true;
 serve=()=>new Promise(r=>inflight.push(r));reset();a=poll();run(`state.page='direction'`);answer(306);await run('refresh(true)');await reply(0,305);await a;
 assert.equal(run('state.data.revision'),306,'old request from previous page ignored');assert.equal(draws.length,d0+2);order.page_change_old_request_ignored=true;
 run(`state.page='overview'`);
 result.out_of_order=order;
 /* R3b: data revision must never go down inside one account+team, whichever request the server answered first. */
 const mono={},hold=()=>{reset();serve=()=>new Promise((ok,fail)=>inflight.push({ok,fail}));};
 const give=(i,rev)=>{inflight[i].ok({...run('state.data'),revision:rev});return new Promise(r=>setTimeout(r,0));};
 const fail=i=>{inflight[i].fail(new Error('旧请求失败'));return new Promise(r=>setTimeout(r,0));};
 const sync={textContent:'每 5 秒刷新'};el.querySelector=q=>q==='#sync-state'?sync:(q==='form[data-dirty=true]'&&dirty?{}:null);
 focus(false);let d1=draws.length;
 hold();a=poll();b=poll();await give(0,310);await a;await give(1,309);await b;
 assert.equal(run('state.data.revision'),310,'r1 answers 310 first, r2 answers 309 later: stays 310');assert.deepEqual(draws.slice(d1).map(x=>x.revision),[310],'drawn [310] only');mono.first_sent_higher_then_later_sent_lower=true;
 d1=draws.length;hold();a=poll();b=poll();await give(1,312);await b;await give(0,311);await a;
 assert.equal(run('state.data.revision'),312);assert.deepEqual(draws.slice(d1).map(x=>x.revision),[312]);mono.later_sent_higher_then_first_sent_lower=true;
 d1=draws.length;focus(true);hold();a=poll();b=poll();await give(0,314);await a;await give(1,313);await b;
 assert.equal(run('state.data.revision'),314,'protected, r1 high first');assert.equal(draws.length,d1);
 focus(false);answer(314);await poll();assert.deepEqual(draws.slice(d1).map(x=>x.revision),[314],'blur: same-revision catch-up');
 d1=draws.length;focus(true);hold();a=poll();b=poll();await give(1,316);await b;await give(0,315);await a;
 assert.equal(run('state.data.revision'),316,'protected, r2 high first');assert.equal(draws.length,d1);
 focus(false);answer(315);await poll();assert.equal(run('state.data.revision'),316,'stale read after blur is not adopted');assert.deepEqual(draws.slice(d1).map(x=>x.revision),[316],'catch-up still happens on that poll, with 316');
 answer(316);await poll();assert.equal(draws.length,d1+1,'no duplicate');mono.protected_both_orders_no_rollback=true;
 hold();a=poll();b=poll();const keepData=()=>run('state.data');await give(1,316);await b;const held=keepData();inflight[0].ok({...held,review_running:true});await new Promise(r=>setTimeout(r,0));await a;
 assert.equal(run('state.data.review_running'),held.review_running,'equal revision from an older request does not overwrite');mono.equal_revision_older_request_ignored=true;
 const rf=renders;run(`state.page='library'`);answer(300);await run('refresh(true)');assert.equal(renders,rf+1,'force still renders');assert.equal(run('state.data.revision'),316,'force answered with a lower revision renders the newer data held');run(`state.page='overview'`);
 answer(316);await run('refresh(true)');assert.equal(renders,rf+2);mono.force_same_or_lower_revision_ok=true;
 run(`state.token='t3'`);answer(1);await poll();assert.equal(run('state.data.revision'),1,'new login context is not compared with the old revision');
 run(`state.team='team-c'`);answer(2);await run('refresh(true)');assert.equal(run('state.data.revision'),2,'new team context is not compared either');run(`state.team='team-a'`);answer(5);await run('refresh(true)');assert.equal(run('state.data.revision'),5);mono.new_context_not_compared=true;
 hold();a=poll();b=poll();await give(1,6);await b;sync.textContent='已同步';await fail(0);await a;assert.equal(sync.textContent,'已同步','error of an older request after a newer success is ignored');
 hold();a=poll();run(`state.team='team-b'`);await fail(0);await a;assert.equal(sync.textContent,'已同步','error from the previous team is ignored');run(`state.team='team-a'`);mono.old_errors_ignored=true;
 let release401;context.fetch=()=>new Promise(r=>release401=()=>r({status:401,ok:false,json:async()=>({error:{message:'登录已过期'}})}));
 run(`state.token='old-token'`);const old=run(`__realApi('/api/core/me')`).catch(e=>e);run(`state.token='new-token'`);release401();await old;
 assert.equal(run('state.token'),'new-token','401 for the old token does not log out the new session');mono.old_401_ignored=true;run(`state.token='t3'`);
 result.monotonic=mono;
 /* R3c: real load(); identity is locked before /me, so a late /me (or its error) never lands in a newer session. */
 const ld={},tick=()=>new Promise(r=>setTimeout(r,0)),me=(id,...teams)=>({id,person:{name:id},teams:teams.map(t=>({id:t,name:t}))});
 const paths=from=>calls.slice(from).map(a=>a[0]);
 hold();let c0=calls.length,r0l=renders;run(`state.token='old-token';state.team='A';state.me=null;`);let L=run('load()');await tick();
 assert.deepEqual(paths(c0),['/api/core/me']);
 run(`state.token='new-token';state.team='B';state.me={id:'new-user',person:{name:'new-user'},teams:[{id:'B',name:'B'}]};`);
 inflight[0].ok(me('old-user','A'));await tick();await tick();
 assert.equal(run('state.me.id'),'new-user','late /me must not write the old user');assert.equal(run('state.team'),'B','late /me must not switch B back to A');
 assert.deepEqual(paths(c0),['/api/core/me'],'no follow-up team request with the new token');assert.equal(renders,r0l,'nothing rendered for the old load');await L;ld.late_me_ignored=true;
 hold();c0=calls.length;run(`state.token='old-token';state.team='A';`);L=run('load()').then(()=>'resolved',e=>'threw:'+e.message);await tick();run(`state.token='new-token';state.team='B';`);await fail(0);
 assert.equal(await L,'resolved','late /me error is swallowed, not shown in the new session');assert.equal(run('state.me.id'),'new-user');assert.deepEqual(paths(c0),['/api/core/me']);ld.late_me_error_ignored=true;
 hold();c0=calls.length;r0l=renders;run(`state.token='tok';state.team='A';state.me=null;`);const L1=run('load()');await tick();const L2=run('load()');await tick();
 inflight[1].ok(me('u-new','A','C'));await tick();assert.deepEqual(paths(c0),['/api/core/me','/api/core/me','/api/core/teams/A']);await give(2,7);await L2;
 assert.equal(run('state.me.id'),'u-new');assert.equal(run('state.data.revision'),7);assert.equal(renders,r0l+1);
 inflight[0].ok(me('u-old','A'));await tick();await tick();assert.equal(run('state.me.id'),'u-new','older load finishing later does not overwrite');assert.equal(calls.length,c0+3,'older load sends nothing more');assert.equal(renders,r0l+1);await L1;
 hold();c0=calls.length;const L3=run('load()');await tick();inflight[0].ok(me('u-new','A','C'));await tick();const L4=run('load()');await tick();
 inflight[2].ok(me('u-new','A','C'));await tick();await give(3,9);await L4;inflight[1].ok({...run('state.data'),revision:8});await L3;await tick();
 assert.equal(run('state.data.revision'),9,'older load team data arriving late is ignored');assert.equal(renders,r0l+2);ld.older_load_after_newer_ignored=true;
 hold();c0=calls.length;r0l=renders;run(`state.token='fresh';state.team='';state.me=null;state.data=null;state.dataCtx='';`);L=run('load()');await tick();
 inflight[0].ok(me('u1','T1','T2'));await tick();assert.deepEqual(paths(c0),['/api/core/me','/api/core/teams/T1'],'first login picks the first team');await give(1,1);await L;
 assert.equal(run('state.team'),'T1');assert.equal(run('state.me.id'),'u1');assert.equal(run('state.data.revision'),1);assert.equal(renders,r0l+1);
 hold();c0=calls.length;run(`state.team='T2';`);L=run('load()');await tick();inflight[0].ok(me('u1','T1','T2'));await tick();assert.deepEqual(paths(c0),['/api/core/me','/api/core/teams/T2'],'remembered team kept');await give(1,4);await L;assert.equal(run('state.team'),'T2');
 hold();c0=calls.length;run(`state.token='solo';state.team='';state.me=null;`);L=run('load()');await tick();inflight[0].ok(me('u2'));await L;assert.deepEqual(paths(c0),['/api/core/me']);assert.equal(run('state.data'),null);assert.equal(renders,r0l+3);ld.normal_first_login_ok=true;
 hold();run(`state.token='live';state.team='';state.me=null;`);L=run('load()').then(()=>'resolved',e=>'threw:'+e.message);await tick();await fail(0);assert.equal(await L,'threw:旧请求失败','error of the current load still surfaces');ld.current_error_still_shown=true;
 run(`state.token='t3';state.team='team-a';`);
 result.load_identity=ld;
 result.open_state=keep;result.refresh_guard=guard;finished=true;console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1);});
