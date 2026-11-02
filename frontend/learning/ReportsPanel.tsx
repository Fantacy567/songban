import { useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import { ApiError, errorText } from './api';
import type { Session } from './types';
import type { Run, Artifact } from './contracts';
import type { Case, Report } from './reportContracts';
import { generationStates, natureLabels, reportStates } from './reportContracts';
import { encode, MutationNotice, readPages, useLessonMutation } from './workspace';
import { Notice } from './ui';

export interface ReportsProps { api: LearningApi; session: Session; learnerId: string; run?: Run; onDirty?: (dirty: boolean) => void }
export function ReportContent({ report: r }: { report: Report }) {
  return <article className="lp-card" aria-label="报告内容"><h3>{reportStates[r.status] || '报告状态待确认'}</h3><p>{generationStates[r.generation_status] || '整理状态待确认'}</p>
    {r.evidence_changed && <Notice>学习记录已有变化。这份报告保留原来的来源，请按新记录重新整理。</Notice>}
    {r.observations.map((o, i) => <div key={i}><p className="lp-caption">{natureLabels[o.nature] || '来源待确认'}</p><p className="lp-pre">{o.text}</p><details><summary>查看这条的来源编号</summary><ul>{o.source_ids.map(id => <li key={id}>{id}</li>)}</ul></details></div>)}
    <h4>这份记录能说明什么</h4><ul>{r.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul>
    <p className="lp-caption">报告只描述这次练习。AI 整理、自动检查与老师的意见各有来源。</p></article>;
}

function Panel({ api, session, learnerId, run, onDirty }: ReportsProps) {
  const [items, setItems] = useState<Report[]>([]), [selected, setSelected] = useState('');
  const [cases, setCases] = useState<Case[]>([]);
  const [loaded, setLoaded] = useState(false), [error, setError] = useState('');
  const [note, setNote] = useState(''), [reason, setReason] = useState(''), [sources, setSources] = useState<string[]>([]), [confirmed, setConfirmed] = useState(false);
  const [mode, setMode] = useState<'mock' | 'live'>('mock');
  const alive = useRef(true), serial = useRef(0);
  const manager = session.mode === 'manager';
  const current = items.find(r => r.id === selected) || null;
  const config = api.snapshot().config as (ReturnType<LearningApi['snapshot']>['config'] & { reports_enabled?: boolean; mock_enabled?: boolean });
  async function refresh() {
    const seq = ++serial.current;
    try {
      const [next, queue] = await Promise.all([readPages<Report>(api, `/learners/${encode(learnerId)}/reports`), manager ? Promise.resolve([] as Case[]) : readPages<Case>(api, '/cases')]);
      if (!alive.current || seq !== serial.current) return;
      if (next.some(r => r.learner_id !== learnerId || (manager && r.status !== 'published'))) throw new Error('Unexpected report scope');
      setItems(next); setCases(queue.filter(c => c.learner_id === learnerId && c.kind === 'report_review')); setLoaded(true); setError('');
    } catch (e) { if (alive.current && seq === serial.current) { setError(errorText(e)); setLoaded(false); if (e instanceof ApiError && [401, 403, 404, 410].includes(e.status)) { setItems([]); setNote(''); setReason(''); setSources([]); setConfirmed(false); } } throw e; }
  }
  const mutation = useLessonMutation(api, refresh);
  useEffect(() => { setConfirmed(false); }, [current?.id, current?.revision]);
  useEffect(() => { alive.current = true; void refresh().catch(() => {}); return () => { alive.current = false; ++serial.current; onDirty?.(false); }; }, []);
  useEffect(() => { onDirty?.(!!note || !!reason || confirmed || mutation.busy || !!mutation.pending); }, [note, reason, confirmed, mutation.busy, mutation.pending, onDirty]);
  const blocked = mutation.locked || !loaded || (!manager && !config?.learning_enabled);
  const reviewCase = cases.find(c => c.target_id === current?.id);
  const evidenceReady = !!run?.current_artifact_id && !!run.current_reflection_ref && !!run.progress[2]?.check_id;
  async function create() {
    if (!run || blocked) return;
    try {
      const fresh = await api.request<Run>(`/runs/${encode(run.id)}`);
      if (fresh.learner_id !== learnerId || !fresh.current_artifact_id || !fresh.current_reflection_ref || !fresh.progress[2]?.check_id) throw new Error('Missing report evidence');
      const artifact = await api.request<Artifact>(`/artifacts/${encode(fresh.current_artifact_id)}`);
      if (!alive.current) return;
      await mutation.run<Report>(`/runs/${encode(run.id)}/reports`, { expected_revision: fresh.revision, reflection_id: fresh.current_reflection_ref.id, artifact_version_id: artifact.current_version.id, check_id: fresh.progress[2].check_id, mode }, r => { setSelected(r.id); });
    } catch (e) { if (alive.current) setError(errorText(e)); }
  }
  function select(id: string) { setSelected(id); setNote(''); setReason(''); setConfirmed(false); setSources([]); }
  return <section className="lp-section" aria-label={manager ? '已发布学习报告' : '我的学习报告'}><h2>{manager ? '孩子的学习报告' : '看看这次练习的记录'}</h2>
    <p>{manager ? '这里只显示已经人工复核并发布的报告。' : '先核对自己的事实，有不准确的地方可以提出，再请老师复核。'}</p>
    {!manager && !config?.learning_enabled && <Notice>学习写入已暂停，已保存的报告仍可查看。</Notice>}
    {error && <Notice error>{error}</Notice>}<MutationNotice mutation={mutation} />
    <button disabled={mutation.busy} onClick={() => void refresh().catch(() => {})}>重新读取报告</button>
    {loaded && !items.length && <p>{manager ? '目前还没有已发布的报告。' : '还没有报告。完成作品检查和复盘后，就可以整理。'}</p>}
    <div className="lp-actions">{items.map(r => <button key={r.id} disabled={mutation.locked || !!note || !!reason || confirmed} aria-pressed={selected === r.id} onClick={() => select(r.id)}>查看报告 · {reportStates[r.status] || '待确认'} · {r.id.slice(-6)}</button>)}</div>
    {current && <><ReportContent report={current} />{!manager && current.status === 'pending_review' && reviewCase && <Notice>复核负责人：{reviewCase.owner_display_name}。处理期限：{new Date(reviewCase.due_at).toLocaleString('zh-CN')}。支持出口：{reviewCase.support_contact_label}。{reviewCase.feedback}</Notice>}{!manager && current.allowed_actions.includes('disputeReport') && <details><summary>有事实不准确</summary>
      <label>哪一处需要改正？<textarea aria-label="哪一处需要改正？" value={note} maxLength={8000} onChange={e => setNote(e.target.value)} /></label>
      <fieldset><legend>相关来源（可以不选）</legend>{[...new Set(current.observations.flatMap(o => o.source_ids))].map(id => <label className="lp-option" key={id}><input type="checkbox" checked={sources.includes(id)} onChange={e => setSources(e.target.checked ? [...sources, id] : sources.filter(s => s !== id))} />{id}</label>)}</fieldset>
      <button disabled={blocked || !note.trim()} onClick={() => void mutation.run(`/reports/${encode(current.id)}/disputes`, { expected_revision: current.revision, note, source_ids: sources }, () => { setNote(''); setSources([]); setConfirmed(false); })}>保存事实异议</button></details>}
      {!manager && current.allowed_actions.includes('submitReport') && <><label className="lp-option"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我已经核对这些事实，需要改正的地方已提交异议</label><button className="lp-primary" disabled={blocked || !confirmed || !!note.trim()} onClick={() => void mutation.run(`/reports/${encode(current.id)}/submit-review`, { expected_revision: current.revision, facts_confirmed: confirmed }, () => setConfirmed(false))}>请老师复核这份报告</button></>}
      {manager && current.allowed_actions.includes('revokeReport') && <details><summary>撤回这份报告</summary><label>撤回原因<textarea aria-label="撤回原因" value={reason} maxLength={8000} onChange={e => setReason(e.target.value)} /></label><button disabled={blocked || !reason.trim()} onClick={() => void mutation.run(`/reports/${encode(current.id)}/revocations`, { expected_revision: current.revision, reason }, () => { setReason(''); setSelected(''); })}>确认撤回报告</button></details>}</>}
    {!manager && run && <div className="lp-card"><p>整理只使用已保存的作品和练习记录，不会重新运行实验。</p><label>报告整理方式<select aria-label="报告整理方式" value={mode} onChange={e => setMode(e.target.value as 'mock' | 'live')}><option value="mock">模拟整理（不调用真实供应商）</option><option value="live" disabled={!config?.live_enabled}>真实模型整理</option></select></label>
      <button className={current ? '' : 'lp-primary'} disabled={blocked || !evidenceReady || !config?.reports_enabled || (mode === 'mock' ? !config?.mock_enabled : !config?.live_enabled) || items.some(r => r.run_id === run.id && ['pending', 'running', 'unknown'].includes(r.generation_status))} onClick={() => void create()}>整理一份新报告</button>
      {!evidenceReady && <p>请先保存作品、完成复盘并提交学习检查，再整理报告。</p>}
      {!config?.reports_enabled && <p>报告整理尚未开放，已保存作品仍保留。</p>}</div>}
  </section>;
}

export function ReportsPanel(props: ReportsProps) { return props.session.mode === 'learner' && props.session.learner_id === props.learnerId ? <Panel key={`${props.session.id}:${props.session.mode_epoch}:${props.learnerId}`} {...props} /> : null; }
export function ParentReports(props: ReportsProps) { return props.session.mode === 'manager' ? <Panel key={`${props.session.id}:${props.session.mode_epoch}:${props.learnerId}`} {...props} /> : null; }
