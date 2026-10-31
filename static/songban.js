'use strict';
const root = document.querySelector('#app');
const $ = selector => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {discussion:'讨论',in_progress:'进行中',blocked:'受阻',reported_done:'本人报告完成',todo:'尚无进展'};
const routePages = {login:'login',interview:'interview',contest:'contest',events:'events',event:'event',team:'team',onboarding:'members',division:'division',ideas:'discussion','idea-library':'ideaLibrary',direction:'direction',workbench:'workbench',tasks:'myTasks',work:'myTasks','team-work':'teamTasks',collaboration:'division',tools:'plugin',library:'library',materials:'materials',members:'members',delivery:'delivery',review:'recap'};
const pageRoutes = {discussion:'ideas',ideaLibrary:'idea-library',overview:'collaboration',myTasks:'work',teamTasks:'team-work',plugin:'tools',recap:'review'};
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
  for(const key of Object.keys(sessionStorage))if(key.startsWith('songban:workbench:'))sessionStorage.removeItem(key);
  if(typeof SongbanMaterials!=='undefined')SongbanMaterials.reset();
  state.epoch++; state.token=''; state.me=null; state.data=null; state.team=''; state.drafts.clear();
  if(persist){identityStorage.removeItem('studio-token');identityStorage.removeItem('studio-squad');}
}
function formError(form,error) {
  let box=form.querySelector('.error');
  if(!box){box=document.createElement('div');box.className='error';box.setAttribute('role','alert');form.prepend(box);}
  box.textContent=error.message || String(error);
  if(error.status===409){const b=document.createElement('button');b.type='button';b.textContent='读取最新版本，保留我的输入';b.onclick=()=>refresh(true);box.append(b);}
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
  root.querySelectorAll('form[data-dirty="true"]:not(#auth-form)').forEach(form=>{
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
  captureDrafts();state.page=routePages[page]||page;render();window.scrollTo({top:0,behavior:'instant'});
}
function shell() {
  unmountWorkbench();
  const activity=['events','event'].includes(state.page);
  root.innerHTML=`<div class="app-shell" data-shell="songban-v1" data-route="${pageRoutes[state.page]||state.page}"><header class="app-header">${brand()}<div class="header-actions"><span class="status" id="sync-state">${state.me?'已连接团队服务':'活动预览'}</span>${state.me?`<button class="ghost" id="logout">退出</button>`:'<button class="ghost" data-auth>登录</button>'}${!window.SONGBAN_DEMO?'<a class="text-link" href="/demo/">演示</a>':''}<button class="help-button" data-help aria-label="使用帮助">?</button></div></header><aside class="sidebar"><a class="sidebar-brand" href="#/events" aria-label="返回活动">松</a><nav aria-label="主导航"><a href="#/events" class="${activity?'active':''}" ${activity?'aria-current="page"':''}>${icon('events')}<span>活动</span></a><a href="#/work" class="${!activity?'active':''}" ${!activity?'aria-current="page"':''}>${icon('work')}<span>实践</span></a></nav><a class="side-profile" href="#/members" aria-label="我的团队设置">${esc(state.me?.person.name?.slice(0,1)||'我')}</a></aside><main id="main-content" tabindex="-1" class="app-content">${!activity?`<div class="practice-bar"><div class="practice-tabs" aria-label="实践页面">${[['ideas','选题'],['direction','方向'],['division','分工'],['work','任务'],['delivery','提交'],['review','复盘']].filter(([route])=>state.data?.topic_confirmed||route==='ideas').filter(([route])=>state.data?.division_status==='published'||(!state.data?.division_status&&state.data?.plan_version>0)||!['work','delivery','review'].includes(route)).map(([route,label])=>`<a href="#/${route}" class="${(pageRoutes[state.page]||state.page)===route?'active':''}">${label}</a>`).join('')}</div>${state.me?.teams.length?`<select id="team-switch" aria-label="切换团队"><option value="__personal" ${state.personal?'selected':''}>我的个人空间</option>${state.me.teams.map(t=>`<option value="${esc(t.id)}" ${t.id===state.team?'selected':''}>${esc(t.name)}</option>`).join('')}<option value="__new">＋ 创建或加入团队</option></select>`:''}</div>`:''}<div id="content"></div>${!activity&&state.me?`<details class="stage-support"><summary>队伍、连接器与赛事资料</summary><div class="action-row"><a href="#/team">队伍与邀请码</a><a href="#/members">我的能力与时间</a><a href="#/tools">松伴连接器</a><a href="#/materials">赛事原件</a><a href="#/idea-library">选题原文</a><a href="#/library">开发资料</a></div></details>`:''}</main><footer class="page-footer">${activity?'活动目录包含虚构样例，请以主办方公告为准。':'团队资料与操作结果以服务端保存记录为准。'}</footer></div>`;
  root.querySelectorAll('[data-auth]').forEach(b=>b.onclick=()=>openAuth());
  $('[data-help]').onclick=()=>showHelp();
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
  if(!window.SONGBAN_DEMO&&!state.token&&state.page!=='login'){location.replace('/demo/'+location.hash);return;}
  gateJourney();
  if(state.data?.topic_confirmed&&(state.data.division_status?state.data.division_status!=='published':!state.data.plan_version)&&['myTasks','teamTasks','overview','delivery','recap','workbench'].includes(state.page))state.page=state.data.division_status?'division':'direction';
  if(state.data&&!state.data.topic_confirmed&&['division','direction','myTasks','teamTasks','overview','library','delivery','recap'].includes(state.page))state.page='discussion';
  if(state.page==='overview')state.page='myTasks';
  const route=pageRoutes[state.page]||state.page;history.replaceState(null,'','#/'+route);
  if(state.page==='login'){landing();return;}
  shell();journeyChrome();
  if(state.page==='events'){eventsPage();return;}
  if(state.page==='event'){eventPage();return;}
  if(!state.me){$('#content').innerHTML=`${head('一起动手','让想法，有一个开始。','登录后创建或加入真实团队，和同伴一起保存进展。')}<section class="card empty"><p>使用手机号登录，接着完成你的作品。</p><button class="primary" data-auth-required>登录并继续 ${icon('arrow')}</button></section>`;$('[data-auth-required]').onclick=()=>openAuth();return;}
  if(state.page==='workbench'){workbenchPage();return;}
  if(state.page==='materials'){materialsPage();return;}
  if(state.page==='interview'){interviewPage();return;}
  if(state.page==='contest'){contestPage();return;}
  if(!state.data){renderOnboarding();return;}
  const pages={team:teamPage,division:divisionPage,discussion:discussionPage,ideaLibrary:()=>libraryView('discussion'),direction:direction,overview:myTasksPage,myTasks:myTasksPage,teamTasks:teamTasksPage,plugin:plugin,library:libraryView,materials:materialsPage,members:members,delivery:deliveryPage,recap:recapPage};
  (pages[state.page]||myTasksPage)();
  if(state.page==='direction'&&!state.data.direction.rules&&state.selectedRules){const f=$('#direction-form');f.elements.rules.value=state.selectedRules;f.dataset.dirty='true';}
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
    onNavigate:page=>{if(epoch===state.epoch&&['direction','materials','library','team','members','tools','delivery','review','tasks'].includes(page))go(page);},
    onPrepareDirection:fields=>{
      if(epoch!==state.epoch)return;
      if(!state.data?.me.captain){toast('请选择你担任队长的团队，再核对并保存共同方向。');return;}
      const limits={goal:3000,rules:12000,rubric:4000,non_goals:2000,deadline:100};
      const entries=Object.entries(fields||{}).filter(([key,value])=>Object.hasOwn(limits,key)&&typeof value==='string'&&value.length<=limits[key]&&(key!=='deadline'||!value||(/(?:Z|[+-]\d{2}:\d{2})$/.test(value)&&!Number.isNaN(Date.parse(value)))));
      if(!entries.length){toast('这条建议没有可填写的方向内容。');return;}
      // A second draft must not silently overwrite a previously edited direction.
      if(state.drafts.has(state.team+':direction-form')){go('direction');toast('已保留原方向草稿，请先处理后再采用新的建议。');return;}
      go('direction');const form=$('#direction-form');if(!form)return;
      entries.forEach(([key,value])=>{const field=form.elements.namedItem(key);if(field&&!field.disabled)field.value=value;});
      form.dataset.dirty='true';captureDrafts();
      const note=document.createElement('p');note.className='notice';note.textContent='已填入工作台建议，尚未保存。请核对每项内容，再确认共同方向。';form.prepend(note);
    },
    onShared:()=>{if(epoch===state.epoch)refresh();},
    onUnauthorized:()=>{if(epoch===state.epoch){clearIdentity();renderAuth();}}
  });
}
function landing(){
  unmountWorkbench();
  const projects=[['question-workshop','问号工坊','Agent'],['dinner-agent','晚饭有谱','Agent'],['tiny-room','方寸小屋','3D'],['creator-shop','小摊计划','商业化产品 · 硬件'],['leaf-archive','叶脉档案','模型训练 · 硬件'],['cloud-post','云上邮局','游戏']];
  root.innerHTML=`<div class="landing reference-design" data-shell="songban-v1" data-route="login"><header class="landing-header">${brand()}<div class="header-actions"><button class="ink-button" data-auth>${state.me?'回到实践':'登录'} ↗</button></div></header><main id="main-content" tabindex="-1"><section class="landing-hero"><div class="hero-copy"><h1>有松伴在场<br>每一步都有方向</h1><p class="subtitle">一场黑客松，一群同路人，让创作一步步发生。</p><a class="primary landing-cta" href="/demo/">找到适合我的黑客松 ${icon('arrow')}</a><p class="caption">免手机号体验 · 演示使用虚构资料</p></div><div class="pine" role="img" aria-label="松伴小松树"><img src="/static/design/pine-mascot.png" alt="" width="220" height="260"></div><div class="project-deck" id="possibilities" aria-label="创作方向示意，非已完成作品">${projects.map(([slug,title,type],i)=>`<div class="project-card card-${i}" style="--card-index:${i}"><img src="/static/design/${slug}.webp" alt="${title}创作方向示意" width="440" height="620"><div class="project-caption"><strong>${title}</strong><small>${type}</small></div></div>`).join('')}</div></section></main><footer class="page-footer">从小而完整的作品开始，留下真实的进展。</footer></div>`;
  $('[data-auth]').onclick=()=>state.me?go('work'):openAuth();
}
function modal(title,body){
  const previous=document.activeElement;const dialog=document.createElement('dialog');dialog.className='check-dialog';
  dialog.innerHTML=`<div class="modal-top"><h2>${esc(title)}</h2><button type="button" aria-label="关闭弹窗" data-close>×</button></div>${body}`;
  root.append(dialog);dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();if(previous?.isConnected)previous.focus();});dialog.showModal();return dialog;
}
function showHelp(){modal('我们一步步来。','<p>先了解活动，创建或加入小队，再一起确认方向。</p><p>在「个人任务」里完成自己的任务，在「团队任务」里查看队友进度；任务安排由队长确认。报告完成后，请另一位队友检查成果。</p><p>「个人工具」可以连接你已有的智能体；未连接时，也可以直接在网页补充进展。</p><p class="muted">活动样例不代表真实报名。任务检查通过也不等于主办方已经收到作品。</p>');}
function renderAuth(){state.page='login';landing();openAuth();}
function openAuth(initial='password',prefill={}){
  const dialog=modal('欢迎来到松伴','<div id="auth-body"></div>');dialog.classList.add('auth-dialog');
  let mode=initial, cooldownUntil=0, sending=false, draft={...prefill};let timer;
  const draw=()=>{
    const old=dialog.querySelector('form');if(old)draft={...draft,...values(new FormData(old))};
    const register=mode==='register';
    dialog.querySelector('#auth-body').innerHTML=`<p class="subtitle">登录，和同伴一起把想法做出来。</p><div class="auth-tabs" role="group" aria-label="登录方式"><button type="button" data-mode="password" aria-pressed="${mode==='password'}">密码登录</button><button type="button" data-mode="sms" aria-pressed="${mode==='sms'}">验证码登录</button></div><form id="auth-form"><label for="auth-phone">手机号</label><input id="auth-phone" name="phone" inputmode="tel" autocomplete="tel" maxlength="20" value="${esc(draft.phone||'')}" required>${mode!=='password'?`<label for="auth-code">短信验证码</label><div class="code-input"><input id="auth-code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" value="${esc(draft.code||'')}" required><button type="button" id="send-code">获取验证码</button></div><p id="code-notice" class="muted" role="status"></p><p id="sms-status" class="caption" role="status">正在检查短信配置…</p>`:''}${mode!=='sms'?`<label for="auth-password">${register?'设置密码':'密码'}</label><input id="auth-password" name="password" type="password" minlength="8" maxlength="64" autocomplete="${register?'new-password':'current-password'}" required>`:''}${register?'<label for="auth-name">你的名字</label><input id="auth-name" name="name" maxlength="40" autocomplete="nickname" required><label for="auth-skills">目前做得到的事</label><input id="auth-skills" name="skills" placeholder="例如：设计、整理资料，或正在学习" maxlength="500" required><label for="auth-profile">这次想尝试什么</label><input id="auth-profile" name="profile" placeholder="例如：和同伴完成第一个作品" maxlength="2000" required>':''}<p class="caption">${register?'注册后，密码和验证码两种方式都可以使用。':'两种登录方式使用同一个松伴账号。'}</p><button class="primary wide" type="submit">${register?'注册并开始':'登录并开始'} ${icon('arrow')}</button><button class="text-link wide" type="button" data-register>${register?'已有账号，返回登录':'第一次来，注册账号'}</button></form>`;
    dialog.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;draw();});
    dialog.querySelector('[data-register]').onclick=()=>{mode=register?'password':'register';draw();};
    const send=dialog.querySelector('#send-code');
    const smsStatus=dialog.querySelector('#sms-status');
    if(smsStatus)api('/api/studio/sms-status').then(status=>{
      if(!smsStatus.isConnected)return;
      smsStatus.textContent=status.configured?'验证码将发送到手机，页面不会显示验证码。':'短信服务尚未配置，暂不能注册或使用验证码登录。已有账号可使用密码登录。';
    }).catch(()=>{if(smsStatus.isConnected)smsStatus.textContent='短信状态暂时无法读取，发送时会显示实际结果。';});
    const tick=()=>{const b=dialog.querySelector('#send-code');if(!b)return;const left=Math.max(0,Math.ceil((cooldownUntil-Date.now())/1000));b.disabled=sending||left>0;b.textContent=sending?'正在发送…':left?left+' 秒后重试':'获取验证码';};
    clearInterval(timer);timer=setInterval(tick,1000);tick();
    if(send)send.onclick=async()=>{
      if(sending)return;sending=true;tick();
      try{const d=await api('/api/studio/codes',{phone:dialog.querySelector('#auth-phone').value});cooldownUntil=Date.now()+60000;
        const notice=dialog.querySelector('#code-notice');if(notice)notice.textContent=d.sent?'验证码已发送，请查看短信。':d.code?'本机开发测试码：'+d.code+'（未发送短信）':d.notice;
      }catch(error){const form=dialog.querySelector('form');if(form)formError(form,error);}
      finally{sending=false;tick();}
    };
    bindForm('#auth-form',async(form,fd)=>{
      const data=values(fd);let auth;
      try{auth=await api('/api/studio/'+(register?'register':mode==='sms'?'login-code':'login'),register?data:mode==='sms'?{phone:data.phone,code:data.code}:{account:data.phone,password:data.password});}
      catch(error){if(error.code==='registration_required'){draft=data;mode='register';draw();formError(dialog.querySelector('form'),error);return;}throw error;}
      unmountWorkbench();state.epoch++;state.personal=false;sessionStorage.removeItem('songban-personal');state.token=auth.token;state.team='';state.data=null;state.drafts.clear();identityStorage.setItem('studio-token',auth.token);dialog.close();
      try{await load();if(state.page==='login')state.page=state.me.teams.length?'myTasks':'events';render();toast('已登录，欢迎回来。');}
      catch(error){shell();$('#content').innerHTML='<p class="error">'+esc(error.message)+'</p><button id="retry-load">重新连接</button>';$('#retry-load').onclick=()=>load().then(render).catch(e=>toast(e.message));}
    });
    dialog.querySelector('#auth-phone').focus();
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
  try{const data=await api('/api/learning/v1/events');if(!container.isConnected)return;state.events=data.items;
    container.innerHTML=head('给第一次出发的你','这几场，也许适合你。','先看看活动的方向，再决定这次想做什么。')+`<div class="notice">${esc(data.notice)}</div><section class="event-list card">${data.items.map((event,i)=>`<a class="event-row" href="#/event?id=${encodeURIComponent(event.id)}"><span class="event-number">0${i+1}</span><div><span class="chip">样例活动</span><h2>${esc(event.title)}</h2><p>${esc(event.date)} · ${esc(event.location)}</p><p class="muted">${esc(event.summary||event.description)}</p></div><span class="${i===0?'primary':'text-link'}">看看这场活动 ${icon('arrow')}</span></a>`).join('')||'<p class="empty">暂时没有活动。</p>'}</section><div class="action-row"><p class="muted">已经有比赛要求或队伍码？</p><a href="#/team" class="text-link">直接开始实践 ${icon('arrow')}</a></div>`;
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
    else if(changed&&!editing&&state.page!=='materials'){state.data=data;if(['library','ideaLibrary'].includes(state.page)&&$('#library-notes'))libraryMarkUpdated();else if(!['login','events','event'].includes(state.page))render();}
    if(changed&&editing&&!force&&['myTasks','teamTasks'].includes(state.page))updateTaskMeters(data);
    const status=$('#sync-state');if(status)status.textContent=changed&&editing&&!force?'有新进展，保存前请核对':'已同步 '+new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
  });}catch(error){const s=$('#sync-state');if(s)s.textContent='同步中断，输入已保留';if(force)toast(error.message);}
  finally{state.syncing=false;const waiters=state.refreshWaiters||[];state.refreshWaiters=[];waiters.forEach(resolve=>resolve());}
}
function routeFromHash(hash=location.hash){
  const [route,query]=(hash.replace(/^#\/?/,'')||'login').split('?');
  const eventId=new URLSearchParams(query||'').get('id');if(eventId)state.eventId=eventId;
  state.page=routePages[route]||'events';
}
document.addEventListener('DOMContentLoaded',async()=>{
  if(window.SONGBAN_DEMO){const demo=await api('/api/demo/bootstrap',{});state.token=demo.token;state.team='';identityStorage.setItem('studio-token',demo.token);}
  routeFromHash();
  if(state.token){try{await load();if(state.page==='login'&&state.me.teams.length)state.page='myTasks';}catch(error){if(state.token)toast(error.message);}}
  render();
  const markDirty=e=>{if(e.target.form){e.target.form.dataset.dirty='true';delete e.target.form.dataset.eventId;}};
  root.addEventListener('input',markDirty);
  root.addEventListener('change',markDirty);
  let routeVersion=0;window.addEventListener('hashchange',async()=>{if(location.hash==='#possibilities')return;const version=++routeVersion,requestedHash=location.hash;captureDrafts();if(state.token){try{await load();}catch(e){toast(e.message);}}if(version!==routeVersion)return;routeFromHash(requestedHash);render();window.scrollTo(0,0);});
  setInterval(()=>{if(!document.hidden&&!['login','events','event'].includes(state.page))refresh();},2000);
  window.addEventListener('storage',e=>{if(window.SONGBAN_DEMO)return;if(e.key==='songban-task-update'&&e.newValue){try{if(JSON.parse(e.newValue).team===state.team)refresh();}catch{}}if(e.key==='studio-token'&&e.newValue!==state.token){clearIdentity(false);state.token=e.newValue||'';if(state.token){load().then(render).catch(error=>toast(error.message));}else go('login');}});
});
