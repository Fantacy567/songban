'use strict';
const journeyRoutes={interview:'interview',contest:'contest',contest_materials:'contestMaterials',team:'team',ideas:'discussion',direction:'direction',division:'division',work:'myTasks',delivery:'delivery',review:'recap'};
const journeyNames={interview:'认识自己',contest:'确认比赛',contest_materials:'导入赛事资料',team:'组队',ideas:'讨论选题',direction:'确认方向',division:'协调分工',work:'执行任务',delivery:'正式提交',review:'赛后复盘'};
function gateJourney(){
 if(typeof wantsLearning==='function'&&wantsLearning()&&['interview','onboarding','login'].includes(state.page))return;
 const flow=state.flow;if(!flow?.strict||!state.me)return;
 const stage=flow.stage,order=Object.keys(journeyRoutes),rank=order.indexOf(stage);
 const route={interview:0,contest:1,contestMaterials:2,team:3,discussion:4,ideaLibrary:4,direction:5,division:6,myTasks:7,teamTasks:7,overview:7,delivery:8,recap:9,workbench:7,library:7};
 if(rank<2){state.page=journeyRoutes[stage];return;}
 if(['login','events','event'].includes(state.page)){state.page=journeyRoutes[stage];return;}
 if(route[state.page]>rank)state.page=journeyRoutes[stage];
 if(stage==='review'&&['myTasks','teamTasks','direction','division','overview','workbench'].includes(state.page))state.page='recap';
}
function journeyChrome(){
 if(typeof wantsLearning==='function'&&wantsLearning()&&state.page==='interview')return;
 if(!state.flow?.strict||!state.me)return;
 const f=state.flow,main=$('#main-content'),tabs=$('.practice-tabs');
 if(tabs)tabs.innerHTML=`<a href="#/${f.route}" aria-current="step">现在：${esc(journeyNames[f.stage])}</a><details class="journey-history"><summary>查看已完成环节</summary>${Object.keys(journeyRoutes).slice(0,Object.keys(journeyRoutes).indexOf(f.stage)).map(k=>`<a href="#/${k}">${esc(journeyNames[k])}</a>`).join('')}</details>`;
 if(window.SONGBAN_DEMO&&main){const banner=document.createElement('div');banner.className='notice demo-notice';banner.innerHTML='演示模式 · 虚构比赛与人物 · AI结果使用预置样例 <button id="demo-peer">模拟队友完成当前环节</button> <button id="demo-reset">重新演示</button><p id="demo-note"></p>';main.prepend(banner);if(state.demoWorking)$('#demo-peer').disabled=true;$('#demo-reset').onclick=()=>{sessionStorage.removeItem('songban-demo-session');identityStorage.removeItem('studio-token');identityStorage.removeItem('studio-squad');location.href=(window.SONGBAN_DEMO_BASE||'')+'/';};$('#demo-peer').onclick=async()=>{const button=$('#demo-peer');state.demoWorking=true;state.busy=true;button.disabled=true;try{await api('/api/demo/peer',{team_id:state.team});await load();render();toast('模拟队友已配合，请继续当前步骤。');}catch(e){$('#demo-note').textContent=e.message;}finally{state.demoWorking=false;state.busy=false;const current=$('#demo-peer');if(current)current.disabled=false;}};}
}
async function interviewPage(){
 const learning=typeof wantsLearning==='function'&&wantsLearning();
 const host=$('#content');host.innerHTML=head('你的起点','先认识一下你。',learning?'通常聊 5～6 题，最多 8 题。确认后，和松伴开始第一个小作品。':'通常聊 5～6 题，最多 8 题。随时可以先看总结，确认后选择比赛。');
 try{const d=await api('/api/core/interview');if(!host.isConnected)return;
 if(d.status==='not_started'){host.insertAdjacentHTML('beforeend','<section class="card"><p>聊聊想做什么、会做什么，以及这次能投入的时间。</p><button class="primary" id="iv-start">开始访谈</button><button id="iv-manual">使用三问手动访谈</button><p id="iv-error" role="status"></p></section>');for(const [id,action] of [['#iv-start','start'],['#iv-manual','manual-start']])$(id).onclick=async()=>{try{$(id).disabled=true;await api('/api/core/interview/'+action,{});await interviewPage();}catch(e){$('#iv-error').textContent=e.message+' 可选择三问手动访谈继续。';$(id).disabled=false;}};return;}
 if(d.status==='asking'){
  const q=d.current_question,limit=d.source?.kind==='manual'?3:d.max_questions;
  const legacy=q.number>limit,answered=d.messages.filter(m=>m.role==='user').length;
  host.insertAdjacentHTML('beforeend',`<form class="card" id="journey-answer">
   <p>${legacy?`已保存 ${answered} 次回答`:`第 ${q.number} 问 · 最多 ${limit} 问${q.number>6?' · 补充问题':''}`}</p>
   <h2>${legacy?'已经聊了很多，可以查看总结了。':esc(q.text)}</h2>
   ${legacy?'<p>之前的回答都已保留，不需要继续回答更多问题。</p>':''}
   <label for="onboard-answer">${legacy?'还想补充什么（选填）':'你的回答'}</label>
   <textarea id="onboard-answer" name="text" ${legacy?'':'required'} maxlength="1000">${esc(!legacy&&window.SONGBAN_DEMO?['我想做一个作业时间安排小工具。','我会画界面草图，愿意向同学介绍作品。','我能投入6小时。'][Math.min(q.number-1,2)]:'')}</textarea>
   <p class="caption">可以留空直接结束；已输入的内容会一起保存。总结仍需你确认。</p>
   <div class="action-row">${legacy?'':`<button class="primary" type="submit">${q.number>=limit?'保存回答，查看总结':'保存回答，继续'}</button>`}
   <button type="button" id="iv-finish" class="${legacy?'primary':'secondary'}">先到这里，查看总结</button></div>
   <p role="status" id="iv-error"></p></form>`);
  const form=$('#journey-answer');let pending=null;
  async function submit(finish){
   const text=form.elements.text.value.trim(),action=finish?'finish':'answer';
   const body={version:d.version,...(!finish||text?{question_id:q.id,text}:{})};
   const key=JSON.stringify([action,body]);
   if(!pending||pending.key!==key)pending={key,request_id:crypto.randomUUID()};
   const wasBusy=state.busy;state.busy=true;
   form.querySelectorAll('button').forEach(b=>b.disabled=true);form.elements.text.readOnly=true;
   $('#iv-error').textContent=finish||q.number>=limit?'正在整理你的回答…':'正在保存回答…';
   try{
    await api('/api/core/interview/'+action,{...body,request_id:pending.request_id});
    form.dataset.dirty='false';state.drafts.delete(state.team+':journey-answer');await interviewPage();
   }finally{
    state.busy=wasBusy;
    if(form.isConnected){form.querySelectorAll('button').forEach(b=>b.disabled=false);form.elements.text.readOnly=false;$('#iv-error').textContent='';}
   }
  }
  bindForm('#journey-answer',()=>submit(legacy));
  $('#iv-finish').onclick=async()=>{
   if(form.dataset.submitting)return;
   form.dataset.submitting='true';form.querySelector('.error')?.remove();
   try{await submit(true);}catch(e){if(form.isConnected)formError(form,e);else toast(e.message);}
   finally{delete form.dataset.submitting;}
  };
  return;
 }
 const draft=d.profile?.draft||{};host.insertAdjacentHTML('beforeend',`<section class="card"><h2>核对你的起点</h2>${Object.entries({goals:'想做的事',experiences:'已有经历',time_available:'可投入时间'}).map(([key,label])=>{const list=Array.isArray(draft[key])?draft[key]:draft[key]?[draft[key]]:[];return `<h3>${label}</h3><p>${list.map(x=>esc(x.text)).join('；')||'尚未了解，可在组队后补充。'}</p>`;}).join('')}<p>这是本人的描述，不代表已经验证的能力。</p><button class="primary" id="iv-confirm">${learning?'确认总结，开始我的作品':'确认画像，选择比赛'}</button></section>`);$('#iv-confirm').onclick=async()=>{try{if(d.status!=='confirmed')await api('/api/core/interview/confirm',{version:d.version,request_id:crypto.randomUUID()});if(learning){location.assign('/learning-prep#/learn/first');return;}await load();go('contest');}catch(e){toast(e.message);}};
 }catch(e){host.insertAdjacentHTML('beforeend',`<p class="error">${esc(e.message)}</p><button onclick="interviewPage()">重新读取</button>`);}
}
async function contestPage(){
 const sample=window.SONGBAN_DEMO?{name:'松伴周末创造营（虚构演示）',event_time:'两天，上午选题，次日下午展示',location:'线上参加（演示）',rubric:'用户价值40%，完成度35%，协作与表达25%',requirements:'可运行网页、项目说明、代码链接、3分钟展示',deadline:'2026-11-02T18:00',source_text:'比赛：松伴周末创造营（虚构演示）\n时间：两天，上午选题，次日下午展示\n地点：线上参加（演示）\n评分：用户价值40%，完成度35%，协作与表达25%\n材料：可运行网页、项目说明、代码链接、3分钟展示\n截止：2026-11-02T18:00'}:{};
 $('#content').innerHTML=head('选择比赛','先把这场比赛了解清楚。','粘贴公告并整理，确认本次比赛后，导入主办方补充资料并提取关键信息。')+`<form class="card" id="journey-contest"><label for="contest-source">比赛公告原文</label><textarea id="contest-source" name="source_text" required>${esc(sample.source_text||'')}</textarea><button id="contest-read" type="button">整理公告</button><p id="contest-note" role="status"></p>${[['name','比赛名称'],['event_time','比赛时间'],['location','地点或参赛方式'],['rubric','公开评分标准'],['requirements','必须提交材料'],['deadline','截止时间']].map(([key,label])=>`<label for="contest-${key}">${label}</label><input id="contest-${key}" name="${key}" ${key==='deadline'?'type="datetime-local"':''} required value="${esc(sample[key]||'')}">`).join('')}<button type="submit" class="primary">确认比赛，导入赛事资料</button></form>`;
 const form=$('#journey-contest');$('#contest-read').onclick=async()=>{const button=$('#contest-read');button.disabled=true;try{const result=await api('/api/journey/extract',{text:form.elements.source_text.value});for(const [key,value] of Object.entries(result.fields||{}))if(form.elements[key]&&value)form.elements[key].value=value;$('#contest-note').textContent=result.notice;}catch(e){$('#contest-note').textContent=e.message+' 公告仍保留，可核对后手动填写。';}finally{button.disabled=false;}};
 bindForm('#journey-contest',async(f,fd)=>{await api('/api/journey/contest',{...values(fd),deadline:new Date(fd.get('deadline')).toISOString()});f.dataset.dirty='false';state.drafts.delete(state.team+':journey-contest');state.personal=false;await load();go('contest-materials');});
}
function journeySubmission(){
 const f=state.flow;if(!f?.strict)return;
 $('#content').innerHTML=head('提交准备','把最后一步完成。','全部成果已通过同伴检查。到主办方平台正式提交后，将真实回执记在这里。')+`<section class="card"><h2>核对必交材料</h2><p>${esc(f.contest?.facts?.requirements||'请对照本队确认的主办方公告。')}</p><form id="journey-submit"><label for="submission-materials">本次提交的作品、代码和展示材料</label><textarea id="submission-materials" name="materials" required>${window.SONGBAN_DEMO?'演示作品：作业时间安排网页；演示代码与展示说明已备齐。':''}</textarea><label for="submission-receipt">主办方回执或收件记录</label><textarea id="submission-receipt" name="receipt" required>${window.SONGBAN_DEMO?'DEMO-2026-001（虚构回执，仅供演示）':''}</textarea><label><input type="checkbox" name="confirmed" required>我已核对材料，并完成主办方平台提交</label><button class="primary" type="submit">记录回执，进入复盘</button></form></section>`;
 bindForm('#journey-submit',async(form,fd)=>{await api('/api/journey/teams/'+encodeURIComponent(state.team)+'/submission',{materials:String(fd.get('materials')),receipt:String(fd.get('receipt')),confirmed:fd.get('confirmed')==='on'});form.dataset.dirty='false';await load();go('review');});
}
