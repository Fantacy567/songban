'use strict';
// Loaded only by scripts/run_demo.py on its separate loopback origin.
(() => {
  const demo = window.SongbanDemo;
  if (!demo) return;
  const prepared = new WeakSet();
  const edited = new WeakSet(), filled = new WeakMap();
  demo.isExampleField = field => !!field && !edited.has(field) && filled.get(field) === field.value;
  let story;
  const steps = [['onboarding','兴趣与城市'],['events','推荐活动'],['team','五人小队'],['materials','资料整理'],['direction','选题讨论与投票'],['work','工作台'],['tasks','个人与团队任务'],['members','成员资料'],['tools','连接工具'],['library','共享资料库'],['delivery','交付检查'],['review','复盘']];
  const sample = {
    city:'上海', experience:'【模拟经历】做过校园活动海报，希望和伙伴一起做一个可操作的小作品。',
    goal:demo.direction.goal, rules:demo.rules, rubric:demo.direction.rubric, non_goals:demo.direction.non_goals,
    deadline:demo.direction.deadline.slice(0,16), hours:'8', label:'我的演示工具', project_dir:'校园活动搭子（模拟项目）',
    code:demo.team.code, evidence_text:'【模拟依据】已走查正常、返回和空内容三种情况。\n【模拟成果】已准备项目说明、三页原型和一分钟展示提纲。',
    blocker:'【模拟】需要队友核对新版页面和展示顺序。', note:'【模拟核对】按示例检查方法查看了页面、返回操作与文字说明。',
    track:'校园生活与 AI 创作', minutes:'20', title:'校园活动搭子 · 演示讨论',
  };
  function actor() {
    const user = demo.users.find(u => u.id === state.me?.person.id) || demo.users[0];
    return {...user, ...story?.people.find(p => 'demo-' + p.key === user.id)};
  }
  function setValue(field, value, force=false) {
    if (!field || field.disabled || field.readOnly || edited.has(field) || field === document.activeElement) return;
    if (field.value === String(value)) return;
    if (!force && field.value && field.value !== filled.get(field)) return;
    prepared.add(field);
    filled.set(field, String(value));
    const proto = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : field instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(field, String(value));
    field.dispatchEvent(new Event('input', {bubbles:true}));
    field.dispatchEvent(new Event('change', {bubbles:true}));
  }
  function fill() {
    if (!story) return;
    const person = actor();
    const report = root.querySelector('#manual-report'), taskKey = report?.elements.task_key?.value;
    const task = state.data?.active_plan?.tasks?.find(t => t.key === taskKey);
    const progress = story.task_details[task?.title] || '已完成兴趣选择、活动推荐和组队分工的流程草图，并列出需要核对的活动时间与入门门槛。';
    const legacyPerson = demo.users.find(u => u.id === person.id);
    for (const field of root.querySelectorAll('input,textarea,select')) {
      if (field.disabled || field.readOnly || edited.has(field) || field.closest('#auth-form')) continue;
      if (['checkbox','radio','file','password','hidden'].includes(field.type)) continue;
      if (field.tagName === 'SELECT' && prepared.has(field)) continue;
      const form = field.form, name = field.name;
      let value, legacy;
      if (name === 'strengths') value = person.strengths;
      else if (name === 'willingness') value = person.willingness;
      else if (name === 'experience') value = person.experience;
      else if (name === 'name' && form?.id === 'create-team') value = story.team_name;
      else if (name === 'summary') value = form?.id === 'reflection-form' ? (person.reflection || story.reflection) : `【虚构进展】${task ? task.key+' · '+task.title+'\n' : ''}${progress}`;
      else if (name === 'evidence_text') value = `【演示成果记录】${progress}\n检查方式：按本任务的验收说明逐项核对成果内容，记录缺项和修改建议，再请另一位队员复查。`;
      else if (name === 'blocker') value = report?.elements.status?.value === 'blocked' ? '等待产品与前端确认同一版原型；请林同学在今天 13:00 前确认推荐理由和返回按钮文案。' : '暂无阻塞；下一步请同伴核对成果，并在周日 13:00 前冻结录屏版本。';
      else if (name === 'note') value = form?.id === 'check-form' ? '【虚构验收记录】已对照上方任务的检查方法逐项查看本轮成果，内容与本轮范围一致，未发现缺项；已记录需要在正式试用中进一步验证的推荐理解度问题。' : story.material_note;
      else if (name === 'task_key' && form?.id === 'manual-report' && !field.value) value = field.options[1]?.value;
      else if (name === 'status' && form?.id === 'manual-report') {setValue(field,'reported_done',true);continue;}
      else if (field.id === 'check-verdict' && !field.querySelector('[value="accepted"]')?.disabled) {setValue(field,'accepted',true);continue;}
      else if (name === 'code' && form?.id === 'join-team') value = (state.team === demo.team.id ? demo.team : demo.topic_team).code;
      else if (name === 'deadline') value = story.deadline.slice(0,16);
      else if (['goal','rules','rubric','non_goals','track'].includes(name)) value = story[name];
      else if (name === 'label') value = person.name + '的 Codex · 校园活动搭子';
      else if (name === 'title') value = '校园活动搭子 · 推荐理由与周末分工';
      else if (Object.hasOwn(sample,name)) value = sample[name];
      else if (field.id === 'material-text') value = story.rules + '\n\n' + story.chat;
      else if (field.id === 'material-url') value = story.url;
      else if (field.id === 'material-author') value = story.author;
      else if (field.id === 'material-nature') { setValue(field, 'sample', true); continue; }
      else if (field.closest('.sbw-composerWrap') && field.tagName === 'TEXTAREA') value = story.prompt;
      else if (field.closest('.sbw-sharePanel') && field.tagName === 'TEXTAREA') value = story.share;
      else if (field.closest('.sbw-sharePanel') && field.tagName === 'SELECT' && !field.value) value = state.team || demo.topic_team.id;
      else if (field.closest('.sbw') && field.tagName === 'INPUT') value = '校园活动搭子 · 推荐理由与周末分工';
      else if (name === 'text' && field.closest('[data-edit]')) value = '周日 15:00 前提交项目说明、可操作原型、代码说明和 60 秒演示视频；推荐卡片应说明适合人群与技能门槛。';
      // Upgrade only exact old demo defaults; never replace a participant's own draft.
      if (value !== undefined) {
        legacy = field.value === sample[name] || field.value === demo.direction[name] ||
          ['strengths','willingness'].includes(name) && field.value === legacyPerson?.[name] ||
          ['【模拟经历】做过校园活动海报，希望和伙伴一起做一个可以实际操作的小作品。',
           demo.rules + '\n【模拟想法】想做校园活动搭子，让同学按兴趣发现活动。',
           'https://example.invalid/songban-demo/rules','演示活动主办方 / 模拟成员',
           '请结合目前的目标和分工，帮我安排下一步，并说明完成后怎么请同伴检查。',
           '【模拟共享】这轮先完成兴趣、活动、组队和任务的完整流程，再请同伴核对成果。',
           '【模拟复盘】我试着把大目标拆成小任务，也学会先提交依据，再请同伴检查。下一次想提前安排演练时间。',
           '【模拟进展】已连接兴趣选择、活动推荐和任务页，接下来请队友按主流程核对。'].includes(field.value);
        setValue(field,value,legacy);
      }
    }
    const attachment=root.querySelector('#material-files');
    if(attachment&&!prepared.has(attachment)){
      prepared.add(attachment);
      if(!root.querySelector('#material-queued')?.textContent.includes('校园活动搭子-演示资料.txt')){
        const transfer=new DataTransfer();transfer.items.add(new File([story.rules+'\n\n'+story.chat], '校园活动搭子-演示资料.txt', {type:'text/plain'}));
        attachment.files=transfer.files;attachment.dispatchEvent(new Event('change',{bubbles:true}));
      }
    }
    for(const selector of ['[data-select]','.sbw-sourceOption input']){
      const fields=[...root.querySelectorAll(selector)];
      if(fields.length&&!fields.some(f=>f.checked)&&!prepared.has(fields[0])&&!fields[0].disabled){prepared.add(fields[0]);fields[0].click();}
    }
    const form = root.querySelector('#starting-form');
    if (form) for (const [key,values] of Object.entries({interests:['校园生活','音乐'],skills:['画画或设计','整理资料'],time:['一个周末']})) {
      if (!form.querySelector(`[name="${key}"]:checked`)) for (const field of form.querySelectorAll(`[name="${key}"]`)) {
        if (!prepared.has(field) && values.includes(field.value)) {prepared.add(field);field.checked=true;field.dispatchEvent(new Event('change',{bubbles:true}));}
      }
    }
    // The normal data mode reads this server's isolated demonstration team.
    const live = root.querySelector('[data-task-mode="live"]'); if (live && live.textContent !== '演示小队') live.textContent = '演示小队';
    const heading = root.querySelector('.task-live-heading'); if (heading && heading.textContent !== '演示小队的任务与协作') heading.textContent = '演示小队的任务与协作';
    const badge = root.querySelector('#sync-state'); if (badge && badge.textContent !== '演示身份 · ' + person.name) badge.textContent = '演示身份 · ' + person.name;
    for(const receipt of root.querySelectorAll('#install-result,#topic-install-result'))
      if(receipt.querySelector('.notice')&&!receipt.querySelector('[data-demo-receipt]')) receipt.innerHTML='<div class="notice" data-demo-receipt><strong>模拟连接流程已完成。</strong><p>点击顶部“填入 5 人讨论”，即可查看模拟回合并继续确认。</p><small>这是模拟回执，没有安装插件或修改电脑配置。</small></div>';
    document.querySelector('#demo-role').value = person.id;
    const current = location.hash.replace('#/','').split('?')[0];
    const step = document.querySelector('#demo-step');if(steps.some(([key])=>key===current))step.value=current;
    const scene=document.querySelector('#demo-scene');if([demo.team.id,demo.topic_team.id].includes(state.team))scene.value=state.team;
    const controls=document.querySelector('#demo-topic-controls');controls.hidden=!['direction','tasks'].includes(current);
    const topic=state.data?.topic_selection;
    const phases={upload:'discussion',confirm_next:'discussion',vote_others:'voting',claim_others:'selected'};
    controls.querySelectorAll('[data-demo-action]').forEach(button=>{
      button.disabled=demoBusy||topic?.phase!==phases[button.dataset.demoAction]||(button.dataset.demoAction==='claim_others'&&!state.data?.plan_version);
      button.hidden=button.dataset.demoAction==='claim_others'?current!=='tasks':current!=='direction';
    });
  }
  async function switchActor(id) {
    const person = demo.users.find(u=>u.id===id);if(!person)return;
    const selectedTeam=state.team||demo.topic_team.id;
    clearIdentity();state.token=person.token;state.team=selectedTeam;
    localStorage.setItem('studio-token',person.token);localStorage.setItem('studio-squad',selectedTeam);
    sessionStorage.setItem('songban-demo-actor',person.id);
    try { await load();render();toast('已切换到模拟成员：'+person.name); }
    catch(error){toast(error.message);}
  }
  let demoBusy=false;
  async function advance(action){
    if(demoBusy)return;demoBusy=true;fill();
    try{const result=await api('/demo/advance',{team_id:state.team,action});await refresh(true);toast(result.notice);}
    catch(error){toast(error.message);}
    finally{demoBusy=false;fill();}
  }
  document.addEventListener('DOMContentLoaded', async () => {
    try {
      const response = await fetch('/static/songban-demo-content.json', {cache:'no-store'});
      if (!response.ok) throw new Error('无法读取演示案例');
      story = await response.json();
      demo.content = story;
    } catch (error) { toast('演示案例加载失败，请刷新重试：'+error.message); return; }
    document.body.classList.add('songban-demo');
    const bar=document.createElement('aside');bar.className='demo-toolbar';bar.setAttribute('aria-label','全流程演示工具');
    bar.innerHTML=`<div class="demo-description"><strong>全流程演示 · 5 人小队</strong><span>${demo.parent_reports?'成员与参赛素材为模拟；家长报告调用真实模型。':'成员、讨论和回复均为模拟；文字已预填，可直接点击继续。'}</span></div><div class="demo-controls"><label>演示场景<select id="demo-scene"><option value="${demo.topic_team.id}">从选题到领取任务</option><option value="${demo.team.id}">已有成果与验收进度</option></select></label><label>演示成员<select id="demo-role">${demo.users.map(u=>`<option value="${u.id}">${u.name} · ${u.role}</option>`).join('')}</select></label><label>演示步骤<select id="demo-step">${steps.map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><button type="button" id="demo-fill">补入示例</button><a href="#/onboarding">从兴趣开始 →</a></div><div id="demo-topic-controls" class="demo-topic-controls" hidden><span>模拟队友操作</span><button type="button" data-demo-action="upload">填入 5 人讨论</button><button type="button" data-demo-action="confirm_next">下一位队友确认</button><button type="button" data-demo-action="vote_others">模拟队友投票</button><button type="button" data-demo-action="claim_others">模拟队友领取任务</button><small>本人确认、投票和队长定方向使用页面原有按钮。</small></div>`;
    document.body.prepend(bar);
    document.querySelector('#demo-role').onchange=e=>void switchActor(e.target.value);
    document.querySelector('#demo-step').onchange=e=>go(e.target.value);
    document.querySelector('#demo-scene').onchange=async e=>{state.team=e.target.value;state.personal=false;sessionStorage.removeItem('songban-personal');localStorage.setItem('studio-squad',state.team);state.epoch++;await load();go(state.team===demo.topic_team.id?'direction':'tasks');};
    bar.querySelectorAll('[data-demo-action]').forEach(button=>button.onclick=()=>advance(button.dataset.demoAction));
    document.querySelector('#demo-fill').onclick=()=>{
      root.querySelectorAll('input,textarea,select').forEach(field=>{if(!field.value.trim()){prepared.delete(field);edited.delete(field);}});fill();toast('空白输入已补入示例，已有文字已保留。');
    };
    // Real edits (including deliberately clearing a field) take priority over defaults.
    for (const event of ['input','change']) root.addEventListener(event,e=>{
      if(e.isTrusted && e.target.matches('input,textarea,select')) edited.add(e.target);
    },true);
    let frame=0;
    new MutationObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(fill);}).observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});
    // Native form resets and React draft clears can change .value without a DOM mutation.
    // Retry only empty/generated values; this neither submits nor changes saved records.
    setInterval(()=>{if(!document.hidden)fill();},750);
    fill();
  });
})();
