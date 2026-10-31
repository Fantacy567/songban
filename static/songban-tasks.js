'use strict';
// Both pages read the same server snapshot; task state is only written through /reports.
function taskNow(member) {
  const task=member.current_task;
  if(task)return ({in_progress:'正在做：',blocked:'受阻：',changes_requested:'需要修改：',next:'下一步：',waiting_review:'等待检查：'}[task.kind]||'任务：')+task.title;
  if(!member.total)return '还没有分配任务';
  return member.all_waiting?'等待前置成果通过检查':'本人的任务已完成';
}
function taskMeter(member,large=false) {
  return `<div class="task-meter ${large?'task-meter-large':''}" data-task-meter="${esc(member.user_id)}"><div class="task-meter-label"><span data-task-count>${member.completed} / ${member.total} 项已完成</span><strong data-task-percent>${member.percent}%</strong></div><progress max="100" value="${member.percent}" aria-label="${esc(member.name)}的本人任务完成进度" aria-valuetext="${member.completed}/${member.total} 项本人完成，${member.accepted}项已验收"></progress></div>`;
}
function updateTaskMeters(data) {
  for(const member of data.task_progress||[]){
    root.querySelectorAll('[data-task-meter]').forEach(meter=>{
      if(meter.dataset.taskMeter!==member.user_id)return;
      meter.querySelector('progress').value=member.percent;
      meter.querySelector('progress').setAttribute('aria-valuetext',`${member.completed}/${member.total} 项本人完成，${member.accepted}项已验收`);
      meter.querySelector('[data-task-count]').textContent=`${member.completed} / ${member.total} 项已完成`;
      meter.querySelector('[data-task-percent]').textContent=member.percent+'%';
    });
    root.querySelectorAll('[data-task-now]').forEach(el=>{if(el.dataset.taskNow===member.user_id)el.textContent=taskNow(member);});
    const accepted=$('#my-task-accepted');if(accepted&&member.user_id===data.me.id)accepted.textContent=`其中 ${member.accepted} 项已通过同伴检查`;
  }
}
function taskTabs(active){return `<nav class="task-view-tabs" aria-label="任务视图"><a href="#/work" ${active==='mine'?'aria-current="page"':''}>个人任务</a><a href="#/team-work" ${active==='team'?'aria-current="page"':''}>团队任务</a></nav>`;}
function taskBoardFooter(){return `<p class="caption task-board-caption">进度按当前安排中本人已完成的任务数计算；待检查计入本人完成，退回修改后重新计入未完成。正式交付仍需同伴检查。</p><div class="action-row"><a class="text-link" href="#/division">查看已确认的分工</a><a class="text-link" href="#/delivery">查看交付与验收</a></div>`;}
function taskDone(task){return task.status==='reported_done'&&['waiting_review','accepted'].includes(task.handoff_state);}
function myTaskCard(task,index){
  const done=taskDone(task),waiting=task.waiting_on?.length;
  const status=task.handoff_state==='accepted'?'已验收':done?'已完成 · 待检查':task.handoff_state==='changes_requested'?'退回修改':task.handoff_state==='dependency_changed'?'前置成果已变化':labels[task.status]||'尚未开始';
  return `<article class="card personal-task ${done?'personal-task-done':''}" id="task-${esc(task.key)}" tabindex="-1"><div class="row spread"><h2>${esc(task.title)}</h2><span class="tag ${done?'green':''}">${esc(status)}</span></div><p class="task-acceptance"><strong>怎样算完成：</strong>${esc(task.acceptance)}</p>${waiting?`<p class="notice">先等待 ${esc(task.waiting_on.join('、'))} 的成果通过检查，再领取并开始。</p>`:''}${task.handoff&&['changes_requested','dependency_changed'].includes(task.handoff_state)?`<p class="notice">${esc(task.handoff.note)}</p>`:''}${task.latest_progress?`<details class="task-last-report"><summary>已保存的成果与进展</summary><p>${esc(task.latest_progress.summary)}</p><pre class="material-source">${esc(task.latest_progress.evidence.join('\n')||'尚未补充成果')}</pre></details>`:''}${!done?`<form id="finish-task-${index}" data-task-key="${esc(task.key)}" class="finish-task-form"><label for="task-evidence-${index}">成果链接或完成说明</label><textarea id="task-evidence-${index}" name="evidence_text" rows="2" maxlength="8000" required placeholder="例如：草图链接，或说明完成了哪些内容" ${waiting?'disabled':''}></textarea><div class="action-row"><button type="submit" class="primary" ${waiting?'disabled':''}>${task.handoff_state==='changes_requested'?'完成修改':'完成这项任务'}</button>${task.status!=='in_progress'?`<button type="button" data-start-task="${esc(task.key)}" ${waiting?'disabled':''}>领取并开始</button>`:''}</div></form>`:`<div class="action-row"><button data-report-task="${esc(task.key)}">${task.handoff_state==='accepted'?'补充新的进展':'补充成果'}</button><button class="ghost" data-reopen-task="${esc(task.key)}">继续修改</button></div>`}</article>`;
}
function notifyTaskSaved(team){try{localStorage.setItem('songban-task-update',JSON.stringify({team,at:Date.now(),nonce:crypto.randomUUID()}));}catch{}}
async function saveTaskReport(task,version,status,evidence=[],eventId=crypto.randomUUID()){
  const team=state.team;
  await api(endpoint('/reports'),{task_key:task.key,plan_version:version,status,event_id:eventId,tool:'个人任务页',origin:'human',summary:(status==='reported_done'?'本人完成：':'正在做：')+task.title,evidence});
  notifyTaskSaved(team);
}
function myTasksPage(){
  const d=state.data,own=(d.active_plan.tasks||[]).filter(t=>t.owner_id===d.me.id);
  const checks=(d.active_plan.tasks||[]).filter(t=>t.owner_id!==d.me.id&&t.handoff_state==='waiting_review'&&!t.waiting_on?.length);
  const member=(d.task_progress||[]).find(m=>m.user_id===d.me.id)||{user_id:d.me.id,name:name(d.me.id),completed:0,total:0,percent:0,accepted:0};
  $('#content').innerHTML=head('个人任务','先做完眼前这一件。','只看自己的任务，完成后队友会看到同一份进度。')+taskTabs('mine')+`<section class="card personal-progress"><div class="row spread"><h2>${esc(member.name)}的任务进度</h2><a class="text-link" href="#/team-work">看看全队</a></div>${taskMeter(member,true)}<div class="row spread"><p class="task-current" data-task-now="${esc(member.user_id)}">${esc(taskNow(member))}</p><p class="caption" id="my-task-accepted">其中 ${member.accepted} 项已通过同伴检查</p></div></section><section id="confirmed-tasks" class="personal-task-list" aria-label="我的具体任务">${own.map(myTaskCard).join('')||`<div class="card empty"><h2>还没有分配给你的任务</h2><p>完成团队分工问答后，内部 AI 会发布你的任务。</p><a href="#/division" class="text-link">开始分工问答</a></div>`}</section>${checks.length?`<section class="card"><h2>队友的成果等你检查</h2>${checks.map(t=>`<p>${esc(name(t.owner_id))}：${esc(t.title)} <button data-peer-check="${esc(t.key)}">检查成果</button></p>`).join('')}</section>`:''}${taskBoardFooter()}<details class="task-ai-support"><summary>和 AI 工作时有新发现？</summary>${connectorInline('development')}</details>`;
  bindConversationEntrances();
  root.querySelectorAll('[data-peer-check]').forEach(b=>b.onclick=()=>openTaskCheck(b.dataset.peerCheck));
  own.forEach((task,index)=>bindForm('#finish-task-'+index,async(form,fd)=>{
    const evidence=String(fd.get('evidence_text')||'').split('\n').map(v=>v.trim()).filter(Boolean);
    if(!evidence.length)throw Error('请补充成果链接或完成说明。');
    if(evidence.length>8||evidence.some(v=>v.length>1000))throw Error('最多填写8条成果，每条不超过1000字。');
    const eventId=form.dataset.eventId||(form.dataset.eventId=crypto.randomUUID());
    await saveTaskReport(task,d.plan_version,'reported_done',evidence,eventId);
    state.drafts.delete(state.team+':'+form.id);form.dataset.dirty='false';await refresh(true);toast('任务已记录为本人完成，团队进度已同步。请队友检查成果。');
  }));
  root.querySelectorAll('[data-start-task],[data-reopen-task]').forEach(button=>button.onclick=async()=>{
    const task=own.find(t=>t.key===(button.dataset.startTask||button.dataset.reopenTask));
    button.disabled=true;
    try{await saveTaskReport(task,d.plan_version,'in_progress',task.latest_progress?.evidence||[]);await refresh(true);toast('正在做的任务已同步给团队。');}catch(error){toast(error.message);button.disabled=false;}
  });
  root.querySelectorAll('[data-report-task]').forEach(button=>button.onclick=()=>openTaskEvidence(button.dataset.reportTask));
}
function openTaskEvidence(key){
  const d=state.data,task=d.active_plan.tasks.find(t=>t.key===key&&t.owner_id===d.me.id);if(!task)return;
  const dialog=modal('补充「'+task.title+'」的成果',`<form id="task-evidence-form"><label for="task-more-evidence">成果链接或完成说明</label><textarea id="task-more-evidence" name="evidence" maxlength="1000" required>${esc((task.latest_progress?.evidence||[]).join('\n').slice(0,1000))}</textarea><button type="submit" class="primary">保存成果，重新等待检查</button></form>`);
  bindForm('#task-evidence-form',async(form,fd)=>{await saveTaskReport(task,d.plan_version,'reported_done',[fd.get('evidence')],form.dataset.eventId||(form.dataset.eventId=crypto.randomUUID()));dialog.close();await refresh(true);toast('成果已更新，需要队友检查本次更新。');});
}
function teamTasksPage(){
  const d=state.data;
  $('#content').innerHTML=head('团队任务','每个人的进展，一眼看清。','页面打开时约每 2 秒同步；当前任务以成员保存的进展为准。')+taskTabs('team')+`<section class="task-member-grid" aria-label="成员任务进度">${(d.task_progress||[]).map(member=>`<button class="task-member-card" data-member-tasks="${esc(member.user_id)}" aria-label="查看${esc(member.name)}的任务"><h2>${esc(member.name)}</h2>${taskMeter(member)}<p class="task-current" data-task-now="${esc(member.user_id)}">${esc(taskNow(member))}</p></button>`).join('')}</section><p class="caption">点击成员名片，可查看任务与检查已提交的成果。</p>${taskBoardFooter()}`;
  root.querySelectorAll('[data-member-tasks]').forEach(button=>button.onclick=()=>openMemberTasks(button.dataset.memberTasks));
}
function openMemberTasks(userId){
  const d=state.data,list=(d.active_plan.tasks||[]).filter(task=>task.owner_id===userId);
  const dialog=modal(name(userId)+'的任务',tasks(list,true));
  dialog.querySelectorAll('[data-check-task]').forEach(button=>button.onclick=()=>{const key=button.dataset.checkTask;dialog.close();openTaskCheck(key);});
  dialog.querySelectorAll('[data-report-task]').forEach(button=>button.onclick=()=>{const key=button.dataset.reportTask;dialog.close();go('work');const target=document.getElementById('task-'+key);target?.scrollIntoView({block:'center'});target?.querySelector('textarea')?.focus();});
}
