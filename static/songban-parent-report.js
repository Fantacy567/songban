'use strict';
// Render a model-generated parent report with authoritative records from the server.
(() => {
  const text = value => typeof value === 'string' ? value.trim() : '';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clean = value => text(value).replace(/^【(?:虚构|模拟|演示)[^】]*】\s*/, '');
  const list = value => Array.isArray(value) ? value.filter(v => typeof v === 'string' && v.trim()) : [];
  const generatedReports = new Map();

  function build(input) {
    const {person, preferences, snapshot, draft, event, analysis, model, generatedAt = new Date().toISOString()} = input;
    if (!person?.id || snapshot?.me?.id !== person.id) throw Error('成员已切换，请重新生成当前成员的报告。');
    const member = snapshot.members?.find(m => m.id === person.id);
    if (!member) throw Error('当前小队没有这位成员，请重新选择小队。');
    const ownReports = (snapshot.reports || []).filter(r => r.user_id === person.id);
    const savedReflection = ownReports.filter(r => /^复盘[：:]/.test(text(r.summary)))
      .sort((a, b) => (b.seq || 0) - (a.seq || 0))[0];
    const savedText = text(savedReflection?.summary).replace(/^复盘[：:]\s*/, '');
    const draftText = input.draftIsExample && savedText ? '' : text(draft);
    const reflection = draftText || savedText;
    const reflectionSource = draftText && draftText !== savedText ? (input.draftIsExample ? '来自本页演示复盘' : '来自本页复盘草稿') : savedText ? '来自已保存的本人复盘' : '尚未填写个人复盘';
    const tasks = (snapshot.active_plan?.tasks || []).filter(t => t.owner_id === person.id).map(task => ({
      title: text(task.title),
      status: task.handoff_state === 'accepted' ? '同伴已核对' : ['changes_requested','dependency_changed'].includes(task.handoff_state) ? '还需修改或补充' : task.handoff_state === 'waiting_review' || task.status === 'reported_done' ? '已报告完成，待同伴核对' : task.status === 'blocked' ? '遇到困难，待协助' : task.status === 'in_progress' ? '正在推进' : '尚未报告进展',
      accepted: task.handoff_state === 'accepted',
      progress: clean(task.latest_progress?.summary),
      evidence: list(task.latest_progress?.evidence).map(clean),
      feedback: clean(task.handoff?.note),
    }));
    const checked = tasks.filter(t => t.accepted).length;
    const name = text(person.name) || text(member.name) || '这位同学';
    const goal = clean(snapshot.direction?.goal);
    const learningGoal = text(member.willingness);
    const strengths = text(member.strengths) || text(person.skills);
    const interests = list(preferences?.interests), skills = list(preferences?.skills);
    if (!analysis?.summary || !Array.isArray(analysis.observations) || !analysis.observations.length || !Array.isArray(analysis.suggestions) || !analysis.suggestions.length || !['live','fixture'].includes(model?.mode)) {
      throw Error('模型没有返回完整的家长报告，请重试');
    }
    const observations = analysis.observations;
    return {
      name, team: text(snapshot.team?.name), event: text(event?.title) || '黑客松创作活动', date: text(event?.date), location: text(event?.location), generatedAt,
      interests, skills, experience:text(preferences?.experience), availableTime:text(preferences?.time), strengths, learningGoal, goal, tasks, checked,
      reflection, reflectionSource, observations,
      summary: analysis.summary,
      suggestions: analysis.suggestions,
      model,
    };
  }

  function render(report) {
    const e = escape;
    const modelLabel = report.model.mode === 'live' ? '真实 AI 生成' : '接口测试替身';
    const modelName = report.model.actual_model || ('配置模型：' + (report.model.requested_model || '未知'));
    const when = new Date(report.generatedAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
    return `<article class="parent-report" aria-label="${e(report.name)}的家长报告">
      <header class="parent-report-cover"><div class="parent-report-top"><span class="parent-report-brand">松伴 · 成长记录</span><span class="parent-report-demo">演示素材 · ${e(modelLabel)}</span></div><p class="parent-report-kicker">给家长的一份参赛记录</p><h2>${e(report.name)}的<br>参赛成长报告</h2><p class="parent-report-lead">从具体的尝试里，看见孩子的每一步。</p><dl class="parent-report-meta"><div><dt>参与活动</dt><dd>${e(report.event)}</dd></div><div><dt>时间与地点</dt><dd>${e([report.date,report.location].filter(Boolean).join(' · ') || '尚未填写')}</dd></div><div><dt>所在小队</dt><dd>${e(report.team || '尚未填写')}</dd></div></dl></header>
      <div class="parent-report-body"><section class="parent-report-letter"><p>亲爱的家长：</p><p>${e(report.summary)}</p></section>
      <section class="parent-report-section"><p class="parent-report-section-number">01 / 出发时</p><h3>孩子带着什么想法出发</h3><div class="parent-report-pills">${report.interests.map(i=>`<span>${e(i)}</span>`).join('')}</div><dl class="parent-report-detail"><div><dt>这次想尝试</dt><dd>${e(report.learningGoal || '尚未填写，欢迎先听孩子说说自己的想法。')}</dd></div><div><dt>已有经历</dt><dd>${e(report.experience || '尚未填写')}</dd></div><div><dt>目前做得到的事</dt><dd>${e(report.strengths || report.skills.join('、') || '尚未填写')}</dd></div><div><dt>愿意投入的时间</dt><dd>${e(report.availableTime || '尚未填写')}</dd></div></dl></section>
      <section class="parent-report-section"><p class="parent-report-section-number">02 / 一起动手</p><h3>孩子实际承担了什么</h3><p class="parent-report-project"><strong>小队的目标</strong><br>${e(report.goal || '当前还没有确认项目目标。')}</p>${report.tasks.length ? `<div class="parent-report-stats"><div><strong>${report.tasks.length}</strong><span>本人负责的任务</span></div><div><strong>${report.checked}</strong><span>同伴已核对的成果</span></div></div><div class="parent-report-task-list">${report.tasks.map(t=>`<article class="parent-report-task"><div class="parent-report-task-title"><h4>${e(t.title)}</h4><span class="${t.accepted?'is-checked':''}">${e(t.status)}</span></div><p>${e(t.progress || '尚未填写本项工作的进展。')}</p>${t.evidence.length?`<ul>${t.evidence.map(item=>`<li>${e(item)}</li>`).join('')}</ul>`:''}${t.feedback?`<p class="parent-report-feedback">同伴反馈：${e(t.feedback)}</p>`:''}</article>`).join('')}</div>`:'<p class="parent-report-empty">尚未记录本人领取或承担的任务。后续补充分工和成果后，重新生成即可更新这里。</p>'}</section>
      <section class="parent-report-section"><p class="parent-report-section-number">03 / 过程里的成长</p><h3>这些经历，值得一起聊聊</h3><div class="parent-report-observations">${report.observations.map(o=>`<article><h4>${e(o.title)}</h4><p>${e(o.detail)}</p><small>依据：${e(o.source)}</small></article>`).join('')}</div></section>
      <section class="parent-report-section"><p class="parent-report-section-number">04 / 孩子自己的话</p><h3>回头看，想留下什么</h3>${report.reflection?`<blockquote>${e(report.reflection)}</blockquote>`:'<p class="parent-report-empty">还没有个人复盘。可以在上方写下这次的收获或困难，再重新生成报告。</p>'}<p class="parent-report-source">${e(report.reflectionSource)}</p></section>
      <section class="parent-report-section parent-report-family"><p class="parent-report-section-number">05 / 回到家以后</p><h3>家长可以这样陪伴下一步</h3><ol>${report.suggestions.map(s=>`<li>${e(s)}</li>`).join('')}</ol></section>
      <footer class="parent-report-footer"><p>根据当前成员填写的兴趣、经历、分工意愿、本人任务、成果检查及复盘整理。复盘草稿仅用于本次生成，未自动保存到团队。</p><p>素材为虚构参赛样例，分析由${e(modelLabel)}。模型：${e(modelName)}。记录参与过程，不作为竞赛成绩或能力测评。</p><p>生成时间：${e(when)} · 松伴</p></footer></div></article>`;
  }

  function plainText(report) {
    const lines = [`${report.name}的参赛成长报告（虚构演示）`, report.event, [report.date,report.location].filter(Boolean).join(' · '), `小队：${report.team}`, '', '亲爱的家长：', report.summary,
      '', '孩子带着什么想法出发', `兴趣：${report.interests.join('、') || '尚未填写'}`, `这次想尝试：${report.learningGoal || '尚未填写'}`, `已有经历：${report.experience || '尚未填写'}`, `目前做得到的事：${report.strengths || report.skills.join('、') || '尚未填写'}`, `愿意投入的时间：${report.availableTime || '尚未填写'}`,
      '', '孩子实际承担了什么', `小队目标：${report.goal || '尚未确认'}`];
    for (const task of report.tasks) lines.push('', `${task.title} · ${task.status}`, task.progress || '尚未记录进展', ...task.evidence, ...(task.feedback ? [`同伴反馈：${task.feedback}`] : []));
    if (!report.tasks.length) lines.push('尚未记录本人任务。');
    lines.push('', '过程里的成长');
    for (const observation of report.observations) lines.push(observation.title, observation.detail, `依据：${observation.source}`);
    lines.push('', '孩子自己的话', report.reflection || '尚未填写个人复盘', report.reflectionSource, '', '家长可以这样陪伴下一步', ...report.suggestions.map((s,i)=>`${i+1}. ${s}`), '', '根据当前成员记录整理。复盘草稿未自动保存到团队。虚构演示素材，不作为竞赛成绩或能力测评。', `报告生成：${report.model.mode === 'live' ? '真实 AI' : '接口测试替身'} · ${report.model.actual_model || report.model.requested_model || '模型未知'}`);
    return lines.join('\n');
  }

  function documentHtml(report, css) {
    return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escape(report.name)}的参赛成长报告</title><style>body{margin:0;padding:24px;background:#f6f5f1;font-family:"Microsoft YaHei",sans-serif;color:#202820;line-height:1.8}*{box-sizing:border-box}${css}</style></head><body>${render(report)}</body></html>`;
  }

  function mount(host, options) {
    if (typeof window === 'undefined' || !window.SongbanDemo) return;
    const section = document.createElement('section');
    section.className = 'card parent-report-entry';
    section.id = 'parent-report-section';
    section.dataset.reportOwner = options.key;
    section.innerHTML = `<div class="parent-report-entry-heading"><div><span class="chip">给家长看见成长</span><h2>把这次经历，讲给家长听。</h2><p class="muted">根据当前演示成员填写的兴趣、分工、成果和复盘，调用真实模型分析并生成家长报告。上方尚未保存的复盘也会带入，生成使用已配置的模型额度。</p></div><button type="button" class="primary" id="generate-parent-report">生成家长报告 <span aria-hidden="true">↗</span></button></div><p class="parent-report-status" role="status" aria-live="polite"></p><div class="parent-report-actions" hidden><button type="button" data-report-copy>复制报告文字</button><button type="button" data-report-download>下载报告</button><span class="muted">下载后可直接打开，或使用浏览器打印为 PDF。</span></div><div class="parent-report-result"></div>`;
    host.append(section);
    const status = section.querySelector('[role=status]'), button = section.querySelector('#generate-parent-report'), result = section.querySelector('.parent-report-result');
    let current = generatedReports.get(options.key) || null;
    function show() {
      if (!current) return;
      result.innerHTML = render(current);
      section.querySelector('.parent-report-actions').hidden = false;
      button.innerHTML = '重新生成报告 <span aria-hidden="true">↻</span>';
      status.textContent = (current.model.mode === 'live' ? '已由真实模型生成家长报告。' : '已生成接口测试报告。') + '修改资料或复盘后，点击重新生成即可更新。';
    }
    show();
    button.onclick = async () => {
      if (button.disabled) return;
      button.disabled = true; status.textContent = 'AI 正在分析孩子的参赛记录，请稍候…';
      try {
        const input = await options.getData(crypto.randomUUID());
        if (!section.isConnected) return;
        current = build(input); generatedReports.set(options.key, current); show();
        result.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block:'start'});
      } catch (error) {
        if (section.isConnected) status.textContent = '本次未生成：' + error.message + (current ? ' 当前仍显示上一次报告。' : '');
      } finally { button.disabled = false; }
    };
    section.querySelector('[data-report-copy]').onclick = async () => {
      if (!current) return;
      try { await navigator.clipboard.writeText(plainText(current)); status.textContent = '报告文字已复制，可以粘贴给家长。'; }
      catch { status.textContent = '复制未成功，请下载报告，或选中报告文字手动复制。'; }
    };
    section.querySelector('[data-report-download]').onclick = async event => {
      if (!current) return;
      const download = event.currentTarget, report = current; download.disabled = true;
      try {
        const response = await fetch('/static/songban-parent-report.css');
        if (!response.ok) throw Error('报告样式未能加载');
        const css = await response.text();
        const url = URL.createObjectURL(new Blob([documentHtml(report, css)], {type:'text/html;charset=utf-8'}));
        const a = document.createElement('a'); a.href = url; a.download = `${report.name.replace(/[<>:"/\\|?*\u0000-\u001f]/g,'').slice(0,60) || '孩子'}-参赛成长报告.html`;
        a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        status.textContent = '报告已下载，可发给家长，或打开后打印为 PDF。';
      } catch (error) { status.textContent = '下载未完成：' + error.message + '，请重试。'; }
      finally { download.disabled = false; }
    };
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = {build, render, plainText, documentHtml};
  if (typeof window !== 'undefined') window.SongbanParentReport = {mount};
})();
