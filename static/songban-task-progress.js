'use strict';

const SongbanTaskProgress = (() => {
  const sessions = new Map();
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const statusNames = {accepted:'已验收', waiting:'待验收', active:'进行中', blocked:'受阻 / 待修改', todo:'待开始'};

  function status(task) {
    if (task.handoff_state === 'accepted') return 'accepted';
    if (['changes_requested', 'dependency_changed'].includes(task.handoff_state) || task.status === 'blocked') return 'blocked';
    if (task.status === 'reported_done') return 'waiting';
    return task.status === 'in_progress' ? 'active' : 'todo';
  }
  function summarize(tasks) {
    const counts = {accepted:0, waiting:0, active:0, blocked:0, todo:0};
    tasks.forEach(task => counts[status(task)]++);
    return {...counts, total:tasks.length, percent:tasks.length ? Math.round(counts.accepted / tasks.length * 100) : 0};
  }
  function sampleTeam() {
    const members = [
      {id:'sample-lin', name:'林同学', role:'产品与交互', strengths:'需求梳理 · 原型设计'},
      {id:'sample-zhou', name:'周同学', role:'前端开发', strengths:'页面实现 · 接口联调'},
      {id:'sample-chen', name:'陈同学', role:'内容与调研', strengths:'用户访谈 · 内容表达'},
      {id:'sample-xu', name:'许同学', role:'测试与展示', strengths:'流程验证 · 演示准备'},
    ];
    const rows = [
      [0,'梳理作品的使用场景','accepted'], [0,'完成第一轮页面草图','accepted'], [0,'确定主流程的验收方法','accepted'], [0,'连接可以操作的交互原型','active'], [0,'整理项目说明与交付清单','todo'],
      [1,'搭建页面结构','accepted'], [1,'接入活动与任务数据','waiting'], [1,'补齐接口错误提示','blocked'], [1,'调整手机端布局','active'],
      [2,'准备访谈问题','accepted'], [2,'整理同学的使用反馈','accepted'], [2,'核对页面说明文案','accepted'], [2,'准备一分钟演示故事','waiting'],
      [3,'验证主流程的正常与异常操作','active'], [3,'重新核对更新后的原型','blocked'], [3,'录制完整的作品演示','todo'],
    ];
    return {members, me:members[0].id, tasks:rows.map(([person,title,stage], i) => ({
      key:'DEMO-' + (i + 1), owner_id:members[person].id, title,
      acceptance:'完成后提供可查看的成果，并请另一位队友按说明核对。',
      status:stage === 'accepted' || stage === 'waiting' ? 'reported_done' : stage === 'active' ? 'in_progress' : stage === 'blocked' ? 'blocked' : 'todo',
      handoff_state:stage === 'accepted' ? 'accepted' : stage === 'waiting' ? 'waiting_review' : 'not_reported',
    }))};
  }
  function advanceSample(task) {
    const current = status(task);
    if (current === 'accepted') return;
    if (current === 'waiting') task.handoff_state = 'accepted';
    else {
      task.status = current === 'active' ? 'reported_done' : 'in_progress';
      task.handoff_state = current === 'active' ? 'waiting_review' : 'not_reported';
    }
  }
  function progressBar(summary, label, large=false) {
    return `<div class="task-meter ${large ? 'task-meter-large' : ''}" role="progressbar" aria-label="${escape(label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${summary.percent}" aria-valuetext="${summary.total ? `已验收 ${summary.accepted} / ${summary.total} 项任务` : '尚未分配任务'}"><span style="width:${summary.percent}%"></span></div>`;
  }
  function taskList(tasks, model, demo) {
    if (!tasks.length) return '<div class="task-progress-empty"><h3>还没有分配到任务</h3><p>先查看待领取任务。队长发布任务后，领取的任务和进度会显示在这里。</p></div>';
    return `<div class="task-progress-list">${tasks.map(task => {
      const stage = status(task), member = model.members.find(m => m.id === task.owner_id);
      const action = {todo:'模拟开始', active:'模拟提交成果', waiting:'模拟通过验收', blocked:'模拟解除阻塞'}[stage];
      return `<article class="task-progress-row"><span class="task-stage-mark stage-${stage}" aria-hidden="true">${stage === 'accepted' ? '✓' : stage === 'blocked' ? '!' : ''}</span><div class="task-progress-copy"><h3>${escape(task.title)}</h3><p>${escape(member?.name || '未分配')} · ${escape(task.key)}</p><details><summary>查看检查方法</summary><p>${escape(task.acceptance || '等待补充检查方法')}</p></details></div><div class="task-progress-row-actions"><span class="task-stage-label stage-${stage}">${statusNames[stage]}</span>${demo ? action ? `<button type="button" data-demo-advance="${escape(task.key)}">${action}</button>` : '' : `<button type="button" data-open-task="${escape(task.key)}">查看与同步</button>`}</div></article>`;
    }).join('')}</div>`;
  }
  function mount(host, snapshot, options={}) {
    const identity = options.identity || 'visitor';
    const key = identity + ':' + (snapshot?.team.id || 'personal');
    if (!sessions.has(key)) sessions.set(key, {mode:snapshot ? 'live' : 'demo', view:'personal', sample:sampleTeam(), member:'', filter:'all'});
    const ui = sessions.get(key);
    function render(focus) {
      const demo = ui.mode === 'demo';
      const model = demo ? ui.sample : {
        members:snapshot?.members || [], tasks:snapshot?.active_plan?.tasks || [], me:snapshot?.me.id,
      };
      if (!model.members.some(m => m.id === ui.member)) ui.member = demo ? model.me : snapshot?.me.id || '';
      const person = model.members.find(m => m.id === ui.member);
      const own = model.tasks.filter(task => task.owner_id === (demo ? model.me : snapshot?.me.id));
      const personal = summarize(own), overall = summarize(model.tasks);
      const viewed = ui.view === 'personal' ? own : model.tasks.filter(task => task.owner_id === ui.member);
      const filtered = ui.filter === 'all' ? viewed : viewed.filter(task => status(task) === ui.filter);
      const current = ui.view === 'personal' ? personal : overall;
      const first = own.find(t => status(t) === 'active') || own.find(t => status(t) === 'blocked') || own.find(t => status(t) !== 'accepted');
      const currentName = model.members.find(m => m.id === model.me)?.name || '我';
      options.onModeChange?.(!demo);
      host.innerHTML = `<div class="task-dashboard">
        <header class="task-dashboard-heading"><div><p class="eyebrow">${demo ? '模拟小队 · 示例数据' : '任务进度 · ' + escape(snapshot?.team.name || '我的个人空间')}</p><h1>${ui.view === 'personal' ? '每一步，都看得见。' : '看看大家，一起走到哪里。'}</h1><p class="subtitle">${demo ? '校园创作小队：从一个想法，到一次完整演示。' : escape(snapshot?.direction.goal || '把分工变成可查看、可交接的成果。')}</p></div><div class="task-source-switch" role="group" aria-label="任务数据"><button type="button" data-task-mode="live" aria-pressed="${!demo}">真实小队</button><button type="button" data-task-mode="demo" aria-pressed="${demo}">模拟小队</button></div></header>
        <div class="task-view-bar"><div class="task-view-tabs" role="tablist" aria-label="任务视图"><button id="task-tab-personal" role="tab" type="button" aria-selected="${ui.view === 'personal'}" aria-controls="task-progress-panel" tabindex="${ui.view === 'personal' ? 0 : -1}" data-task-view="personal">个人任务</button><button id="task-tab-team" role="tab" type="button" aria-selected="${ui.view === 'team'}" aria-controls="task-progress-panel" tabindex="${ui.view === 'team' ? 0 : -1}" data-task-view="team">团队任务 <span>${model.members.length}</span></button></div>${demo ? '<button type="button" class="text-link" data-demo-reset>重置示例</button>' : '<button type="button" class="text-link" data-task-refresh>刷新进度</button>'}</div>
        ${demo ? `<div class="task-demo-note"><span class="tag">模拟演示</span><p>以下 4 位成员与任务均为示例。可以点击“模拟”按钮观察进度变化，不会写入真实小队。</p>${ui.view === 'personal' ? `<label>演示角色<select aria-label="演示角色" data-demo-person>${model.members.map(m => `<option value="${m.id}" ${m.id === model.me ? 'selected' : ''}>${escape(m.name)}</option>`).join('')}</select></label>` : ''}</div>` : ''}
        <div id="task-progress-panel" role="tabpanel" aria-labelledby="task-tab-${ui.view}">
          <section class="task-progress-hero ${demo ? 'is-demo' : ''}" aria-label="${ui.view === 'personal' ? '个人总体进度' : '团队总体进度'}"><div class="task-progress-lead"><div><p class="task-progress-eyebrow">${ui.view === 'personal' ? escape(currentName) + '的整体进度' : '团队整体进度'}</p><h2>${current.total ? `已验收 <strong>${current.accepted}</strong> / ${current.total} 项任务` : '等待确认第一份任务安排'}</h2><p class="muted">${ui.view === 'personal' && first ? `当前关注：${escape(first.title)}` : current.total ? '每一项成果通过检查，进度就向前一步。' : '没有任务时显示 0%，不代表已经完成。'}</p></div><div class="task-progress-percent"><strong>${current.percent}</strong><span>%</span></div></div>${progressBar(current, ui.view === 'personal' ? '个人验收进度' : '团队验收进度', true)}<div class="task-progress-counts">${Object.keys(statusNames).map(stage => `<div><strong>${current[stage]}</strong><span>${statusNames[stage]}</span></div>`).join('')}</div><p class="task-progress-basis">进度 = 已通过同伴验收的任务数 / 分配任务数；进行中和待验收单独记录。</p></section>
          ${!demo && !snapshot ? '<div class="task-progress-empty"><h2>创建或加入小队，开始记录真实进度。</h2><p>也可以先切换到模拟小队，看看多人协作的样子。</p><button type="button" class="primary" data-task-create>创建或加入小队</button></div>' : ''}
          ${ui.view === 'team' ? `<section class="task-members-section" aria-label="团队成员进度"><div class="task-section-title"><h2>每个人，都在往前走。</h2><span class="muted">${model.members.length} 位${demo ? '模拟' : ''}成员</span></div><div class="task-member-grid">${model.members.map((m, index) => {
            const list = model.tasks.filter(t => t.owner_id === m.id), summary = summarize(list);
            const next = list.find(t => status(t) === 'blocked') || list.find(t => status(t) === 'active') || list.find(t => status(t) === 'waiting');
            return `<article class="task-member-card ${ui.member === m.id ? 'is-selected' : ''}"><div class="task-member-heading"><span class="task-member-avatar avatar-tone-${index % 3}" aria-hidden="true">${escape(m.name.slice(0,1))}</span><div><h3>${escape(m.name)} ${m.id === model.me ? '<small>我</small>' : ''}</h3><p>${escape(m.role || (snapshot?.team.captain_id === m.id ? '队长' : '团队成员'))}</p></div>${demo ? '<span class="task-sample-label">模拟</span>' : ''}</div><p class="task-member-skills">${escape(m.strengths || m.willingness || '一起把作品做出来')}</p><div class="task-member-ratio"><span>已验收 ${summary.accepted} / ${summary.total} 项</span><strong>${summary.percent}%</strong></div>${progressBar(summary, m.name + '的验收进度')}<p class="task-member-status">${summary.active} 项进行中 · ${summary.waiting} 项待验收${summary.blocked ? ` · ${summary.blocked} 项待处理` : ''}</p><p class="task-member-next">${next ? `${status(next) === 'blocked' ? '需要配合' : '当前任务'}：${escape(next.title)}` : summary.total && summary.accepted === summary.total ? '本轮任务已全部验收。' : summary.total ? '下一步：开始已分配的任务。' : '等待分配任务。'}</p><button type="button" data-task-member="${escape(m.id)}" aria-pressed="${ui.member === m.id}">查看个人任务 <span aria-hidden="true">→</span></button></article>`;
          }).join('')}</div></section>` : ''}
          <section class="task-person-list" aria-label="任务清单"><div class="task-section-title"><h2>${ui.view === 'personal' ? '我的任务' : escape(person?.name || '成员') + '的任务'}</h2><span class="muted">${viewed.length} 项${demo ? '示例' : ''}任务</span></div><div class="task-filters" role="group" aria-label="筛选任务状态">${[['all','全部'],...Object.entries(statusNames)].map(([key,label]) => `<button type="button" data-task-filter="${key}" aria-pressed="${ui.filter === key}">${label}</button>`).join('')}</div>${filtered.length ? taskList(filtered, model, demo) : viewed.length ? '<p class="task-filter-empty">这个状态下暂时没有任务。</p>' : taskList([], model, demo)}</section>
        </div>
      </div>`;
      host.querySelectorAll('[data-task-mode]').forEach(button => button.onclick = () => { ui.mode = button.dataset.taskMode; ui.member = ''; ui.filter = 'all'; render(`[data-task-mode="${ui.mode}"]`); });
      host.querySelectorAll('[data-task-view]').forEach(button => {
        button.onclick = () => { ui.view = button.dataset.taskView; ui.filter = 'all'; render(`[data-task-view="${ui.view}"]`); };
        button.onkeydown = event => {
          if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
          event.preventDefault(); ui.view = event.key === 'Home' ? 'personal' : event.key === 'End' ? 'team' : ui.view === 'personal' ? 'team' : 'personal'; ui.filter = 'all'; render(`[data-task-view="${ui.view}"]`);
        };
      });
      host.querySelectorAll('[data-task-member]').forEach(button => button.onclick = () => { ui.member = button.dataset.taskMember; ui.filter = 'all'; render(`[data-task-member="${ui.member}"]`); host.querySelector('.task-person-list').scrollIntoView({block:'nearest',behavior:'smooth'}); });
      host.querySelectorAll('[data-task-filter]').forEach(button => button.onclick = () => { ui.filter = button.dataset.taskFilter; render(`[data-task-filter="${ui.filter}"]`); });
      host.querySelectorAll('[data-demo-advance]').forEach(button => button.onclick = () => { const task = ui.sample.tasks.find(t => t.key === button.dataset.demoAdvance); if (!demo || !task) return; advanceSample(task); render(`[data-demo-advance="${task.key}"]`); });
      host.querySelectorAll('[data-open-task]').forEach(button => button.onclick = () => options.onOpenTask?.(button.dataset.openTask));
      const actor = host.querySelector('[data-demo-person]'); if (actor) actor.onchange = () => { ui.sample.me = actor.value; ui.filter = 'all'; render('[data-demo-person]'); };
      const reset = host.querySelector('[data-demo-reset]'); if (reset) reset.onclick = () => { ui.sample = sampleTeam(); ui.member = ''; ui.filter = 'all'; render('[data-demo-reset]'); };
      const refresh = host.querySelector('[data-task-refresh]'); if (refresh) refresh.onclick = () => options.onRefresh?.();
      const create = host.querySelector('[data-task-create]'); if (create) create.onclick = () => options.onCreateTeam?.();
      if (focus) (host.querySelector(focus) || host.querySelector('[aria-selected="true"]'))?.focus({preventScroll:true});
    }
    render();
  }
  return {mount, summarize, status, sampleTeam, advanceSample, reset:() => sessions.clear()};
})();
if (typeof module !== 'undefined') module.exports = SongbanTaskProgress;
