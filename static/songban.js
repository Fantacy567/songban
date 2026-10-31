'use strict';
const root = document.querySelector('#app');
const $ = selector => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {discussion:'讨论',in_progress:'进行中',blocked:'受阻',reported_done:'本人报告完成',todo:'尚无进展'};
const routePages = {login:'login',interview:'interview',contest:'contest','contest-materials':'contestMaterials',contest_materials:'contestMaterials',events:'events',event:'event',team:'team',onboarding:'onboarding',division:'division',ideas:'discussion','idea-library':'ideaLibrary',direction:'direction',workbench:'workbench',tasks:'myTasks',work:'myTasks','team-work':'teamTasks',collaboration:'division',tools:'plugin',library:'library',materials:'materials',members:'members',delivery:'delivery',review:'recap'};
const pageRoutes = {contestMaterials:'contest-materials',discussion:'ideas',ideaLibrary:'idea-library',overview:'tasks',myTasks:'work',teamTasks:'team-work',plugin:'tools',recap:'review'};
const identityStorage=window.SONGBAN_DEMO?sessionStorage:localStorage;
const state = {token:identityStorage.getItem('studio-token') || '',team:identityStorage.getItem('studio-squad') || '',page:'login',personal:sessionStorage.getItem('songban-personal')==='1',me:null,data:null,busy:false,epoch:0,events:[],eventId:sessionStorage.getItem('songban-event') || '',selectedRules:'',drafts:new Map(),syncing:false};
const endpoint = suffix => '/api/core/teams/' + encodeURIComponent(state.team) + suffix;
const values = data => Object.fromEntries(data.entries());
function toast(message) {
  const el=document.querySelector('#toast'); el.textContent=message; el.hidden=false;
  clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.hidden=true,6500);
}
async function api(path, body, method) {
  const epoch=state.epoch, token=state.token;
  const response=await fetch(path,{method:method || (body ? 'POST':'GET'),headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});
  let data; try { data=await response.json(); } catch { throw Error('服务返回异常，请稍后重试。'); }
  if(epoch!==state.epoch) throw Error('账号已切换，请在当前页面重试。');
  if(!response.ok) {
    const error=Object.assign(Error(data.error?.message || (response.status===404?'页面与服务版本不一致，请刷新；若仍失败请重启当前服务。':'请求失败，请重试。')),{status:response.status,code:data.error?.code});
    if(response.status===401 && token && !path.startsWith('/api/studio/')) { clearIdentity(); renderAuth(); }
    throw error;
  }
  return data;
}
let workbenchMount=null;
function unmountWorkbench(){if(workbenchMount){workbenchMount.unmount();workbenchMount=null;}}
function clearIdentity(persist=true) {
  clearArchiveState();
  unmountWorkbench();state.personal=false;sessionStorage.removeItem('songban-personal');
  root.querySelector('#parent-report-section')?.remove();
  guestOpening=null;startingDrafts.clear();
  for(const key of Object.keys(sessionStorage))if(key.startsWith('songban:workbench:')||key.startsWith('songban:start:'))sessionStorage.removeItem(key);
  if(typeof SongbanMaterials!=='undefined')SongbanMaterials.reset();
  if(typeof SongbanTaskProgress!=='undefined')SongbanTaskProgress.reset();
  if(typeof SongbanTopics!=='undefined')SongbanTopics.reset();
  state.epoch++; state.token=''; state.me=null; state.flow=null; state.data=null; state.team=''; state.libraryNote=''; state.drafts.clear();
  if(persist){identityStorage.removeItem('studio-token');identityStorage.removeItem('studio-squad');}
}
function formError(form,error) {
  let box=form.querySelector('.error');
  if(!box){box=document.createElement('div');box.className='error';box.setAttribute('role','alert');form.prepend(box);}
  box.textContent=error.message || String(error);
  if(error.status===409&&form.id!=='auth-form'){const b=document.createElement('button');b.type='button';b.textContent='读取最新版本，保留我的输入';b.onclick=()=>refresh(true);box.append(b);}
}
function bindForm(id,handler) {
  const form=$(id); if(!form)return;
  form.addEventListener('submit',async e=>{
    e.preventDefault();if(form.dataset.submitting)return;
    const team=state.team,submitted=new FormData(form),snapshot=JSON.stringify(values(submitted));
    form.dataset.submitting='true';const button=form.querySelector('button[type=submit]');if(button)button.disabled=true;
    form.querySelector('.error')?.remove();
    try{
      await handler(form,submitted);
      const current=$(id);
      if(current && state.team===team && JSON.stringify(values(new FormData(current)))===snapshot){
        current.dataset.dirty='false';current.querySelector('[data-draft-notice]')?.remove();
        state.drafts.delete(team+':'+form.id);
      }
      if(!current)state.drafts.delete(team+':'+form.id);
    }
    catch(error){if(form.isConnected)formError(form,error);else toast(error.message);}
    finally{delete form.dataset.submitting;if(button)button.disabled=false;}
  });
}
function captureDrafts() {
  root.querySelectorAll('form[data-dirty="true"]:not(#auth-form):not(#starting-form)').forEach(form=>{
    if(form.dataset.submitting)return;
    const fields=[...form.elements].filter(e=>e.name && !['password','file'].includes(e.type));
    state.drafts.set(state.team+':'+form.id,fields.map(e=>[e.name,e.type==='checkbox'?e.checked:e.value]));
  });
}
function restoreDrafts() {
  root.querySelectorAll('form:not(#auth-form)').forEach(form=>{
    const draft=state.drafts.get(state.team+':'+form.id);if(!draft)return;
    for(const [name,value] of draft){const input=form.elements.namedItem(name);if(input){if(input.type==='checkbox')input.checked=value;else input.value=value;}}
    form.dataset.dirty='true';const note=document.createElement('p');note.className='notice';note.dataset.draftNotice='true';note.textContent='已保留你未保存的输入，请核对最新团队资料后再保存。';form.prepend(note);
  });
}
function icon(kind) {
  const paths={events:'M5 5h14v15H5z M8 2v6 M16 2v6 M5 10h14',work:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',arrow:'M4 12h16 M14 6l6 6-6 6'};
  return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[kind]||paths.arrow}"/></svg>`;
}
function pine(small=false){return `<div class="pine ${small?'pine-small':''}" role="img" aria-label="松伴小松树"><div class="pine-shape"></div><div class="pine-eyes"><i></i><i></i></div></div>`;}
function brand(){return '<a class="wordmark" href="#/login" aria-label="松伴首页"><b>松伴</b><span>SONGBAN</span></a>';}
function head(kicker,title,description){return `<div class="page-heading"><div><p class="eyebrow">${esc(kicker)}</p><h1>${esc(title)}</h1><p class="subtitle">${esc(description)}</p></div>${pine(true)}</div>`;}
function go(page) {
  captureDrafts();routeFromHash('#/'+(pageRoutes[page]||page));render();window.scrollTo({top:0,behavior:'instant'});
  refreshOnEntry();
}
function refreshOnEntry(){if(state.me&&state.team&&!['login','events','event','onboarding'].includes(state.page)){const s=$('#sync-state');if(s)s.textContent='正在同步最新进展…';void refresh();}}
async function navigateWorkspace(page,target){
  if(!['work','direction','materials','library','team','members','tools','delivery','review','tasks'].includes(page))return;
  if(target){
    const team=target.teamId;
    if(team!==null&&!state.me?.teams.some(t=>t.id===team)){toast('请先加入目标团队，再查看记录。');return;}
    captureDrafts();unmountWorkbench();state.epoch++;state.personal=team===null;state.team=team||'';state.data=null;
    sessionStorage.setItem('songban-personal',state.personal?'1':'0');identityStorage.setItem('studio-squad',state.team);
    const epoch=state.epoch;
    try{if(team)state.data=await api(endpoint(''));if(epoch!==state.epoch)return;}
    catch(error){if(epoch===state.epoch){go('work');toast(error.message);}return;}
  }
  state.libraryNote=target?.noteId||'';go(page);
}
function chooseLibraryTeam(){
  $('#content').innerHTML=head('选择查看范围','查看已共享的团队记录','个人讨论仍属于你。请选择已经接收内容的小队。')+`<section class="card"><div class="action-row">${state.me.teams.map(t=>`<button data-library-team="${esc(t.id)}">查看「${esc(t.name)}」的记录</button>`).join('')}</div></section>`;
  root.querySelectorAll('[data-library-team]').forEach(b=>b.onclick=()=>navigateWorkspace('library',{teamId:b.dataset.libraryTeam}));
}
function deadlineToInput(value){if(!value||Number.isNaN(Date.parse(value)))return '';return new Date(Date.parse(value)+8*3600000).toISOString().slice(0,16);}
function shell() {
  unmountWorkbench();
  const activity=['events','event','onboarding'].includes(state.page);
  root.innerHTML=`<div class="app-shell" data-shell="songban-v1" data-route="${pageRoutes[state.page]||state.page}"><header class="app-header">${brand()}<div class="header-actions"><span class="status" id="sync-state">${state.me?(state.me.guest?'访客体验':'已连接团队服务'):'可直接体验'}</span>${state.me?`<button class="ghost" id="account-settings">账号</button><button class="ghost" id="logout">退出</button>`:'<button class="ghost" data-auth>登录</button>'}${!window.SONGBAN_DEMO?'<a class="text-link" href="/demo/">演示</a>':''}<button class="help-button" data-help aria-label="使用帮助">?</button></div></header><aside class="sidebar"><a class="sidebar-brand" href="#/events" aria-label="返回活动">松</a><nav aria-label="主导航"><a href="#/events" class="${activity?'active':''}" ${activity?'aria-current="page"':''}>${icon('events')}<span>活动</span></a><a href="#/work" class="${!activity?'active':''}" ${!activity?'aria-current="page"':''}>${icon('work')}<span>实践</span></a></nav><a class="side-profile" href="#/members" aria-label="我的团队设置">${esc(state.me?.person.name?.slice(0,1)||'我')}</a></aside><main id="main-content" tabindex="-1" class="app-content">${!activity?`<div class="practice-bar"><div class="practice-tabs" aria-label="实践页面">${[['ideas','选题'],['direction','方向'],['division','分工'],['work','任务'],['delivery','提交'],['review','复盘']].filter(([route])=>state.data?.topic_confirmed||route==='ideas').filter(([route])=>state.data?.division_status==='published'||(!state.data?.division_status&&state.data?.plan_version>0)||!['work','delivery','review'].includes(route)).map(([route,label])=>`<a href="#/${route}" class="${(pageRoutes[state.page]||state.page)===route?'active':''}">${label}</a>`).join('')}</div>${state.me?.teams.length?`<select id="team-switch" aria-label="切换团队"><option value="__personal" ${state.personal?'selected':''}>我的个人空间</option>${state.me.teams.map(t=>`<option value="${esc(t.id)}" ${t.id===state.team?'selected':''}>${esc(t.name)}</option>`).join('')}<option value="__new">＋ 创建或加入团队</option></select>`:''}</div>`:''}<div id="content"></div>${!activity&&state.me?`<details class="stage-support"><summary>队伍、连接器与赛事资料</summary><div class="action-row"><a href="#/team">队伍与邀请码</a><a href="#/members">我的能力与时间</a><a href="#/tools">松伴连接器</a><a href="#/contest-materials">本场赛事关键信息</a><a href="#/materials">其他原件</a><a href="#/idea-library">选题原文</a><a href="#/library">开发资料</a></div></details>`:''}</main><footer class="page-footer">${activity?'活动目录包含虚构样例，请以主办方公告为准。':'团队资料与操作结果以服务端保存记录为准。'}</footer></div>`;
  root.querySelectorAll('[data-auth]').forEach(b=>b.onclick=()=>openAuth());
  $('[data-help]').onclick=()=>showHelp();
  if($('#account-settings'))$('#account-settings').onclick=openAccount;
  if($('#logout'))$('#logout').onclick=()=>{if(window.SONGBAN_DEMO){location.href='/';return;}clearIdentity();go('login');toast('已退出当前浏览器。');};
  if($('#team-switch'))$('#team-switch').onchange=async e=>{
    captureDrafts();const team=e.target.value;
    if(team==='__new'){go('team');renderOnboarding();return;}
    unmountWorkbench();state.epoch++;state.personal=team==='__personal';sessionStorage.setItem('songban-personal',state.personal?'1':'0');state.team=state.personal?'':team;state.data=null;identityStorage.setItem('studio-squad',state.team);
    if(state.personal){go('workbench');return;}
    try{state.data=await api(endpoint(''));render();}catch(error){$('#content').innerHTML=`<p class="error">${esc(error.message)}</p>`;}
  };
}
function render() {
  gateJourney();
  const guided=!!(state.flow?.strict || state.data?.legacy_topic_selection || state.data?.division_status);
  if(guided&&state.data?.topic_confirmed&&(state.data.division_status?state.data.division_status!=='published':!state.data.plan_version)&&['myTasks','teamTasks','overview','delivery','recap','workbench'].includes(state.page))state.page=state.data.division_status?'division':'direction';
  if(guided&&state.data&&!state.data.topic_confirmed&&['division','direction','myTasks','teamTasks','overview','library','delivery','recap'].includes(state.page))state.page='discussion';
  if(state.page==='overview'&&guided)state.page='myTasks';
  const route=pageRoutes[state.page]||state.page;history.replaceState(null,'','#/'+route);
  if(state.page==='login'){landing();return;}
  shell();journeyChrome();
  if(state.page==='onboarding'){onboardingPage();return;}
  if(state.page==='events'){eventsPage();return;}
  if(state.page==='event'){if(!state.me){guestEntryPage();return;}eventPage();return;}
  if(!state.me){guestEntryPage();return;}
  if(state.page==='workbench'){workbenchPage();return;}
  if(state.page==='materials'){materialsPage();return;}
  if(state.page==='interview'){interviewPage();return;}
  if(state.page==='contest'){contestPage();return;}
  if(state.page==='contestMaterials'){contestMaterialsPage();return;}
  if(state.page==='library'&&!state.data&&state.me.teams.length){chooseLibraryTeam();return;}
  if(state.page==='overview'&&!state.data){overview();return;}
  if(!state.data){renderOnboarding();return;}
  const pages={team:teamPage,division:divisionPage,discussion:discussionPage,ideaLibrary:()=>libraryView('discussion'),direction:direction,overview:overview,myTasks:myTasksPage,teamTasks:teamTasksPage,plugin:plugin,library:libraryView,materials:materialsPage,members:members,delivery:deliveryPage,recap:window.SongbanDemo?.parent_reports?legacyRecapPage:recapPage};
  (pages[state.page]||myTasksPage)();
  if(state.page==='direction'&&!state.data.direction.rules&&state.selectedRules){const f=$('#direction-form');if(f){f.elements.rules.value=state.selectedRules;f.dataset.dirty='true';}else if(!state.data.topic_selection){state.drafts.set(state.team+':topic-start',[['rules',state.selectedRules]]);}}
  restoreDrafts();
  root.querySelectorAll('label:not([for])').forEach((label,index)=>{
    if(label.querySelector('input,textarea,select'))return;
    const next=label.nextElementSibling;
    const field=next?.matches('input,textarea,select')?next:next?.querySelector('input,textarea,select');
    if(field){if(!field.id)field.id='field-'+state.page+'-'+index;label.htmlFor=field.id;}
  });
}
function workbenchPage(){
  const host=$('#content');
  if(!window.SongbanWorkbench){
    host.innerHTML=head('实践 / 项目工作台','工作台暂时未能加载。','可以重新加载页面，或继续处理团队任务。')+'<p class="error">工作台资源加载失败，请重新加载页面。</p><a class="primary" href="#/tasks">查看团队任务</a>';
    return;
  }
  const epoch=state.epoch;
  workbenchMount=window.SongbanWorkbench.mount(host,{
    token:state.token,identityKey:String(state.me.person.id),teamId:state.team||null,
    onNavigate:(page,target)=>{if(epoch===state.epoch)void navigateWorkspace(page,target);},
    onPrepareDirection:fields=>{
      if(epoch!==state.epoch)return;
      if(!state.data?.me.captain){toast('请选择你担任队长的团队，再核对并保存共同方向。');return;}
      const limits={goal:3000,rules:12000,rubric:4000,non_goals:2000,deadline:100};
      const entries=Object.entries(fields||{}).filter(([key,value])=>Object.hasOwn(limits,key)&&typeof value==='string'&&value.length<=limits[key]&&(key!=='deadline'||!value||(/(?:Z|[+-]\d{2}:\d{2})$/.test(value)&&!Number.isNaN(Date.parse(value)))));
      if(!entries.length){toast('这条建议没有可填写的方向内容。');return;}
      if(!state.data.plan_version||state.data.topic_selection){
        if(!state.data.topic_selection){
          const key=state.team+':topic-start';
          if(!state.drafts.has(key))state.drafts.set(key,entries.filter(([k])=>['rules','rubric'].includes(k)));
          toast('赛事要求和评分依据已带入讨论设置；主方向需要全员讨论、投票确认。');
        }else toast('当前选题轮已开启，请通过连接器共享想法，再按全员投票确认主方向。');
        go('direction');return;
      }
      // A second draft must not silently overwrite a previously edited direction.
      if(state.drafts.has(state.team+':direction-form')){go('direction');toast('已保留原方向草稿，请先处理后再采用新的建议。');return;}
      go('direction');const form=$('#direction-form');if(!form)return;
      entries.forEach(([key,value])=>{const field=form.elements.namedItem(key);if(field&&!field.disabled)field.value=key==='deadline'?deadlineToInput(value):value;});
      form.dataset.dirty='true';captureDrafts();
      const note=document.createElement('p');note.className='notice';note.textContent='已填入工作台建议，尚未保存。请核对每项内容，再确认共同方向。';form.prepend(note);
    },
    onShared:()=>{if(epoch===state.epoch)refresh();},
    onUnauthorized:()=>{if(epoch===state.epoch){clearIdentity();renderAuth();}}
  });
}
const conceptProjects=[
  {slug:'question-workshop',name:'问号工坊',track:'Agent',description:'通过追问与练习，把学习卡点拆成下一步。'},
  {slug:'dinner-agent',name:'晚饭有谱',track:'Agent',description:'根据已有食材安排晚餐，并整理缺少的食材清单。'},
  {slug:'tiny-room',name:'方寸小屋',track:'3D',description:'摆放家具、切换材质，搭建可旋转浏览的三维空间。'},
  {slug:'creator-shop',name:'小摊计划',track:'商业化产品 · 硬件',description:'让校园创作者的贴纸与手作，通过智能售卖柜被发现。'},
  {slug:'leaf-archive',name:'叶脉档案',track:'模型训练 · 硬件',description:'用摄像头采集叶片，让自己训练的分类模型认识植物。'},
  {slug:'cloud-post',name:'云上邮局',track:'游戏',description:'连接漂浮云岛，解开谜题，送出一封跨越云海的信。'}
];
function previewConcept(project,trigger){
  const dialog=modal(project.name,`<p class="concept-meta">概念项目 · ${esc(project.track)}</p><img class="concept-cover" src="/static/landing/projects/${project.slug}-cover.webp" alt="${esc(project.name)}概念设计预览" width="1600" height="1000"><p class="concept-description">${esc(project.description)}</p><div class="concept-actions"><p class="caption">创作方向示意，不代表已完成的参赛作品。</p><a class="text-link" href="#/events">寻找适合的活动 ${icon('arrow')}</a></div>`);
  dialog.classList.add('concept-dialog');
  dialog.querySelector('h2').id='concept-title';dialog.setAttribute('aria-labelledby','concept-title');
  trigger.setAttribute('aria-expanded','true');
  dialog.addEventListener('close',()=>trigger.setAttribute('aria-expanded','false'));
  dialog.addEventListener('click',e=>{const r=dialog.getBoundingClientRect();if(e.target===dialog&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))dialog.close();});
  dialog.querySelector('a').onclick=()=>dialog.close();
}
function landing(){
  unmountWorkbench();
  root.innerHTML=`<div class="landing landing-showcase" data-shell="songban-v1" data-route="login"><header class="landing-header"><a class="landing-wordmark" href="#/login" aria-label="松伴首页"><img src="/static/landing/songban-cn.png" alt="松伴" width="78" height="34"><img src="/static/landing/songban-en.png" alt="SONGBAN" width="103" height="20"></a><button class="ink-button landing-login" data-auth>${state.me?'回到实践':'登录'} <span aria-hidden="true">↗</span></button></header><main id="main-content" tabindex="-1"><section class="landing-stage" aria-label="松伴黑客松创作陪练"><div class="showcase-copy"><h1><span>有松伴在场</span><span>每一步都有方向</span></h1><p>一场黑客松，一群同路人，让创作一步步发生。</p><a class="primary showcase-cta" href="#/onboarding"><span>找到适合我的黑客松</span>${icon('arrow')}</a></div><div class="showcase-companion" role="img" aria-label="松伴小松树"><span class="showcase-silhouette"></span><span class="showcase-eye eye-left"><i></i></span><span class="showcase-eye eye-right"><i></i></span></div><div class="showcase-deck" aria-label="六个概念项目，点击查看创作方向">${conceptProjects.map(project=>`<button class="showcase-card concept-${project.slug}" data-concept="${project.slug}" aria-label="查看${project.name}" aria-haspopup="dialog" aria-expanded="false"><span class="showcase-card-inner"><img src="/static/landing/projects/${project.slug}-thumb.webp" alt="" width="640" height="400" decoding="async"><span class="showcase-card-label"><strong>${project.name}</strong><small>${project.track}</small></span></span></button>`).join('')}</div></section></main></div>`;
  $('[data-auth]').onclick=()=>state.me?go('work'):openAuth();
  root.querySelectorAll('[data-concept]').forEach(button=>button.onclick=()=>previewConcept(conceptProjects.find(project=>project.slug===button.dataset.concept),button));
  if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
    const stage=$('.landing-stage'),companion=$('.showcase-companion');
    stage.onpointermove=e=>{const r=companion.getBoundingClientRect();companion.style.setProperty('--gaze-x',Math.max(-3,Math.min(3,(e.clientX-r.left-r.width/2)/90))+'px');companion.style.setProperty('--gaze-y',Math.max(-3,Math.min(3,(e.clientY-r.top-r.height/2)/90))+'px');};
    stage.onpointerleave=()=>{companion.style.setProperty('--gaze-x','0px');companion.style.setProperty('--gaze-y','0px');};
  }
}
function modal(title,body){
  const previous=document.activeElement;const dialog=document.createElement('dialog');dialog.className='check-dialog';
  dialog.innerHTML=`<div class="modal-top"><h2>${esc(title)}</h2><button type="button" aria-label="关闭弹窗" data-close>×</button></div>${body}`;
  root.append(dialog);dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();if(previous?.isConnected)previous.focus();});dialog.showModal();return dialog;
}
function showHelp(){modal('我们一步步来。','<p>先了解活动、收集个人材料，在「实践 → 工作台」整理思路。还没有小队也可以开始个人讨论。</p><p>准备与同伴合作时创建或加入小队，用队伍码邀请队友。个人讨论仍在「我的个人空间」；选择内容、编辑摘要并预览后，才会共享给指定团队。</p><p>队长确认共同方向，在「任务」里生成并核对分工。成员同步成果与依据，再由另一位队友检查。</p><p>工作台会显示当前项目的下一步。可以随时回个人空间继续旧讨论；「交付」导出交接清单，「复盘」记录收获。</p><p>无需安装外部工具，也能在网页完成讨论、进展同步和检查。「个人工具」用于连接已有工具。</p><p class="muted">活动样例不代表真实报名。任务检查通过也不等于主办方已经收到作品。</p>');}
function renderAuth(){state.page='login';landing();openAuth();}
async function openAccount(){
  const dialog=modal('登录账号','<p role="status">正在读取账号信息…</p>');
  try{
    const account=await api('/api/studio/account');if(!dialog.isConnected)return;
    const body=document.createElement('div');
    body.innerHTML=account.email?`<p>已绑定邮箱：<strong>${esc(account.email)}</strong></p><p class="muted">可以使用邮箱验证码或原来的密码登录同一个账号。</p>`:'<p>绑定邮箱后，可以用邮箱验证码登录，继续使用原来的团队和资料。</p><button class="primary" id="bind-email">绑定邮箱</button>';
    dialog.querySelector('[role=status]').replaceWith(body);
    body.querySelector('#bind-email')?.addEventListener('click',()=>{dialog.close();openAuth('bind');});
  }catch(error){if(dialog.isConnected)dialog.querySelector('[role=status]').textContent=error.message;}
}
function openAuth(initial='password',prefill={}){
  const binding=initial==='bind';
  const dialog=modal(binding?'绑定邮箱':'欢迎来到松伴','<div id="auth-body"></div>');dialog.classList.add('auth-dialog');
  let mode=initial,timer;
  const drafts={password:{...prefill},sms:{...prefill},email:{...prefill},bind:{...prefill}},cooldowns=new Map(),sending=new Set();
  const draw=()=>{
    const old=dialog.querySelector('form');if(old)drafts[old.dataset.channel]={...drafts[old.dataset.channel],...values(new FormData(old))};
    const register=['register','email-register'].includes(mode),email=mode.startsWith('email')||binding;
    const channel=binding?'bind':email?'email':mode==='password'?'password':'sms',draft=drafts[channel],renderMode=mode;
    const contactId=email?'auth-email':mode==='password'?'auth-account':'auth-phone';
    const contactName=email?'email':mode==='password'?'account':'phone';
    dialog.querySelector('#auth-body').innerHTML=`<p class="subtitle">${binding?'验证邮箱，继续使用同一个松伴账号。':'登录，和同伴一起把想法做出来。'}</p>${binding?'':`<div class="auth-tabs" role="group" aria-label="登录方式"><button type="button" data-mode="password" aria-pressed="${mode==='password'}">密码登录</button><button type="button" data-mode="email" aria-pressed="${email}">邮箱登录</button><button type="button" data-mode="sms" aria-pressed="${channel==='sms'}">短信登录</button></div>`}<form id="auth-form" data-channel="${channel}">
      <label for="${contactId}">${email?'邮箱地址':mode==='password'?'手机号或邮箱':'手机号'}</label><input id="${contactId}" name="${contactName}" type="${email?'email':'text'}" ${channel==='sms'?'inputmode="tel"':''} autocomplete="${email?'email':channel==='sms'?'tel':'username'}" maxlength="${channel==='sms'?20:254}" value="${esc(draft[contactName]||'')}" required>
      ${mode!=='password'?`<label for="auth-code">${email?'邮箱':'短信'}验证码</label><div class="code-input"><input id="auth-code" name="code" inputmode="numeric" autocomplete="one-time-code" minlength="6" maxlength="6" pattern="[0-9]{6}" value="${esc(draft.code||'')}" required><button type="button" id="send-code">获取验证码</button></div><p id="code-notice" class="muted" role="status"></p><p id="code-status" class="caption" role="status">正在检查验证码服务…</p>`:''}
      ${register||mode==='password'?`<label for="auth-password">${register?'设置密码':'密码'}</label><input id="auth-password" name="password" type="password" minlength="8" maxlength="64" autocomplete="${register?'new-password':'current-password'}" required>`:''}
      ${register?`<label for="auth-name">你的名字</label><input id="auth-name" name="name" maxlength="40" autocomplete="nickname" value="${esc(draft.name||'')}" required><label for="auth-skills">目前做得到的事</label><input id="auth-skills" name="skills" placeholder="例如：设计、整理资料，或正在学习" maxlength="500" value="${esc(draft.skills||'')}" required><label for="auth-profile">这次想尝试什么</label><input id="auth-profile" name="profile" placeholder="例如：和同伴完成第一个作品" maxlength="2000" value="${esc(draft.profile||'')}" required>`:''}
      <p class="caption">${binding?'绑定后，原有的手机号和密码仍可使用。':email?'已有手机号账号？请先登录，再在右上角「账号」中绑定邮箱，保留原团队和资料。':register?'注册后，密码和验证码两种方式都可以使用。':'已绑定的手机号和邮箱使用同一个松伴账号。'}</p>
      <button class="primary wide" type="submit">${binding?'确认绑定':register?'注册并开始':'登录并开始'} ${icon('arrow')}</button>${binding?'':`<button class="text-link wide" type="button" data-register>${register?'已有账号，返回登录':'第一次来，注册账号'}</button>`}</form>`;
    const form=dialog.querySelector('form'),contact=form.elements[contactName];
    if(form.elements.password)form.elements.password.value=draft.password||'';
    dialog.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;draw();});
    dialog.querySelector('[data-register]')?.addEventListener('click',()=>{mode=register?(email?'email':'sms'):(channel==='sms'?'register':'email-register');draw();});
    const statusNode=dialog.querySelector('#code-status'),send=dialog.querySelector('#send-code');let available=null;
    const key=()=>channel+':'+contact.value.trim().toLowerCase();
    const tick=()=>{
      if(!form.isConnected){clearInterval(timer);return;}if(!send)return;
      const left=Math.max(0,Math.ceil(((cooldowns.get(key())||0)-Date.now())/1000)),busy=sending.has(key());
      send.disabled=busy||left>0||available!==true||!!form.dataset.submitting;
      send.textContent=busy?'正在发送…':left?left+' 秒后重试':available===false?'暂不可用':'获取验证码';
      form.querySelector('button[type=submit]').disabled=available===false||!!form.dataset.submitting;
    };
    clearInterval(timer);timer=setInterval(tick,1000);contact.addEventListener('input',tick);tick();
    if(statusNode)api('/api/studio/'+(email?'email-status':'sms-status')).then(status=>{
      if(!statusNode.isConnected)return;available=status.registration_available??status.ready;
      statusNode.textContent=available?(email?'验证码发送到你的邮箱，10 分钟内有效。':status.test_mode?'当前为开发测试环境，验证码不会发送到手机。':'验证码将发送到手机。'):(email?'邮箱验证码暂不可用，已有账号可使用密码登录。':'短信验证码暂不可用，可以尝试邮箱注册或使用密码登录。');tick();
    }).catch(()=>{if(statusNode.isConnected){available=true;statusNode.textContent='暂时无法读取服务状态，发送时会显示实际结果。';tick();}});
    if(send)send.onclick=async()=>{
      if(!contact.reportValidity())return;
      const requestKey=key();if(sending.has(requestKey))return;sending.add(requestKey);form.querySelector('.error')?.remove();tick();
      try{
        const data=await api('/api/studio/'+(email?'email-codes':'codes'),email?{email:contact.value,purpose:binding?'bind':'login'}:{phone:contact.value});
        cooldowns.set(requestKey,Date.now()+(data.retry_after||60)*1000);
        if(form.isConnected)form.querySelector('#code-notice').textContent=data.sent?(email?'验证码已发送，请查看邮箱；如未收到，请检查垃圾邮件。':'验证码已发送，请查看短信。'):data.code?'本机开发测试码：'+data.code+'（未发送短信）':data.notice;
      }catch(error){if(form.isConnected)formError(form,error);}
      finally{sending.delete(requestKey);if(form.isConnected)tick();}
    };
    bindForm('#auth-form',async(submitted,fd)=>{
      const data=values(fd);let auth;
      const route=binding?'email-bind':register?(email?'register-email':'register'):email?'login-email':renderMode==='sms'?'login-code':'login';
      try{auth=await api('/api/studio/'+route,data);}
      catch(error){if(error.code==='registration_required'&&!binding&&submitted.isConnected){drafts[channel]=data;mode=email?'email-register':'register';draw();formError(dialog.querySelector('form'),error);return;}throw error;}
      unmountWorkbench();state.epoch++;
      if(!binding){state.personal=false;sessionStorage.removeItem('songban-personal');state.team='';state.data=null;state.drafts.clear();}
      state.token=auth.token;identityStorage.setItem('studio-token',auth.token);dialog.close();
      try{await load();if(state.page==='login')state.page=state.me.teams.length?'workbench':state.me.preferences?'events':'onboarding';render();toast(binding?'邮箱已绑定，团队和资料保持不变。':'已登录，欢迎回来。');}
      catch(error){shell();$('#content').innerHTML='<p class="error">'+esc(error.message)+'</p><button id="retry-load">重新连接</button>';$('#retry-load').onclick=()=>load().then(render).catch(e=>toast(e.message));}
    });
    contact.focus();
  };
  dialog.addEventListener('close',()=>clearInterval(timer));draw();
}
async function serialStateRead(read){
  const previous=state.readQueue||Promise.resolve();let release;
  state.readQueue=new Promise(resolve=>release=resolve);
  await previous;
  try{return await read();}finally{release();}
}
async function load(){
 return serialStateRead(async()=>{
  state.me=await api('/api/core/me');
  if(state.personal)state.team='';
  else if(!state.me.teams.some(t=>t.id===state.team))state.team=state.me.teams[0]?.id||'';
  identityStorage.setItem('studio-squad',state.team);state.data=state.team?await api(endpoint('')):null;
  state.flow=await api('/api/journey?team_id='+encodeURIComponent(state.team));
 });
}
async function eventsPage(){
  const container=$('#content');container.innerHTML=head('给第一次出发的你','这几场，也许适合你。','先看看活动的方向，再决定这次想做什么。')+'<p class="empty" role="status">正在读取活动…</p>';
  try{const p=state.me?.preferences;const query=p?'?'+new URLSearchParams({interests:p.interests.join(','),time:p.time}):'';const data=await api('/api/learning/v1/events'+query);if(!container.isConnected)return;state.events=data.items;
    container.innerHTML=head('给第一次出发的你','这几场，也许适合你。','先看看活动的方向，再决定这次想做什么。')+startingPreferencesSummary()+`<div class="notice">${esc(data.notice)}</div><section class="event-list card">${data.items.map((event,i)=>`<a class="event-row" href="#/event?id=${encodeURIComponent(event.id)}"><span class="event-number">0${i+1}</span><div><span class="chip">样例活动</span><h2>${esc(event.title)}</h2><p>${esc(event.date)} · ${esc(event.location)}</p><p class="muted">${esc(event.summary||event.description)}</p></div><span class="${i===0?'primary':'text-link'}">${i===0?'最推荐这场':'看看这场活动'} ${icon('arrow')}</span></a>`).join('')||'<p class="empty">暂时没有活动。</p>'}</section><div class="action-row"><p class="muted">已经有比赛要求或队伍码？</p><a href="#/team" class="text-link">直接开始实践 ${icon('arrow')}</a></div>`;
  }catch(error){if(container.isConnected){container.innerHTML=head('活动','暂时没有连接上。','可以稍后重试，也可以直接进入已有团队。')+`<p class="error">${esc(error.message)}</p><button class="primary" id="retry-events">重新读取</button>`;$('#retry-events').onclick=eventsPage;}}
}
async function eventPage(){
  const c=$('#content');c.innerHTML='<p class="empty" role="status">正在读取活动详情…</p>';
  try{
    if(!state.eventId){const list=await api('/api/learning/v1/events');state.eventId=list.items[0]?.id||'';}
    const data=await api('/api/learning/v1/events/'+encodeURIComponent(state.eventId));if(!c.isConnected)return;
    const e=data.item;sessionStorage.setItem('songban-event',e.id);
    c.innerHTML=`<a class="text-link back-link" href="#/events">← 返回活动</a>${head('先了解，再开始 / 样例活动',e.title,e.date+' · '+e.location)}<p class="event-lead">${esc(e.summary||e.description)}</p><div id="materials-host"></div><div class="action-row"><a class="text-link" href="#/team">创建或加入小队 →</a></div>`;
    await SongbanMaterials.mount($('#materials-host'),{event:e});
  }catch(error){if(c.isConnected)c.innerHTML=`<p class="error">${esc(error.message)}</p><a href="#/events">返回活动列表</a>`;}
}
function renderOnboarding(){
  const c=$('#content');if(!c)return;
  c.innerHTML=head('朋友一起，或者先自己开始','这次，和谁一起做？','创建一个真实的小队，用队伍码邀请熟悉的同伴。')+`<div class="two"><form class="card" id="create-team"><span class="chip">我来发起</span><h2>给小队起个名字。</h2><label for="team-name">小队名称</label><input id="team-name" name="name" maxlength="80" placeholder="例如：周末造梦小队" value="${window.SONGBAN_DEMO?'松伴演示小队':''}" required><p class="muted">创建后你负责确认共同方向；全员确认分工后，由内部 AI 发布任务。</p><button type="submit" class="primary">创建小队 ${icon('arrow')}</button></form><form class="card" id="join-team"><span class="chip">同伴在等我</span><h2>加入熟悉的队伍。</h2><label for="team-code">队伍码</label><input id="team-code" name="code" maxlength="80" placeholder="粘贴队友分享的队伍码" required><p class="muted">加入后，会读取这支队伍的真实方向和进展。</p><button type="submit" class="secondary">加入小队 ${icon('arrow')}</button></form></div>`;
  for(const [id,path] of [['#create-team','/api/core/teams'],['#join-team','/api/core/join']])bindForm(id,async(form,fd)=>{
    const created=await api(path,values(fd));state.personal=false;sessionStorage.removeItem('songban-personal');state.team=created.id;identityStorage.setItem('studio-squad',state.team);await load();go(id==='#create-team'?'discussion':'work');toast('小队已连接。');
  });
}
function teamPage(){
  const d=state.data;$('#content').innerHTML=head('一起动手，把想法做出来',d.team.name,'每个人，都能找到自己的位置。')+`<section class="card"><div class="row spread"><h2>我们的创作小队</h2><button id="new-team">创建或加入另一支小队</button></div><div class="member-grid">${d.members.map(m=>`<article class="member-tile"><div class="avatar">${esc(m.name.slice(0,1))}</div><h3>${esc(m.name)}</h3><p class="muted">${m.id===d.team.captain_id?'队长':'成员'}${m.id===d.me.id?' · 我':''}</p><p>${esc(m.willingness||'还没有填写这次想尝试的工作')}</p></article>`).join('')}</div><div class="invite-line"><span>邀请同伴加入</span><code>${esc(d.team.code)}</code><button id="copy-code">复制队伍码</button></div></section><div class="action-row"><a class="text-link" href="#/members">填写我的优势与时间</a><a class="primary" href="#/ideas">一起讨论选题 ${icon('arrow')}</a></div>`;
  $('#new-team').onclick=renderOnboarding;$('#copy-code').onclick=async()=>{try{await navigator.clipboard.writeText(d.team.code);toast('队伍码已复制。');}catch{toast('请选中页面上的队伍码手动复制。');}};
}
function deliveryPage(){
  if(state.flow?.strict){journeySubmission();return;}
  const d=state.data;$('#content').innerHTML=head('先核对，再交付','让作品，完整地出发。','依据团队当前记录检查成果，正式提交请前往主办方指定入口。')+workflowCard()+deliveryCard()+`<section class="card"><h2>逐项核对成果</h2>${tasks(d.active_plan.tasks||[],true)}</section>`;
  $('#content details.delivery-check').open=true;bindWorkflow();
  root.querySelectorAll('[data-report-task]').forEach(b=>b.onclick=()=>{const key=b.dataset.reportTask;go('tasks');root.querySelector(`[data-report-task="${CSS.escape(key)}"]`)?.click();});
}
function legacyRecapPage(){
  const d=state.data,w=d.workflow;$('#content').innerHTML=head('回头看看，每一步都有意义','这一次，我们走到了这里。','复盘来自当前团队记录；未知的结果，留给实际体验来回答。')+`<section class="card"><div class="recap-numbers"><div><strong>${w.total_tasks}</strong><span>已确认任务</span></div><div><strong>${w.accepted_tasks}</strong><span>当前成果有同伴检查</span></div><div><strong>${d.reports.length}</strong><span>最近进展记录</span></div></div><h2>我们最初想做什么</h2><p class="wrap">${esc(d.direction.goal||'尚未填写共同方向')}</p><h2>下一步</h2><p>${esc(w.next_action.title)}</p><p class="muted">${esc(w.next_action.reason)}</p></section><form class="card" id="reflection-form"><h2>留下一句真实的收获。</h2><label for="reflection">这次尝试了什么，哪里还想继续练习？</label><textarea id="reflection" name="summary" maxlength="3000" required placeholder="说说具体发生的事，也可以记录卡住的地方。"></textarea><p class="caption">保存为一条本人进展，团队成员可以看到。</p><button type="submit" class="primary">保存到团队记录 ${icon('arrow')}</button></form><section class="card"><h2>最近的脚印</h2>${reports()}</section>`;
  bindForm('#reflection-form',async(form,fd)=>{await api(endpoint('/reports'),{summary:'复盘：'+values(fd).summary,event_id:crypto.randomUUID(),tool:'网页复盘',origin:'human',status:'discussion'});state.drafts.delete(state.team+':reflection-form');await refresh(true);toast('复盘已保存到团队。');});
  if(window.SongbanDemo?.parent_reports && window.SongbanParentReport){
    const personId=d.me.id, teamId=d.team.id;
    window.SongbanParentReport.mount($('#content'),{
      key:personId+':'+teamId,
      getData:async(requestId)=>{
        const field=$('#reflection'),draft=field?.value||'',draftIsExample=window.SongbanDemo.isExampleField?.(field)===true;
        const result=await api('/api/core/teams/'+encodeURIComponent(teamId)+'/parent-report',{request_id:requestId,draft,draft_is_example:draftIsExample});
        if(state.team!==teamId || state.me?.person.id!==personId)throw Error('成员或小队已切换，请重新生成');
        return {...result.input,analysis:result.analysis,model:result.model};
      },
    });
  }
}
async function refresh(force=false){
  if(!state.token||!state.team)return;
  if(state.syncing){if(!force)return;await new Promise(resolve=>(state.refreshWaiters??=[]).push(resolve));return refresh(true);}
  state.syncing=true;const team=state.team;
  try{await serialStateRead(async()=>{
    const data=await api(endpoint(''));const flow=await api('/api/journey?team_id='+encodeURIComponent(team));if(team!==state.team)return;
    const stageChanged=state.flow?.stage!==flow.stage;state.flow=flow;
    const changed=stageChanged||!state.data||data.division_status!==state.data.division_status||data.division_round_id!==state.data.division_round_id||data.revision!==state.data.revision||data.proposal?.id!==state.data.proposal?.id||data.review_running!==state.data.review_running||data.last_error!==state.data.last_error;
    const editing=!!root.querySelector('form[data-dirty="true"],dialog[open]')||state.busy;
    if(state.page==='workbench'){state.data=data;}
    else if(force){captureDrafts();state.data=data;render();}
    else if(changed&&!editing&&state.page!=='materials'){state.data=data;if(['library','ideaLibrary'].includes(state.page)&&$('#library-notes'))libraryMarkUpdated();else if(!['login','events','event','onboarding'].includes(state.page))render();}
    if(changed&&editing&&!force&&['myTasks','teamTasks'].includes(state.page))updateTaskMeters(data);
    const status=$('#sync-state');if(status)status.textContent=changed&&editing&&!force?'有新进展，保存前请核对':'已同步 '+new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
  });}catch(error){const s=$('#sync-state');if(s)s.textContent='同步中断，输入已保留';if(force)toast(error.message);}
  finally{state.syncing=false;const waiters=state.refreshWaiters||[];state.refreshWaiters=[];waiters.forEach(resolve=>resolve());}
}
function routeFromHash(hash=location.hash){
  const [route,query]=(hash.replace(/^#\/?/,'')||'login').split('?');
  const eventId=new URLSearchParams(query||'').get('id');if(eventId)state.eventId=eventId;
  state.page=routePages[route]||'events';
  if(!state.flow?.strict&&!state.data?.legacy_topic_selection&&!state.data?.division_status){
    if(route==='work')state.page='workbench';
    if(route==='tasks')state.page='overview';
    if(route==='ideas')state.page='direction';
  }
}
document.addEventListener('DOMContentLoaded',async()=>{
  if(window.SONGBAN_DEMO){const demo=await api('/api/demo/bootstrap',{});state.token=demo.token;state.team='';identityStorage.setItem('studio-token',demo.token);}
  routeFromHash();
  if(state.token){try{await load();if(state.page==='login'&&state.me.teams.length)state.page='myTasks';}catch(error){if(state.token)toast(error.message);}}
  render();
  const markDirty=e=>{if(e.target.form&&e.target.form.id!=='starting-form'){e.target.form.dataset.dirty='true';delete e.target.form.dataset.eventId;}};
  root.addEventListener('input',markDirty);
  root.addEventListener('change',markDirty);
  let routeVersion=0;window.addEventListener('hashchange',async()=>{if(location.hash==='#possibilities')return;const version=++routeVersion,requestedHash=location.hash;captureDrafts();if(state.token){try{await load();}catch(e){toast(e.message);}}if(version!==routeVersion)return;routeFromHash(requestedHash);render();window.scrollTo(0,0);});
  setInterval(()=>{if(!document.hidden&&!['login','events','event','onboarding'].includes(state.page))refresh();},2000);
  window.addEventListener('storage',e=>{if(window.SONGBAN_DEMO)return;if(e.key==='songban-task-update'&&e.newValue){try{if(JSON.parse(e.newValue).team===state.team)refresh();}catch{}}if(e.key==='studio-token'&&e.newValue!==state.token){clearIdentity(false);state.token=e.newValue||'';if(state.token){load().then(render).catch(error=>toast(error.message));}else go('login');}});
});
