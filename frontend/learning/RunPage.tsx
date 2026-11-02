import { useCallback, useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Check, Readback } from './contracts';
import type { Config, Route } from './types';
import { currentCheckReceipt } from './checkReceipt';
import { RolesPanel } from './RolesPanel';
import { ReportsPanel } from './ReportsPanel';
import { Notice, useGuard, type LeaveGuard, type SetGuard } from './ui';
import { CreateForm, EditArtifactForm, OpenVersion, ReflectionForm, RequirementsForm, SelfCheckForm, TransferForm } from './TaskForms';
import { childFeedback, encode, lessonError, MutationNotice, Preview, progressLabels, readSnapshot, stages, TextField, useLessonMutation, type Snapshot } from './workspace';

type View = 'clarify' | 'create' | 'self' | 'edit' | 'transfer' | 'reflection' | 'submit';
export function RunPage({ api, learnerId, id, config, setGuard, canLeave, navigate, review }: { api: LearningApi; learnerId: string; id: string; config: Config; setGuard: SetGuard; canLeave: () => Promise<boolean>; navigate: (r: Route) => Promise<boolean>; review: boolean }) {
  const [s, setSnapshot] = useState<Snapshot | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false), [view, setView] = useState<View | null>(review ? 'submit' : null);
  const [formGuard, setFormGuard] = useState<LeaveGuard>({ dirty: false }), [readback, setReadback] = useState<Readback | null>(null);
  const [checkReceipt, setCheckReceipt] = useState<Check | null>(null);
  const [helpGuard, setHelpGuard] = useState<LeaveGuard>({ dirty: false });
  const [reportDirty, setReportDirty] = useState(false);
  const [support, setSupport] = useState('');
  const alive = useRef(true), generation = useRef(0), title = useRef<HTMLHeadingElement>(null);
  const load = useCallback(async () => {
    const epoch = ++generation.current; setLoading(true);
    try { const data = await readSnapshot(api, id, learnerId); if (!alive.current || epoch !== generation.current) return; setSnapshot(data); setError(''); }
    catch (e) { if (alive.current && epoch === generation.current) setError(lessonError(e)); throw e; }
    finally { if (alive.current && epoch === generation.current) setLoading(false); }
  }, [api, id, learnerId]);
  useEffect(() => { alive.current = true; void load().catch(() => {}); return () => { alive.current = false; ++generation.current; }; }, [load]);
  const m = useLessonMutation(api, load);
  useEffect(() => {
    if (!s?.model || !['pending', 'running'].includes(s.model.status) || m.busy || m.pending || loading || error) return;
    const timer = setTimeout(() => void load().catch(() => {}), 2500);
    return () => clearTimeout(timer);
  }, [s?.model?.id, s?.model?.status, m.busy, m.pending, loading, error, load]);
  const childGuard = useCallback((g: LeaveGuard) => setFormGuard(g), []);
  useGuard(setGuard, formGuard.dirty || helpGuard.dirty || reportDirty || !!support || m.busy || !!m.pending, !support && !helpGuard.dirty && !reportDirty && !m.locked ? formGuard.save : undefined);
  const stage = s?.run.progress.find(p => p.state !== 'passed' && p.state !== 'locked')?.stage || 'review';
  const inferred: View = stage === 'clarify' ? 'clarify' : stage === 'create' ? 'create' : !s?.self ? 'self' : (s.artifact?.current_version.version || 0) < 2 ? 'edit' : !s.transfer?.transfer_response ? 'transfer' : !s.reflection || s.reflection.artifact_version_id !== s.artifact?.current_version.id || s.reflection.transfer_attempt_revision !== s.transfer?.revision ? 'reflection' : 'submit';
  const active = view || inferred;
  const currentStage = active === 'clarify' ? 'clarify' : active === 'create' ? 'create' : 'review';
  useEffect(() => { title.current?.focus(); }, [active]);
  useEffect(() => { setCheckReceipt(null); }, [currentStage]);
  if (!s) return <section className="lp-card"><h2>恢复当前任务</h2>{error ? <><Notice error>{error}</Notice><button onClick={() => void load().catch(() => {})}>重新读取当前任务</button><button onClick={() => void navigate('#/learn')}>回到学习首页</button></> : <Notice>正在读取已保存的任务与作品…</Notice>}</section>;
  const run = s.run, artifact = s.artifact;
  const taskId = ({ clarify: 'S1.1', create: artifact ? 'S2.2' : 'S2.1', self: 'S3.1', edit: 'S3.2', transfer: 'S3.3', reflection: 'S3.4', submit: 'S3.4' })[active];
  const task = s.course.task_cards.find(t => t.id === taskId) || s.course.task_cards.find(t => t.stage === currentStage);
  const completed = run.progress.length > 0 && run.progress.every(p => p.state === 'passed');
  const editingCompleted = completed && active === 'edit';
  const waiting = run.progress.some(p => p.state === 'pending_review');
  const caseItem = s.cases.find(c => c.status !== 'resolved') || s.cases[0];
  const lockedStage = !run.progress.some(p => p.stage === currentStage && p.state !== 'locked');
  const disabled = !config.learning_enabled || loading || lockedStage || (completed && !editingCompleted) || waiting;
  const allowed = (op: string) => !disabled && !m.locked && run.allowed_actions.includes(op);
  const savedCheck = s.checks.find(c => c.stage === currentStage);
  const confirmed = !!readback && readback.artifact_version_id === artifact?.current_version.id;
  const checkReadback = confirmed ? { id: readback!.id, revision: readback!.revision } : s.checks.find(c => c.artifact_version_id === artifact?.current_version.id && c.readback_ref)?.readback_ref || null;
  // preflight/blocked feedback deliberately leaves progress.check_id unchanged.
  // Accept the direct receipt only while its stage, versions and run revision match.
  const currentReceipt = currentCheckReceipt(checkReceipt, s, currentStage, task?.rubric_version_id, checkReadback);
  const check = currentReceipt || savedCheck;
  const preflight = currentCheckReceipt(check, s, currentStage, task?.rubric_version_id, checkReadback);
  const preflightReady = preflight?.purpose === 'preflight' && preflight.outcome === 'feedback_only'
    && preflight.progress_effect === 'none' && preflight.rule_result === 'pass'
    && preflight.evidence_complete && preflight.model_state === 'succeeded';
  async function choose(next: View) { if (await canLeave()) { setView(next); } }
  function doCheck(purpose: 'preflight' | 'advance' | 'submit_review') {
    if (!task) return;
    void m.run<Check>(`/runs/${encode(id)}/checks`, { expected_revision: run.revision, lesson_version_id: run.progress.find(p => p.stage === currentStage)!.lesson_version_id, artifact_version_id: currentStage === 'clarify' ? null : artifact?.current_version.id || null, rubric_version_id: task.rubric_version_id, stage: currentStage, requirements_ref: run.current_requirements_ref, self_check_ref: run.current_self_check_ref, reflection_ref: run.current_reflection_ref, transfer_attempt_ref: run.current_transfer_attempt_ref, readback_ref: checkReadback, purpose }, result => { setCheckReceipt(result); if (result.outcome === 'advanced' && result.progress_effect === 'passed_and_unlocked') setView(null); });
  }
  const props = { snapshot: s, mutation: m, setGuard: childGuard, disabled, config };
  const finalReady = !!(artifact && run.current_self_check_ref && run.current_transfer_attempt_ref && run.current_reflection_ref && checkReadback);
  return <>
    <section className="lp-card lp-current" aria-busy={loading || m.busy}><p className="lp-eyebrow">{s.course.title} · {completed ? '本课回顾' : `第 ${currentStage === 'clarify' ? 1 : currentStage === 'create' ? 2 : 3} 关`}</p><h2 ref={title} tabIndex={-1}>{completed && !editingCompleted ? '这次练习已完成' : waiting ? caseItem?.feedback ? '看看老师需要你补充什么' : '作品已交老师，等待反馈' : ({ clarify: '说清这张卡的要求', create: '操作工具，留下作品', self: '先做一次自己的检查', edit: '亲手改进一处', transfer: '换张材料，自己再试', reflection: '说说你的判断和改进', submit: '核对记录，再交给老师' })[active]}</h2>
      <p className="lp-mode">{s.model?.mode === 'live' ? '作品候选来自真实模型调用。AI 可能写错，仍需你对照资料、修改并说明。' : s.model?.mode === 'replay' ? '作品候选来自历史回放，不是本次新生成。' : config.live_enabled ? '生成前请选择模拟或真实工具。每次帮助和作品运行都会分别标明来源。' : '这是模拟练习，不会调用真实 AI。模拟结果不能证明你已经学会使用真实工具。'}</p>
      {error && <Notice error>{error}</Notice>}<MutationNotice mutation={m} />
      {!completed && !waiting && <p>当前提示：{run.current_action.label}</p>}
      {lockedStage ? <Notice>这一步还没开启。先完成当前任务，再回来看看。</Notice> : completed && !editingCompleted ? <><p>本课完成情况来自已保存的检查记录。家长报告需要另外核对和发布。</p>{artifact && <Preview content={artifact.current_version.content} label={`最终已保存 v${artifact.current_version.version}`} />}{s.reflection && <p>我的回顾：{s.reflection.change_explanation}</p>}<button className="lp-primary" onClick={() => void navigate('#/learn/works')}>打开我的作品</button>{run.allowed_actions.includes('versionArtifact') && <button onClick={() => void choose('edit')}>继续修改作品（需重新检查）</button>}</> : waiting ? <><p>保存的作品和练习都还在。老师反馈后，可以从这里继续。</p>{artifact && <Preview content={artifact.current_version.content} label={`待查看 v${artifact.current_version.version}`} />}</> : !task ? <Notice error>当前任务卡还没读全，请重新读取。</Notice> : <>
        {active === 'clarify' && <RequirementsForm {...props} advance={() => doCheck('advance')} />}
        {active === 'create' && (artifact ? <><OpenVersion key={artifact.current_version.id} api={api} artifact={artifact} mutation={m} disabled={disabled} onReadback={setReadback} confirmed={confirmed} />{(confirmed || checkReadback) && <button className="lp-primary" disabled={!allowed('checkArtifact')} onClick={() => doCheck('advance')}>检查保存记录并进入第三关</button>}</> : <CreateForm {...props} />)}
        {active === 'self' && artifact && <SelfCheckForm {...props} done={() => setView(null)} />}
        {active === 'edit' && artifact && <>{s.self && <button disabled={!allowed('checkArtifact')} onClick={() => doCheck('preflight')}>看看自查后的规则反馈</button>}<EditArtifactForm {...props} done={() => setView(artifact.current_version.version >= 2 ? 'self' : null)} /></>}
        {active === 'transfer' && s.course.task_cards.some(t => t.id === 'S3.3') && <TransferForm {...props} />}
        {active === 'reflection' && artifact && s.transfer && s.self && <ReflectionForm {...props} />}
        {active === 'submit' && <><p>先预检已保存内容。预检只给反馈，之后需要你明确送给老师。</p><ul className="lp-checklist"><li>{s.self ? '自查已保存' : '还缺自己的判断'}</li><li>{(artifact?.current_version.version || 0) > 1 ? '改进已另存新版本' : '还需要亲手修改并说明'}</li><li>{s.transfer?.transfer_response ? '换材料尝试已保存' : '还缺换材料尝试'}</li><li>{s.reflection ? '复盘已保存，送审会核对版本' : '还缺复盘'}</li></ul>{artifact && <OpenVersion key={artifact.current_version.id} api={api} artifact={artifact} mutation={m} disabled={disabled} onReadback={setReadback} confirmed={confirmed || !!checkReadback} />}
          <div className="lp-actions"><button className={preflightReady && finalReady ? '' : 'lp-primary'} disabled={!allowed('checkArtifact')} onClick={() => doCheck('preflight')}>预检已保存的记录</button>{preflightReady && finalReady && <button className="lp-primary" disabled={!allowed('checkArtifact')} onClick={() => doCheck('submit_review')}>交给老师看看</button>}</div></>}
      </>}
      {check && <div className="lp-notice"><h3>{check.stale || (check.artifact_version_id && check.artifact_version_id !== artifact?.current_version.id) ? '旧版本检查，需要重新核对' : check.human_result === 'passed' ? '老师已确认这一版' : check.human_result === 'needs_practice' ? '按老师的反馈再练一步' : check.purpose === 'preflight' ? '预检反馈 · 还没有送审' : check.outcome === 'awaiting_review' && check.progress_effect === 'pending_review' && check.case_id ? '已交老师' : check.outcome === 'blocked_support' ? '暂时没有老师接收，尚未送审' : check.outcome === 'blocked_unknown' ? '操作结果仍在核对，尚未送审' : check.outcome === 'advanced' && check.progress_effect === 'passed_and_unlocked' ? '本关记录已确认，可以继续' : '检查反馈 · 还需补充'}</h3>{check.human_result && !check.stale ? <p>{check.human_result === 'passed' ? '这一版的检查已完成。继续修改会另存新版本，并重新检查。' : '作品已经保留，看看老师提出的具体建议再继续。'}</p> : check.feedback.map((f, i) => <p key={i}>{childFeedback(f)}</p>)}{check.missing_evidence.length > 0 && <p>还有 {check.missing_evidence.length} 项记录需要核对，请按当前任务补充。</p>}</div>}
      <div className="lp-actions"><button disabled={loading || m.busy} onClick={() => void load().catch(() => {})}>重新读取当前任务</button><button onClick={() => void navigate('#/learn')}>保存过的内容留在这里，回首页</button></div>
    </section>
    <section className="lp-card"><h2>三关地图</h2><ol className="lp-map">{Object.entries(stages).map(([key, label]) => { const p = run.progress.find(p => p.stage === key); return <li key={key} aria-current={key === currentStage ? 'step' : undefined}><strong>{label}</strong><span>{p ? progressLabels[p.state] || '状态待确认' : '还未开启'}</span><button disabled={!p || p.state === 'locked' || m.busy} onClick={() => void choose(key === 'review' ? inferred === 'clarify' || inferred === 'create' ? 'submit' : inferred : key as View)}>查看这一关</button></li>; })}</ol>
      {run.progress.some(p => p.stage === 'review' && p.state !== 'locked') && <nav className="lp-actions" aria-label="第三关练习记录">{([['self', '我的自查'], ['edit', '修改作品'], ['transfer', '换材料尝试'], ['reflection', '我的复盘'], ['submit', '检查与送审']] as [View, string][]).map(([v, label]) => <button key={v} disabled={m.busy || (v === 'reflection' && (!s.self || !s.transfer))} onClick={() => void choose(v)}>{label}</button>)}</nav>}
    </section>
    {(!completed || editingCompleted) && task && <RolesPanel api={api} run={run} task={task} helps={s.helps} config={config} mutation={m} setGuard={setHelpGuard} sourceIds={{ guide: [], tool_guide: [s.requirements?.id, s.attempt?.id].filter((id): id is string => !!id), creation_coach: [...task.material_version_ids, ...[s.requirements?.id, artifact?.current_version.id].filter((id): id is string => !!id)], review_coach: [...task.material_version_ids, ...[artifact?.current_version.id, s.self?.id].filter((id): id is string => !!id)] }} />}
    <section className="lp-card"><h2>{caseItem ? '老师与帮助进度' : '需要老师帮忙'}</h2>{caseItem ? <><p>负责人：{caseItem.owner_display_name}</p><p>预计处理时间：{new Date(caseItem.due_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p><p>联系办法：{caseItem.support_contact_label}</p>{caseItem.feedback && <Notice>{caseItem.feedback}</Notice>}<p>下一步：{caseItem.next_action.label}</p></> : <p>可以说明卡住的地方。只有老师接收成功后，这里才会显示负责人和处理时间。</p>}
      {caseItem?.status !== 'resolved' && <><TextField label={caseItem ? '补充给老师的说明' : '我需要什么帮助'} value={support} change={setSupport} multiline max={8000} />
      <button disabled={m.locked || !config.learning_enabled || !support.trim() || (caseItem ? !caseItem.allowed_actions.includes('appendCase') : !run.allowed_actions.includes('askHuman'))} onClick={() => void m.run(caseItem ? `/cases/${encode(caseItem.id)}/messages` : `/runs/${encode(id)}/cases`, { expected_revision: caseItem?.revision ?? run.revision, message: support, source_ids: artifact ? [artifact.current_version.id] : [], ...(caseItem ? {} : { reason_category: 'operation_help' }) }, () => setSupport(''))}>{caseItem ? '提交补充说明' : '请求老师帮助'}</button></>}
    </section>
    {config.reports_enabled && s.reflection && api.snapshot().session && <ReportsPanel api={api} session={api.snapshot().session!} learnerId={learnerId} run={run} onDirty={setReportDirty} />}
  </>;
}
