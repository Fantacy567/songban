import { useEffect, useRef, useState } from 'react';
import { ApiError, errorText, requestId, type LearningApi } from './api';
import type { Artifact, Attempt, CardText, Case, Check, Course, Help, HelpDisclosure, Material, Reflection, Requirements, Run, SelfCheck } from './contracts';
import { Notice } from './ui';

export const encode = encodeURIComponent;
export const factLabels = { event_name: '活动名称', audience: '邀请谁', date: '日期', start_time: '开始时间', end_time: '结束时间', place: '地点', preparation: '准备物品' };
export const cardLabels = { title: '标题', audience: '邀请谁', date: '日期', start_time: '开始时间', end_time: '结束时间', place: '地点', preparation: '准备物品', invitation_line: '邀请语' };
export const blankFacts = () => ({ event_name: '', audience: '', date: '', start_time: '', end_time: '', place: '', preparation: '' });
export const blankHelp = (): HelpDisclosure => ({ kind: 'unknown', note: '', child_confirmed: false, example_source_ids: [] });
export const stages = { clarify: '说清要求', create: '操作与保存', review: '检查与改进' };
export const progressLabels = { locked: '还未开始', available: '可以开始', in_progress: '正在练习', pending_review: '等待老师', needs_practice: '需要补练', passed: '本关已完成' };
export function childFeedback(text: string) {
  if (text.includes('模拟协议检查')) return '这是模拟练习的记录核对，老师还会查看你的判断和解释。';
  const code = text.match(/R\d+\.([A-Za-z_]+)/)?.[1];
  if (!code) return text;
  const names: Record<string, string> = { requirements: '已确认的要求', requirements_facts: '要求中的活动信息', artifact: '保存的作品', model_run: '本次工具操作结果', readback: '打开作品后的确认', attempt: '这次保存的工具输入', self_check: '你自己的判断', previous_version: '修改前的作品', no_change: '作品的一处实际改进', reflection: '修改理由和复盘', self_check_version: '对这一版作品的自查', transfer: '换材料尝试', facts: '新材料中的活动信息', changes: '两处不同的说明', invitation_line: '自己写的邀请语', audience: '邀请谁', date: '活动日期', start_time: '开始时间', end_time: '结束时间', place: '地点', preparation: '准备物品' };
  return `请核对${names[code] || '当前任务的保存记录'}，补充后再检查。`;
}
export function lessonError(e: unknown) {
  if (e instanceof ApiError) {
    const messages: Record<string, string> = { operation_unavailable: '三关练习暂未开放，可以继续保存起点或请家长查看。', course_unavailable: '这份课程目前不可用，已保存记录仍保留。', entitlement_required: '还需要确认本课试点资格，请家长联系项目支持。', support_unavailable: '老师队列尚未开放，已保存的内容仍保留。请家长联系项目支持后再试。', evidence_stale: '作品或练习已有新版本，请核对当前记录后重新检查。', active_run_unknown: '上次操作的结果还在核对，请查看进度。', invalid_transition: '当前还不能做这一步，请读取最新任务。', content_unavailable: '这份材料目前不可读取，草稿已保留。请联系项目支持。' };
    if (messages[e.code]) return messages[e.code];
  }
  return errorText(e);
}
/** Immutable request body retained through lost receipts. Conflict resolution never writes. */
export function useLessonMutation(api: LearningApi, refresh: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [pending, setPending] = useState<{ path: string; method: string; body: object; accept?: (v: never) => void } | null>(null);
  const [conflict, setConflict] = useState(false), [blocked, setBlocked] = useState(false);
  const [reconciled, setReconciled] = useState(0);
  const alive = useRef(true), lock = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function perform(job: NonNullable<typeof pending>) {
    if (lock.current) return false;
    lock.current = true; setBusy(true); setError('');
    try {
      const result = await api.request<never>(job.path, job.method, job.body);
      if (!alive.current) return false;
      setPending(null); job.accept?.(result);
      try { await refresh(); } catch { if (alive.current) { setError('操作回执已收到，但最新任务未读全。请先重新读取记录。'); setConflict(true); } }
      return true;
    } catch (e) {
      if (!alive.current) return false;
      setError(lessonError(e));
      if (e instanceof ApiError && e.code === 'idempotency_conflict') { setBlocked(true); setPending(null); }
      else if (e instanceof ApiError && ['revision_conflict', 'evidence_stale', 'stale_evidence', 'invalid_transition', 'invalid_read_receipt'].includes(e.code)) { setConflict(true); setPending(null); }
      else if (e instanceof ApiError && e.unknown && !['support_unavailable', 'operation_unavailable', 'model_unavailable', 'course_unavailable'].includes(e.code)) setPending(job);
      return false;
    } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  return { busy, error, pending, conflict, blocked, reconciled, locked: busy || !!pending || conflict || blocked,
    run<T>(path: string, body: object, accept?: (v: T) => void, method = 'POST') {
      if (busy || pending || conflict || blocked) return Promise.resolve(false);
      return perform({ path, method, body: { ...body, request_id: requestId() }, accept: accept as (v: never) => void });
    },
    async retry() { if (!pending) return; try { await refresh(); await perform(pending); } catch (e) { if (alive.current) setError(lessonError(e)); } },
    async reconcile() { try { await refresh(); if (alive.current) { setReconciled(n => n + 1); setConflict(false); setError(''); } } catch (e) { if (alive.current) setError(lessonError(e)); } },
  };
}
export type Mutation = ReturnType<typeof useLessonMutation>;
export function MutationNotice({ mutation: m }: { mutation: Mutation }) {
  return <>{m.busy && <Notice>正在保存并核对最新任务…</Notice>}{m.error && <Notice error>{m.error}</Notice>}{m.pending && <button disabled={m.busy} onClick={() => void m.retry()}>核对并重试原操作</button>}{m.conflict && <div className="lp-notice"><p>你的输入仍在页面里。先读取最新保存内容，再决定如何修改；这里不会自动覆盖。</p><button onClick={() => void m.reconcile()}>读取最新记录，保留我的输入</button></div>}{m.blocked && <p>操作编号冲突，已停止写入。请保留输入并联系项目支持核对。</p>}</>;
}
export function HelpFields({ value, change }: { value: HelpDisclosure; change: (v: HelpDisclosure) => void }) {
  return <fieldset className="lp-help-disclosure"><legend>这一步得到了什么帮助？</legend><label>帮助情况<select aria-label="帮助情况" value={value.kind} onChange={e => change({ ...value, kind: e.target.value as HelpDisclosure['kind'] })}>
    <option value="unknown">还不确定</option><option value="none_reported">我没有要报告的帮助</option><option value="reading_or_operation">朗读或操作提示</option><option value="adult_transcription">我口述，大人帮我打字</option><option value="adult_content">大人提供了内容</option><option value="peer_content">同伴提供了内容</option><option value="ai_content">AI 提供了内容</option><option value="example_reference">参考过示例</option>
  </select></label><label>帮助补充（可以不填）<textarea rows={2} maxLength={300} value={value.note} onChange={e => change({ ...value, note: e.target.value })} /></label>{value.kind === 'example_reference' && <label>参考的示例编号<input value={value.example_source_ids.join(',')} onChange={e => change({ ...value, example_source_ids: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} /></label>}
  <label className="lp-option"><input type="checkbox" checked={value.child_confirmed} onChange={e => change({ ...value, child_confirmed: e.target.checked })} />我确认这一步的内容和帮助情况</label><p className="lp-caption">记录帮助不会扣分；没有报告帮助，也不能证明线下无人帮助。</p></fieldset>;
}
export function TextField({ label, value, change, max = 300, multiline = false }: { label: string; value: string; change: (s: string) => void; max?: number; multiline?: boolean }) {
  return <label>{label}{multiline ? <textarea aria-label={label} rows={3} maxLength={max} value={value} onChange={e => change(e.target.value)} /> : <input aria-label={label} maxLength={max} value={value} onChange={e => change(e.target.value)} />}</label>;
}
export function MaterialCard({ material }: { material: Material }) {
  return <aside className="lp-material"><h3>虚构活动资料卡</h3><p>{material.notice}</p><dl className="lp-facts">{Object.entries(factLabels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{material.facts[key as keyof typeof factLabels]}</dd></div>)}</dl></aside>;
}
export function Preview({ content, label }: { content: CardText; label: string }) {
  return <article className="lp-invitation" aria-label={label}><p className="lp-eyebrow">{label} · 虚构活动</p><h3>{content.title}</h3><p>给：{content.audience}</p><p>{content.date}　{content.start_time}–{content.end_time}</p><p>地点：{content.place}</p><p>准备：{content.preparation}</p><p className="lp-pre">{content.invitation_line}</p></article>;
}
export function candidate(text: string | null): CardText | null {
  try { const obj = JSON.parse(text || ''); const keys = Object.keys(cardLabels); if (!obj || Object.keys(obj).length !== keys.length || keys.some(k => typeof obj[k] !== 'string' || !obj[k].trim() || obj[k].length > (k === 'title' ? 40 : k === 'invitation_line' ? 160 : ['date', 'start_time', 'end_time'].includes(k) ? 100 : 200))) return null; return obj; } catch { return null; }
}
export interface Snapshot { run: Run; course: Course; requirements: Requirements | null; attempt: Attempt | null; transfer: Attempt | null; artifact: Artifact | null; self: SelfCheck | null; reflection: Reflection | null; model: import('./contracts').ModelRun | null; materials: Record<string, Material>; checks: Check[]; helps: Help[]; cases: Case[] }
export async function readPages<T>(api: LearningApi, path: string): Promise<T[]> {
  const items: T[] = [], cursors = new Set<string>(); let cursor: string | null = null;
  do {
    const page: { items: T[]; next_cursor: string | null } = await api.request(`${path}${cursor ? `?cursor=${encode(cursor)}` : ''}`);
    items.push(...page.items); cursor = page.next_cursor;
    if (cursor) { if (cursors.has(cursor) || cursors.size >= 100) throw new Error('Incomplete pagination'); cursors.add(cursor); }
  } while (cursor);
  return items;
}
export async function readSnapshot(api: LearningApi, id: string, learnerId: string): Promise<Snapshot> {
  const run = await api.request<Run>(`/runs/${encode(id)}`);
  if (run.id !== id || run.learner_id !== learnerId) throw new Error('Scope mismatch');
  const course = await api.request<Course>(`/courses/${encode(run.course_version_id)}`);
  const read = <T,>(path: string | null) => path ? api.request<T>(path) : Promise.resolve(null);
  const requests = [read<Requirements>(run.current_requirements_ref ? `/runs/${encode(id)}/requirements` : null), read<Attempt>(run.current_attempt_ref ? `/attempts/${encode(run.current_attempt_ref.id)}` : null), read<Attempt>(run.current_transfer_attempt_ref ? `/attempts/${encode(run.current_transfer_attempt_ref.id)}` : null), read<Artifact>(run.current_artifact_id ? `/artifacts/${encode(run.current_artifact_id)}` : null), read<SelfCheck>(run.current_self_check_ref ? `/self-checks/${encode(run.current_self_check_ref.id)}` : null), read<Reflection>(run.current_reflection_ref ? `/reflections/${encode(run.current_reflection_ref.id)}` : null), read<import('./contracts').ModelRun>(run.active_model_run_id ? `/model-runs/${encode(run.active_model_run_id)}` : null)] as const;
  const [requirements, attempt, transfer, artifact, self, reflection, model] = await Promise.all(requests);
  for (const record of [requirements, attempt, transfer, artifact, self, reflection]) if (record && record.run_id !== id) throw new Error('Scope mismatch');
  const activeStages = run.progress.filter(p => p.state !== 'locked').map(p => p.stage);
  const mids = [...new Set(course.task_cards.filter(t => activeStages.includes(t.stage)).flatMap(t => t.material_version_ids))];
  const [materialList, checks, helps, cases] = await Promise.all([
    Promise.all(mids.map(mid => api.request<Material>(`/courses/${encode(course.id)}/materials/${encode(mid)}`))),
    Promise.all([...new Set(run.progress.flatMap(p => p.check_id ? [p.check_id] : []))].map(cid => api.request<Check>(`/checks/${encode(cid)}`))),
    readPages<Help>(api, `/runs/${encode(id)}/help`),
    readPages<Case>(api, '/cases'),
  ]);
  const caseIds = checks.flatMap(c => c.case_id ? [c.case_id] : []);
  return { run, course, requirements, attempt, transfer, artifact, self, reflection, model, materials: Object.fromEntries(mids.map((mid, i) => [mid, materialList[i]])), checks, helps, cases: cases.filter(c => c.learner_id === learnerId && (c.target_id === id || caseIds.includes(c.id))) };
}
