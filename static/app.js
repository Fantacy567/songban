"use strict";
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const app = $("#app");
const sessionKey = "hackathon-collab-session-v1";
let session = null;
try { session = JSON.parse(localStorage.getItem(sessionKey) || "null"); } catch { localStorage.removeItem(sessionKey); }
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.get("project") && fragment.get("token")) {
  session = {project: fragment.get("project"), token: fragment.get("token")};
  localStorage.setItem(sessionKey, JSON.stringify(session));
  history.replaceState(null, "", location.pathname);
}
let workspace = null, activeTab = "sources", draft = null, recap = null, busy = false, pendingAction = null;
let newMembers = 2, noticeTimer, invites = new Map(), discovery = null;
const tabNames = {sources:"资料与讨论",plan:"分工确认",tasks:"共享任务",recap:"交付与复盘",events:"过程记录",model:"模型接入"};
const statuses = {todo:"待开始",in_progress:"进行中",blocked:"已阻塞",review:"待验收",accepted:"已通过"};
const date = value => new Date(value).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});
const localDateInput = value => {const d = new Date(value); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0,16);};
let fieldCounter = 0;
const field = (label, control) => {
  const found = control.match(/\bid="([^"]+)"/), id = found ? found[1] : `field-${++fieldCounter}`;
  if (!found) control = control.replace(/<(input|select|textarea)\b/, `<$1 id="${id}"`);
  return `<div class="field"><label for="${id}">${label}</label>${control}</div>`;
};
const memberName = id => workspace.members.find(m => m.id === id)?.name || "未知成员";

function notify(message, error = false) {
  const node = $("#notice"); node.textContent = message; node.className = error ? "error" : ""; node.hidden = false;
  clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { node.hidden = true; }, error ? 12000 : 5000);
}

async function api(path, options = {}) {
  const headers = { ...(options.body ? {"Content-Type":"application/json"} : {}), ...(session ? {Authorization:`Bearer ${session.token}`} : {}), ...options.headers};
  let response;
  try {response = await fetch(path, {...options, headers});} catch {throw new Error("无法连接后端，请检查服务是否仍在运行。输入内容尚在页面中。");}
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = new Error(data.error?.message || `请求失败（${response.status}）`);
    error.code = data.error?.code; error.status = response.status;
    const details = data.error?.details;
    if (Array.isArray(details)) error.message += "\n" + details.slice(0,4).map(d => d.member ? `${d.member}：计划 ${d.planned_hours}h / 可用 ${d.available_hours}h` : `${d.field}：${d.reason}`).join("\n");
    throw error;
  }
  return response;
}

async function run(action) {
  if (busy) return;
  busy = true; $$('button').forEach(b => {b.dataset.wasDisabled = b.disabled ? "1" : "0"; b.disabled = true;});
  try {await action();} catch (error) {notify(error.message, true);} finally {
    busy = false;
    $$('button').forEach(b => {if (b.dataset.wasDisabled === "0") b.disabled = false; delete b.dataset.wasDisabled;});
  }
}

async function refresh() {
  workspace = await (await api(`/api/projects/${session.project}`)).json();
  const selected = workspace.project.active_proposal_id ? workspace.proposals.find(p => p.id === workspace.project.active_proposal_id) : workspace.proposals[0];
  draft = selected ? structuredClone(selected) : null;
  if (activeTab === "recap") recap = await (await api(`/api/projects/${session.project}/recap`)).json();
  render();
}

function welcome() {
  const end = localDateInput(new Date(Date.now() + 24*3600000));
  app.innerHTML = `<div class="welcome"><header class="welcome-top"><div class="brand"><span class="mark">∴</span>赛内协作</div><span class="muted">独立成员入口 · 本地持久化 · 结果经人工确认</span></header>
    <div class="intro"><section class="intro-copy"><div class="eyebrow">From discussion to delivery</div><h1>把讨论，<br>推进成作品。</h1><p>明确目标，确认分工，带着可以验收的任务开始下一步。</p><div class="steps">
      <div class="step"><span class="step-number">01</span><div><h3>先留下共同依据</h3><p class="muted">赛事规则、团队讨论和成员可用时间。</p></div></div>
      <div class="step"><span class="step-number">02</span><div><h3>建议经过团队确认</h3><p class="muted">每项任务都有负责人、原文依据和验收标准。</p></div></div>
      <div class="step"><span class="step-number">03</span><div><h3>用成果推动下一步</h3><p class="muted">交付后请另一成员验收，过程记录用于复盘。</p></div></div></div><p class="muted" style="margin-top:35px"><a href="/workflow" target="_blank" rel="noopener">查看业务流程 ↗</a></p></section>
    <section class="panel create-card"><div class="section-head"><h2>创建团队工作区</h2><span class="badge">首版 · 2—8 人</span></div><form id="create-form">
      <div class="grid2">${field("项目名称",'<input id="project-name" name="project_name" required maxlength="100" placeholder="例如：赛内协作助手">')}${field("赛事截止时间（本地时区）",`<input id="deadline" type="datetime-local" required value="${end}">`)}</div>
      <div id="member-inputs">${memberEditor(0)}${memberEditor(1)}</div>
      <div class="form-foot"><button type="button" class="ghost small" id="add-member">＋ 添加成员</button><button type="submit" id="create-project">创建工作区 →</button></div>
      <p class="muted" style="margin-top:18px">首位成员为队长。创建后会提供各自的私密入口；这是演练版访问方式，无真实账号系统。</p>
    </form></section></div></div>`;
  $("#add-member").onclick = () => {if(newMembers >= 8) return; $("#member-inputs").insertAdjacentHTML("beforeend", memberEditor(newMembers++)); $("#add-member").disabled = newMembers >= 8;};
  $("#create-form").onsubmit = event => {event.preventDefault(); run(async () => {
    const members = Array.from({length:newMembers}, (_, i) => ({name:$(`#member-name-${i}`).value, role:$(`#member-role-${i}`).value, skills:$(`#member-skills-${i}`).value, available_hours:Number($(`#member-hours-${i}`).value)}));
    const payload = {name:$("#project-name").value, deadline:new Date($("#deadline").value).toISOString(), members};
    const created = await (await api("/api/projects", {method:"POST", body:JSON.stringify(payload)})).json();
    session = {project:created.project_id, token:created.invites[0].access_token};
    localStorage.setItem(sessionKey, JSON.stringify(session));
    invites = new Map(created.invites.map(m => [m.member_id, m.access_token]));
    await refresh(); showEntries(); notify("工作区已创建。请先保存队长入口，再分别发送成员入口。");
  });};
}

function memberEditor(i) {
  return `<div class="member-edit"><div class="member-top"><h3>${i === 0 ? "你 · 队长" : `成员 ${i+1}`}</h3><span class="muted">工时由本人填写</span></div><div class="grid2">${field("姓名",`<input id="member-name-${i}" required maxlength="40" placeholder="${i===0?"你的姓名":"成员姓名"}">`)}${field("角色",`<input id="member-role-${i}" required maxlength="80" placeholder="${i===0?"产品 / 后端":"前端 / 设计"}">`)}</div><div class="grid2">${field("能力与工具",`<input id="member-skills-${i}" required maxlength="500" placeholder="${i===0?"Python、AI 辅助开发":"JavaScript、界面实现"}">`)}${field("本场可投入工时",`<input id="member-hours-${i}" type="number" required min="0.25" max="168" step="0.25" value="4">`)}</div></div>`;
}

function render() {
  if (!workspace) {welcome(); return;}
  const p = workspace.project, locked = !!p.active_proposal_id;
  const hours = Math.max(0, (new Date(p.deadline) - Date.now()) / 3600000).toFixed(1);
  const phaseLabel = {preparing:"准备与确认",executing:"执行与验收",ready:"必须任务已通过"}[p.phase];
  app.innerHTML = `<div class="app-shell"><aside class="sidebar"><div class="brand"><span class="mark">∴</span>赛内协作</div><div><div class="side-heading">团队工作台</div><nav class="nav">${Object.entries(tabNames).map(([key,name],i)=>`<button data-tab="${key}" class="${activeTab===key?"active":""}"><span class="nav-no">0${i+1}</span>${name}</button>`).join("")}</nav></div><div class="side-bottom"><span class="muted">首版聚焦一次确认后的执行。<br>资料与任务都来自当前工作区。</span><a href="/workflow" target="_blank" rel="noopener">业务流程 ↗</a><button id="logout" class="ghost small">离开此工作区</button></div></aside>
    <main class="main"><header class="topline"><span class="identity">${esc(workspace.me.name)}<span>${workspace.me.captain?"队长":"成员"} · ${esc(workspace.me.role)}</span></span><div class="actions">${workspace.me.captain?'<button id="team-entries" class="ghost small">成员入口</button>':''}<button id="refresh" class="ghost small">刷新进度</button><span class="badge ${workspace.model_configured?"":"gray"}">${workspace.model_configured?"模型已配置":"规则演练可用"}</span></div></header>
    <section class="hero"><div><div class="eyebrow">Team workspace</div><h1>${esc(p.name)}</h1><div class="hero-meta"><span class="badge">${phaseLabel}</span><span>${workspace.members.length} 名成员 · ${workspace.tasks.length} 项任务</span></div></div><div class="deadline"><strong>${hours} <small>小时</small></strong><small>距截止 · ${date(p.deadline)}</small></div></section>
    <div id="content">${({sources:sourceView,plan:planView,tasks:taskView,recap:recapView,events:eventView,model:modelView}[activeTab])()}</div>
    </main></div>`;
  const nav = $('.nav'), selectedNav = $('.nav button.active');
  if (nav.scrollWidth > nav.clientWidth && selectedNav) {
    const bounds = nav.getBoundingClientRect(), selected = selectedNav.getBoundingClientRect();
    if (selected.left < bounds.left) nav.scrollLeft -= bounds.left - selected.left;
    else if (selected.right > bounds.right) nav.scrollLeft += selected.right - bounds.right;
  }
  $$('[data-tab]').forEach(b => b.onclick = () => run(async () => {activeTab = b.dataset.tab; await refresh();}));
  $("#refresh").onclick = () => run(async () => {await refresh(); notify("已从后端读取最新进度。");});
  if($("#logout")) $("#logout").onclick = () => {if(confirm("请确认已保存自己的成员入口。离开只清除此浏览器的入口，不删除项目。")){localStorage.removeItem(sessionKey);session=null;workspace=null;draft=null;recap=null;discovery=null;invites.clear();activeTab="sources";welcome();}};
  if($("#team-entries")) $("#team-entries").onclick = showEntries;
  if(activeTab === "sources") bindSources();
  if(activeTab === "plan") bindPlan();
  if(activeTab === "tasks") bindTasks();
  if(activeTab === "model") bindModel();
  if(activeTab === "recap" && $("#export")) $("#export").onclick = () => run(exportReport);
}

function sourceView() {
  const locked = !!workspace.project.active_proposal_id;
  return `<div class="workspace-grid"><section class="panel"><div class="section-head"><div><h2>共同依据</h2><p class="muted">先录入规则和讨论，之后每项建议都能回看原文。</p></div><span class="badge gray">${workspace.sources.length} 份</span></div>
    ${locked?'<div class="note">正式方案已确认，首版冻结资料与分工。执行问题可在任务中记录阻塞或退回。</div>':`<form id="source-form"><div class="grid2">${field("来源类型",'<select id="source-kind"><option value="rules">赛事规则</option><option value="discussion">团队讨论</option></select>')}${field("资料标题",'<input id="source-title" required maxlength="100" placeholder="例如：评分与提交要求">')}</div>${field("原文内容",'<textarea id="source-body" rows="7" required maxlength="20000" placeholder="粘贴真实资料，或明确标注为演练示例。"></textarea>')}<div class="actions"><button type="submit">保存原文</button><button type="button" id="sample-sources" class="ghost">添加两份演练原文</button></div><p class="muted" style="margin-top:12px">仅上传团队有权使用的讨论。原文不可覆盖，确认前可追加；新增资料会使旧草案失效。</p></form>`}
    <div>${workspace.sources.map(s=>`<article class="source-item"><div class="source-title"><span class="badge gray">${s.kind==="rules"?"规则":"讨论"}</span><h3>${esc(s.title)}</h3></div><details><summary>查看原文 · ${s.body.length} 字</summary><p class="source-body">${esc(s.body)}</p></details></article>`).join("")}</div></section>
    <aside class="stack"><section class="panel"><h2>本场成员</h2><div class="team-list">${workspace.members.map(m=>`<div class="person"><div>${esc(m.name)} ${m.captain?'<span class="badge gray">队长</span>':''}<small>${esc(m.role)} · ${esc(m.skills)}</small></div><span>${m.available_hours}h</span></div>`).join("")}</div></section><section class="panel"><h3>下一步：分工确认</h3><p class="muted" style="margin:12px 0">规则和讨论至少各一份。选择本地规则演练或真实模型生成草案，核对后由队长确认。</p><button class="ghost" id="go-plan">去核对方案 →</button></section></aside></div>`;
}

function bindSources() {
  $("#go-plan").onclick = () => run(async()=>{activeTab="plan";await refresh();});
  if(!$("#source-form")) return;
  $("#source-form").onsubmit = event => {event.preventDefault();run(async()=>{
    const body={kind:$("#source-kind").value,title:$("#source-title").value,body:$("#source-body").value};
    await api(`/api/projects/${session.project}/sources`,{method:"POST",body:JSON.stringify(body)});await refresh();notify("原文已保存，旧草案需重新生成。");
  });};
  $("#sample-sources").onclick = () => run(async()=>{
    if(workspace.sources.length && !confirm("将追加两份明确标注的演练原文，旧草案会失效。继续吗？")) return;
    for(const source of [{kind:"rules",title:"演练示例 · 评分与交付",body:"【演练示例，非真实赛事公告】\n评分关注用户价值、创新和实现质量。需提交可运行演示与项目说明；演示必须清楚标明真实能力和替身。"},{kind:"discussion",title:"演练示例 · 团队讨论",body:"【演练示例，非自动监听结果】\n目标：让两名成员共同推进一个能验收的核心流程。\n决定：首版先完成资料录入、分工确认、共享任务和成员验收。\n待确认：实际前端与后端的请求字段需要双方确认。\n任务：实现资料录入和任务状态接口 2h\n任务：完成分工确认和任务板页面 2h\n待办：前后端联调并走通一次完整流程 1h\nTODO: 加分项：截止前 2 小时提醒未完成任务\n演示时要不要现场录入一段真实讨论？"}]) await api(`/api/projects/${session.project}/sources`,{method:"POST",body:JSON.stringify(source)});
    await refresh();notify("两份演练原文已保存，来源标签会持续保留。");
  });
}

function planView() {
  const locked=!!workspace.project.active_proposal_id, captain=!!workspace.me.captain;
  const ready=workspace.sources.some(s=>s.kind==="rules")&&workspace.sources.some(s=>s.kind==="discussion");
  const generate = !locked?`<section class="panel"><div class="section-head"><div><h2>先有建议，再共同确认</h2><p class="muted">队长核对目标、工时和依赖，确认后才生成正式任务。</p></div></div><div class="generation"><button id="generate-rules" ${!captain||!ready?'disabled':''}>离线规则生成<small>读取讨论中的“任务：/待办：/- [ ]”行 · 不调用大模型</small></button><button id="generate-model" class="ghost" ${!captain||!ready?'disabled':''}>模型优先生成<small>${esc(workspace.current_model?.name||'DeepSeek-V4-Pro')} · ${esc(workspace.current_model?.model_id||'deepseek-v4-pro')}<br>${workspace.model_configured?'模型不可用时自动改用离线规则，并标注原因':'尚未配置密钥 · 将直接使用离线规则并标注'}</small></button></div><p class="muted">${!captain?'等待队长生成并确认；你可以查看原文和草案。':!ready?'请先各保存一份规则和讨论。':'讨论里按“任务：内容 @成员 2h”写，离线规则就能提取负责人和工时；没有任务行时使用角色模板。结果都需人工核对。'}</p></section>`:'';
  if(!draft) return `<div class="stack">${generate}<div class="note">尚无草案。正式任务会在队长确认后出现。</div></div>`;
  const disabled = locked||!captain||draft.stale;
  return `<div class="stack">${generate}<section class="panel"><div class="section-head"><div><h2>${locked?'已确认方案':'待确认草案'}</h2><p class="muted">${esc(draft.source_label)} · 版本 ${draft.version}</p></div><span class="badge ${draft.stale?'amber':''}">${draft.stale?'资料已更新，需重新生成':locked?'已确认':'需人工确认'}</span></div>
    ${draft.response_model_id?`<p class="muted" style="margin-bottom:15px">服务响应模型 ID：${esc(draft.response_model_id)}（服务商返回标识）</p>`:''}
    ${draft.fallback_reason?`<div class="note warning" style="margin-bottom:20px">模型未生成本草案：${esc(draft.fallback_reason)}。以下为离线规则结果，不是大模型建议。</div>`:''}
    ${draft.stale?'<div class="note warning" style="margin-bottom:20px">这份草案引用的资料已过期，请重新生成，旧草案不可确认。</div>':''}
    ${draft.capacity_warnings?.length?`<div class="note warning" style="margin-bottom:20px">工时超出预算：${draft.capacity_warnings.map(w=>`${esc(w.member)} ${w.planned_hours}h / ${w.available_hours}h`).join("；")}。调整后才能确认。</div>`:''}
    <form id="draft-form"><fieldset ${disabled?'disabled':''} style="border:0;padding:0;margin:0"><div class="field"><label for="draft-goal">本次目标</label><textarea id="draft-goal" rows="2" maxlength="500" required>${esc(draft.content.goal)}</textarea></div><div class="draft-intro">${field('已决定（每行一项）',`<textarea id="draft-decisions" rows="3">${esc(draft.content.decisions.join("\n"))}</textarea>`)}${field('仍待确认（每行一项）',`<textarea id="draft-questions" rows="3">${esc(draft.content.open_questions.join("\n"))}</textarea>`)}</div>${field('风险与提醒（每行一项）',`<textarea id="draft-risks" rows="3">${esc(draft.content.risks.join("\n"))}</textarea>`)}<h3>任务建议 · ${draft.content.tasks.length} 项</h3><div id="draft-tasks">${draft.content.tasks.map(taskEditor).join("")}</div></fieldset>
    ${!disabled?`<div class="draft-footer"><button type="button" id="add-task" class="ghost" ${draft.content.tasks.length>=12?'disabled':''}>＋ 增加任务</button><div class="actions"><button type="button" id="save-draft" class="ghost">保存草案</button><button type="submit" id="confirm-plan">保存并确认分工 →</button></div></div><p class="muted" style="margin-top:14px">确认后首版冻结资料与分工，请先核对所有待确认事项和预算。</p>`:''}</form></section></div>`;
}

function taskEditor(t) {
  const k=esc(t.key), locked=!!workspace.project.active_proposal_id||!workspace.me.captain||draft.stale;
  return `<article class="draft-task" data-draft-task="${k}"><div class="task-editor-top"><h3>${k}</h3>${!locked?`<button type="button" class="ghost small" data-remove-task="${k}" ${draft.content.tasks.length<=1?'disabled':''}>移除</button>`:''}</div>
    <div class="grid2">${field('任务名称',`<input data-field="title" value="${esc(t.title)}" required maxlength="120">`)}${field('负责人',`<select data-field="owner_id">${workspace.members.map(m=>`<option value="${esc(m.id)}" ${m.id===t.owner_id?'selected':''}>${esc(m.name)} · ${esc(m.role)}</option>`).join("")}</select>`)}</div>
    <div class="grid3">${field('预计工时',`<input data-field="estimated_hours" type="number" min="0.25" max="48" step="0.25" required value="${t.estimated_hours}">`)}${field('优先级',`<select data-field="priority"><option value="must" ${t.priority==='must'?'selected':''}>必须完成</option><option value="should" ${t.priority==='should'?'selected':''}>可选</option></select>`)}${field('任务截止（本地时区）',`<input data-field="due_at" type="datetime-local" required value="${localDateInput(t.due_at)}">`)}</div>
    ${field('验收标准',`<textarea data-field="acceptance" rows="2" maxlength="1000" required>${esc(t.acceptance)}</textarea>`)}${field('前置任务编号（逗号分隔，例如 T1,T2）',`<input data-field="depends_on" value="${esc(t.depends_on.join(','))}" placeholder="无依赖则留空">`)}
    <details><summary>核对原文依据 · ${t.evidence.length} 处引用</summary>${t.evidence.map((e,i)=>`<div class="cite"><label>来源</label><select data-source-index="${i}">${workspace.sources.map(s=>`<option value="${esc(s.id)}" ${s.id===e.source_id?'selected':''}>${esc(s.title)}</option>`).join("")}</select><label style="margin-top:10px">连续原文引用</label><textarea data-quote-index="${i}" rows="2" required maxlength="300">${esc(e.quote)}</textarea></div>`).join("")}</details></article>`;
}

function collectDraft() {
  const lines = id => $(id).value.split("\n").map(s=>s.trim()).filter(Boolean);
  return {goal:$("#draft-goal").value,decisions:lines("#draft-decisions"),open_questions:lines("#draft-questions"),risks:lines("#draft-risks"),tasks:$$('[data-draft-task]').map(node=>{
    const current=draft.content.tasks.find(t=>t.key===node.dataset.draftTask), task={...current};
    $$('[data-field]',node).forEach(input=>{const key=input.dataset.field;task[key]=key==='estimated_hours'?Number(input.value):key==='depends_on'?input.value.split(/[,，]/).map(s=>s.trim()).filter(Boolean):key==='due_at'?new Date(input.value).toISOString():input.value;});
    task.evidence=current.evidence.map((e,i)=>({source_id:$(`[data-source-index="${i}"]`,node).value,quote:$(`[data-quote-index="${i}"]`,node).value})); return task;
  })};
}

async function saveDraft() {
  const content=collectDraft();
  const saved=await (await api(`/api/projects/${session.project}/proposals/${draft.id}`,{method:"PUT",body:JSON.stringify({expected_version:draft.version,content})})).json();
  draft={...saved,stale:false}; return saved;
}

function bindPlan() {
  for(const [selector,mode] of [["#generate-rules","local_rules"],["#generate-model","auto"]]) if($(selector)) $(selector).onclick=()=>run(async()=>{
    if(mode==='auto'&&workspace.model_configured&&!confirm("将把本项目的规则、讨论和成员信息发送给所选模型服务，生成建议。继续吗？")) return;
    notify(mode==='auto'&&workspace.model_configured?"正在请求模型，请等待，资料已保存。":"正在用离线规则生成草案。");
    const created=await(await api(`/api/projects/${session.project}/proposals`,{method:"POST",body:JSON.stringify({mode})})).json();await refresh();
    notify(created.fallback_reason?`${created.fallback_reason}，已改用离线规则生成草案，请核对。`:"草案已生成，请核对后再确认。",!!created.fallback_reason);
  });
  if(!$("#save-draft")) return;
  $("#save-draft").onclick=()=>run(async()=>{if(!$("#draft-form").reportValidity())return;await saveDraft();await refresh();notify("草案已保存，尚未生成正式任务。");});
  $("#draft-form").onsubmit=event=>{event.preventDefault();run(async()=>{
    if(!confirm("确认目标、工时、依赖和待确认事项已核对？确认后首版将冻结资料与分工。"))return;
    await saveDraft();
    try {await api(`/api/projects/${session.project}/proposals/${draft.id}/confirm`,{method:"POST",body:JSON.stringify({expected_version:draft.version})});}
    catch(error){await refresh();throw error;}
    activeTab="tasks";await refresh();notify("分工已确认，正式任务已生成。");
  });};
  $("#add-task").onclick=()=>{
    try {draft.content=collectDraft();let n=1;while(draft.content.tasks.some(t=>t.key===`T${n}`))n++;const source=workspace.sources[0];draft.content.tasks.push({key:`T${n}`,title:"",owner_id:workspace.me.id,acceptance:"",estimated_hours:1,priority:"must",due_at:workspace.project.deadline,depends_on:[],evidence:[{source_id:source.id,quote:source.body.slice(0,100)}]});render();}catch(error){notify("请先填好当前任务的日期等必填内容。",true);}
  };
  $$('[data-remove-task]').forEach(b=>b.onclick=()=>{
    if(!confirm("移除此任务，同时移除其他任务对它的依赖？保存草案后才生效。"))return;
    try {draft.content=collectDraft();draft.content.tasks=draft.content.tasks.filter(t=>t.key!==b.dataset.removeTask);draft.content.tasks.forEach(t=>t.depends_on=t.depends_on.filter(k=>k!==b.dataset.removeTask));render();}catch{notify("请先填好当前任务的日期等必填内容。",true);}
  });
}

function taskView() {
  if(!workspace.tasks.length) return '<section class="panel"><h2>还没有正式任务</h2><p class="muted" style="margin-top:12px">请先由队长在“分工确认”中核对并确认草案。</p></section>';
  const lanes=[['待开始',['todo']],['推进中',['in_progress','blocked']],['待验收',['review']],['已通过',['accepted']]];
  return `<div class="section-head"><div><h2>一起推进，交叉验收</h2><p class="muted">负责人提交成果后，由另一成员验收；刷新读取团队最新状态。</p></div><span class="badge gray">${workspace.tasks.filter(t=>t.status==='accepted').length} / ${workspace.tasks.length} 已通过</span></div><div class="board">${lanes.map(([name,states])=>{const items=workspace.tasks.filter(t=>states.includes(t.status));return `<section class="lane"><div class="lane-head">${name}<span>${items.length}</span></div>${items.length?items.map(taskCard).join(''):'<div class="quiet">暂无任务</div>'}</section>`;}).join('')}</div>`;
}

function taskCard(t) {
  const own=t.owner_id===workspace.me.id, deps=t.depends_on.map(id=>workspace.tasks.find(v=>v.id===id)).filter(Boolean), pending=deps.filter(v=>v.status!=='accepted');
  let controls='';
  const button=(action,label,disabled=false,ghost=false)=>`<button data-action="${action}" data-task="${esc(t.id)}" ${disabled?'disabled':''} class="${ghost?'ghost':''}">${label}</button>`;
  if(own&&t.status==='todo') controls=button('start',pending.length?'等待前置任务验收':'开始任务',!!pending.length);
  if(own&&t.status==='in_progress') controls=button('submit','提交成果')+button('block','记录阻塞',false,true);
  if(own&&t.status==='blocked') controls=button('resume','解除阻塞并继续',!!pending.length);
  if(t.status==='review') controls=own?'<span class="muted">等待另一位成员验收</span>':button('accept','验收通过')+button('return','退回修改',false,true);
  if(t.status==='accepted') controls=`<span class="muted">${esc(memberName(t.reviewed_by))} 已验收</span>`;
  return `<article class="task-card" data-task-card="${esc(t.task_key)}" data-status="${esc(t.status)}"><div class="actions"><span class="badge ${t.priority==='must'?'':'gray'}">${t.priority==='must'?'必须':'可选'}</span><span class="muted">${esc(t.task_key)} · v${t.version}</span>${t.status==='blocked'?'<span class="badge amber">阻塞</span>':''}</div><h3>${esc(t.title)}</h3><div class="task-meta"><span>${esc(memberName(t.owner_id))}${own?' · 你':''}</span><span>${t.estimated_hours}h</span></div><p class="task-acceptance">${esc(t.acceptance)}</p><p class="muted" style="font-size:11px;margin-top:10px">截止 ${date(t.due_at)}${deps.length?`<br>依赖 ${deps.map(v=>esc(v.task_key)).join('、')}${pending.length?'（尚未全部验收）':'（已通过）'}`:''}</p>
    ${t.block_reason&&t.status==='blocked'?`<div class="task-note blocked">阻塞原因：${esc(t.block_reason)}</div>`:''}${t.deliverable?`<div class="task-note">成果：${esc(t.deliverable)}</div>`:''}${t.review_note?`<div class="task-note">验收意见：${esc(t.review_note)}</div>`:''}
    <details style="margin-top:10px"><summary>原文依据 · ${t.evidence.length} 处</summary>${t.evidence.map(e=>`<p class="cite">${esc(workspace.sources.find(s=>s.id===e.source_id)?.title)}<br>${esc(e.quote)}</p>`).join('')}</details>${controls?`<div class="task-controls">${controls}</div>`:''}</article>`;
}

function bindTasks() {
  $$('[data-action]').forEach(b=>b.onclick=()=>{
    const task=workspace.tasks.find(t=>t.id===b.dataset.task), action=b.dataset.action;
    if(['start','resume'].includes(action))return run(()=>sendAction(task,action,''));
    pendingAction={task,action};
    const text={block:['记录阻塞','当前遇到什么问题？'],submit:['提交成果','成果与验收标准的对应说明（可附地址）'],accept:['验收通过','验收说明（可选）'],return:['退回修改','需要修改的具体问题（必填）']}[action];
    $('#action-heading').textContent=text[0];$('#action-label').textContent=text[1];$('#action-note').value='';$('#action-note').required=action!=='accept';$('#action-dialog').showModal();
  });
}

async function sendAction(task,action,note) {
  await api(`/api/projects/${session.project}/tasks/${task.id}/actions`,{method:'POST',body:JSON.stringify({expected_version:task.version,action,note})});
  $('#action-dialog').close();pendingAction=null;await refresh();notify('任务状态已保存，队友刷新后可看到。');
}

function recapView() {
  if(!recap)return '<section class="panel"><h2>正在读取复盘…</h2></section>';
  const s=recap.stats;
  return `<section class="panel"><div class="section-head"><div><h2>${recap.ready?'核心成果，已通过验收。':'先把必须任务推进到验收。'}</h2><p class="muted">${esc(recap.source_label)}</p></div><button id="export" class="ghost">导出 Markdown</button></div><div class="note ${recap.ready?'':'warning'}">${recap.ready?'所有必须任务已通过；请继续人工核对赛规、提交文件和入口。':'当前尚不可交付。提交成果后，还需要另一成员通过验收。'}</div><div class="metrics"><div class="metric"><strong>${s.must_accepted}/${s.must_total}</strong><small>必须任务已验收</small></div><div class="metric"><strong>${s.accepted}/${s.total}</strong><small>全部任务已验收</small></div><div class="metric"><strong>${s.block_events}</strong><small>阻塞记录次数</small></div><div class="metric"><strong>${s.return_events}</strong><small>验收退回次数</small></div></div><h3>交付核对清单</h3>${recap.checklist.map(t=>`<div class="check-item"><span class="check-dot ${t.accepted?'yes':''}">${t.accepted?'✓':'·'}</span><div><h3>${esc(t.title)} <span class="muted">${t.required?'必须':'可选'}</span></h3><p class="muted">验收：${esc(t.acceptance)}</p><p class="muted">成果：${esc(t.deliverable||'尚未提交')}</p></div></div>`).join('')}<h3 style="margin-top:24px">根据本次记录，下一次可以练什么</h3><ul class="suggestions">${recap.suggestions.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></section>`;
}

async function exportReport() {
  const response=await api(`/api/projects/${session.project}/export`), blob=await response.blob(), url=URL.createObjectURL(blob), a=document.createElement('a');
  a.href=url;a.download='hackathon-recap.md';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('已导出当前任务、资料原文与过程记录。');
}

function eventView() {
  return `<section class="panel"><div class="section-head"><div><h2>每次推进，都留有依据</h2><p class="muted">显示最近 200 条记录；完整记录会随复盘导出。</p></div><span class="badge gray">${workspace.events.length} 条</span></div>${workspace.events.slice().reverse().map(e=>`<div class="event-row"><span class="muted">${date(e.created_at)}</span><span>${esc(memberName(e.actor_id))}</span><span class="event-detail">${esc(e.detail)}</span></div>`).join('')}</section>`;
}

function modelView() {
  const current=workspace.current_model||{name:'DeepSeek-V4-Pro',model_id:'deepseek-v4-pro',provider:'DeepSeek 官方',mode:'builtin',key_configured:false,version:0};
  const captain=!!workspace.me.captain;
  return `<div class="workspace-grid"><section class="panel"><div class="section-head"><div><h2>选择这次协作的模型</h2><p class="muted">完整名称与模型 ID 分别展示，密钥不会在页面回显。</p></div><span class="badge ${current.key_configured?'':'amber'}">${current.key_configured?'密钥已配置':'等待配置'}</span></div>
    <div class="note"><strong>当前：${esc(current.name)}</strong><br>完整模型 ID：${esc(current.model_id)}<br>服务来源：${esc(current.provider)}${current.custom_key_memory_only?'<br>自带密钥仅保存在本次服务内存，服务重启后需重新连接。':''}</div>
    <h3 style="margin:24px 0 10px">内置基础模型</h3><p>DeepSeek-V4-Pro <span class="badge gray">deepseek-v4-pro</span></p><p class="muted" style="margin:10px 0 15px">使用 DeepSeek 官方接口，由服务端配置密钥。预设名称不代表已经验证可调用；生成成功后会另记服务响应的模型标识。</p><button id="use-builtin" class="ghost" ${!captain?'disabled':''}>使用内置基础模型</button>
    ${captain?`<h3 style="margin:30px 0 17px">使用自己的 API key</h3><form id="model-form">${field('API 服务地址（兼容 Chat Completions）','<input id="model-base" type="url" required value="https://api.deepseek.com" placeholder="https://api.deepseek.com">')}${field('API key','<input id="model-key" type="password" autocomplete="off" required maxlength="1000" placeholder="仅用于向你选择的服务验证，不写入磁盘">')}<button type="submit" id="discover-models">读取可用模型</button><p class="muted" style="margin-top:12px">同一密钥通常可调用多个模型。读取列表后请选择具体名称；读取列表不等于已验证生成质量。密钥只发给本后端及所选服务，不存浏览器本地存储。</p></form>`:'<p class="muted" style="margin-top:25px">模型选择由队长设置，成员可查看当前完整名称与 ID。</p>'}
    ${discovery&&captain?`<form id="select-model-form" style="margin-top:25px">${field('服务商返回的模型列表',`<select id="discovered-model">${discovery.models.map(m=>`<option value="${esc(m.id)}">${esc(m.name)} — ${esc(m.id)}</option>`).join('')}</select>`)}<p id="model-full-id" class="muted" style="margin-bottom:13px;word-break:break-all">完整模型 ID：${esc(discovery.models[0]?.id)}</p><button id="save-model" type="submit">使用所选模型</button></form>`:''}
    </section><aside class="stack"><section class="panel"><h3>名称从哪里来？</h3><p class="muted" style="margin-top:12px">自带模型的名称和完整 ID 来自你所选服务的 /models 接口。服务未提供展示名称时，原样展示完整 ID，不猜测模型身份。</p></section><section class="panel"><h3>调用之前</h3><p class="muted" style="margin-top:12px">选择真实模型生成方案时，会向该服务发送本项目原文、成员信息与截止时间，请先取得团队同意。切回内置模型会清除本项目暂存的自带密钥。</p></section></aside></div>`;
}

function bindModel() {
  if($('#use-builtin'))$('#use-builtin').onclick=()=>run(async()=>{
    await api(`/api/projects/${session.project}/model`,{method:'PUT',body:JSON.stringify({mode:'builtin',expected_version:workspace.current_model.version})});discovery=null;await refresh();notify('已切回服务端基础模型；此前自带密钥已从本次工作区内存清除。');
  });
  if($('#model-form'))$('#model-form').onsubmit=event=>{event.preventDefault();run(async()=>{
    const payload={base_url:$('#model-base').value,api_key:$('#model-key').value};
    discovery=await(await api(`/api/projects/${session.project}/model/discover`,{method:'POST',body:JSON.stringify(payload)})).json();
    $('#model-key').value='';render();notify('已读取服务商模型列表，请核对完整 ID 后选择。');
  });};
  if($('#discovered-model'))$('#discovered-model').onchange=()=>{$('#model-full-id').textContent='完整模型 ID：'+$('#discovered-model').value;};
  if($('#select-model-form'))$('#select-model-form').onsubmit=event=>{event.preventDefault();run(async()=>{
    await api(`/api/projects/${session.project}/model`,{method:'PUT',body:JSON.stringify({mode:'custom',expected_version:workspace.current_model.version,discovery_id:discovery.discovery_id,model_id:$('#discovered-model').value})});discovery=null;await refresh();notify('模型选择已保存到本次服务内存。实际生成结果会记录使用的完整模型 ID。');
  });};
}

function inviteUrl(token) {return `${location.origin}/#project=${encodeURIComponent(session.project)}&token=${encodeURIComponent(token)}`;}
async function copy(text) {try {await navigator.clipboard.writeText(text);notify('入口已复制，请私下发送给对应成员。');}catch{notify('浏览器未允许复制。请允许此页面使用剪贴板后重试。',true);}}
function showEntries() {
  $('#entries').innerHTML=workspace.members.map(m=>`<div class="entry-row"><div><h3>${esc(m.name)} ${m.captain?'<span class="badge gray">队长</span>':''}</h3><small>${esc(m.role)}</small></div><button class="ghost small" data-entry="${esc(m.id)}">${m.id===workspace.me.id||invites.has(m.id)?'复制成员入口':'重发入口（旧入口失效）'}</button></div>`).join('');
  $$('[data-entry]').forEach(b=>b.onclick=()=>run(async()=>{
    const mid=b.dataset.entry;
    if(mid===workspace.me.id) return copy(inviteUrl(session.token));
    let token=invites.get(mid);
    if(!token){if(!confirm('重发将使该成员旧入口立即失效，继续吗？'))return;const result=await(await api(`/api/projects/${session.project}/members/${mid}/rotate-token`,{method:'POST'})).json();token=result.access_token;invites.set(mid,token);await refresh();}
    await copy(inviteUrl(token));showEntries();
  }));
  if(!$('#entry-dialog').open) $('#entry-dialog').showModal();
}

$('#close-dialog').onclick=()=>$('#entry-dialog').close();
$('#cancel-action').onclick=()=>{$('#action-dialog').close();pendingAction=null;};
$('#action-form').onsubmit=event=>{event.preventDefault();if(!pendingAction)return;const {task,action}=pendingAction;run(()=>sendAction(task,action,$('#action-note').value.trim()));};
(async()=>{if(session){try{await refresh();return;}catch(error){notify(error.message,true);if(error.status===401||error.status===404){session=null;localStorage.removeItem(sessionKey);}else{app.innerHTML='<main class="loading">连接暂时中断，资料保存在后端。请确认服务启动后刷新页面。</main>';return;}}}welcome();})();
