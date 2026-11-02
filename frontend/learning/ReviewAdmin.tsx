import { useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import { ApiError, errorText } from './api';
import type { Session } from './types';
import type { Case, CaseEvidence, ManualFinding, Observation, Report } from './reportContracts';
import { natureLabels } from './reportContracts';
import { ReportContent } from './ReportsPanel';
import { encode, MutationNotice, readPages, useLessonMutation } from './workspace';
import { Notice } from './ui';

export interface ReviewAdminProps { api: LearningApi; session: Session; onDirty?: (dirty: boolean) => void }
const kinds: Record<string, string> = { relationship: '关系核验', learning_review: '学习作品复核', report_review: '学习报告复核', support: '学习求助' };
const blankFindings = (): ManualFinding[] => (['M1', 'M2', 'M3', 'M4'] as const).map(rubric_id => ({ rubric_id, verdict: 'unclear', note: '', source_ids: [] }));

function Admin({ api, onDirty }: ReviewAdminProps) {
  const [cases, setCases] = useState<Case[]>([]), [current, setCurrent] = useState<Case | null>(null), [evidence, setEvidence] = useState<CaseEvidence | null>(null), [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState(''), [ready, setReady] = useState(false), [note, setNote] = useState(''), [ids, setIds] = useState<string[]>([]), [resolved, setResolved] = useState<string[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]), [findings, setFindings] = useState(blankFindings), [decision, setDecision] = useState('needs_information');
  const [edit, setEdit] = useState(false), [assignee, setAssignee] = useState(''), [due, setDue] = useState('');
  const [baseRevision, setBaseRevision] = useState(0);
  const alive = useRef(true), seq = useRef(0), selected = useRef('');
  const dirty = !!note || edit || ids.length > 0 || resolved.length > 0 || !!assignee || !!due;
  async function refresh() {
    const generation = ++seq.current;
    try {
      const list = await readPages<Case>(api, '/cases');
      let c: Case | null = null, e: CaseEvidence | null = null, r: Report | null = null;
      if (selected.current) {
        c = await api.request<Case>(`/cases/${encode(selected.current)}`);
        e = await api.request<CaseEvidence>(`/cases/${encode(selected.current)}/evidence`);
        if (c.kind === 'report_review') r = await api.request<Report>(`/reports/${encode(c.target_id)}`);
      }
      if (!alive.current || generation !== seq.current) return;
      setCases(list); setCurrent(c); setEvidence(e); setReport(r); setError(''); setReady(true);
    } catch (err) { if (alive.current && generation === seq.current) { setError(errorText(err)); setReady(false); if (err instanceof ApiError && [401, 403, 404, 410].includes(err.status)) { selected.current = ''; setCases([]); setCurrent(null); setEvidence(null); setReport(null); clear(); } } throw err; }
  }
  const mutation = useLessonMutation(api, refresh);
  useEffect(() => { alive.current = true; void refresh().catch(() => {}); return () => { alive.current = false; ++seq.current; onDirty?.(false); }; }, []);
  useEffect(() => { onDirty?.(dirty || mutation.busy || !!mutation.pending); }, [dirty, mutation.busy, mutation.pending, onDirty]);
  useEffect(() => { if (report && !edit) setObservations(report.observations); }, [report, edit]);
  useEffect(() => { if (!dirty) setBaseRevision(report?.revision || current?.revision || 0); }, [report?.revision, current?.revision, dirty]);
  function clear() { setNote(''); setIds([]); setResolved([]); setEdit(false); setFindings(blankFindings()); setAssignee(''); setDue(''); }
  async function select(c: Case) { selected.current = c.id; clear(); setCurrent(null); setReport(null); setEvidence(null); setDecision(c.kind === 'relationship' ? 'rejected' : c.kind === 'support' ? 'answered' : 'needs_information'); await refresh().catch(() => {}); }
  const changed = dirty && baseRevision !== (report?.revision || current?.revision || 0);
  const locked = mutation.locked || !ready || changed;
  const disputes = (evidence?.sources || []).flatMap(s => { try { const d = JSON.parse(s.redacted_text); return d.report_id === report?.id && d.status === 'open' ? [{ id: d.id as string, note: d.note as string }] : []; } catch { return []; } });
  const sources = [...new Set((evidence?.sources || []).map(s => s.ref.source_id))];
  function writeCase(suffix: string, body: object) { if (current) void mutation.run(`/cases/${encode(current.id)}/${suffix}`, { expected_revision: current.revision, ...body }, clear); }
  function review(decision: 'approved' | 'changes_requested') { if (report) void mutation.run(`/reports/${encode(report.id)}/reviews`, { expected_revision: report.revision, source_hash: report.source_hash, decision, corrected_observations: observations, note, resolved_dispute_ids: resolved }, clear); }
  return <section className="lp-section" aria-label="人工复核待办"><h2>人工复核待办</h2><p>这里只列出实际分配给你的案件。自动检查和 AI 建议都需要按来源核对。</p>
    {error && <Notice error>{error}</Notice>}<MutationNotice mutation={mutation} /><button disabled={mutation.busy} onClick={() => void refresh().catch(() => {})}>重新读取待办</button>
    {changed && <Notice error>保存版本已变化，输入仍保留。请核对上面的最新材料后继续。<button onClick={() => setBaseRevision(report?.revision || current?.revision || 0)}>已核对最新版本，保留我的修改</button></Notice>}
    {ready && !cases.length && <p>目前没有分配给你的案件。</p>}
    <div className="lp-actions">{cases.map(c => <button key={c.id} disabled={mutation.locked || dirty} aria-pressed={current?.id === c.id} onClick={() => void select(c)}>{kinds[c.kind] || '待确认案件'} · {c.status === 'open' ? '待认领' : c.status === 'claimed' ? '处理中' : c.status === 'resolved' ? '已完成' : '已升级'} · {c.id.slice(-6)}</button>)}</div>
    {current && <><h3>{kinds[current.kind]}</h3><p>负责人：{current.owner_display_name} · 期限：{new Date(current.due_at).toLocaleString('zh-CN')}</p><p>支持出口：{current.support_contact_label}</p>{current.feedback && <Notice>{current.feedback}</Notice>}
      {current.allowed_actions.includes('claimCase') && <button className="lp-primary" disabled={locked} onClick={() => writeCase('claim', {})}>认领这项复核</button>}
      <h4>已保存的复核材料</h4>{evidence?.sources.map((s, i) => <details key={`${s.ref.source_id}:${i}`}><summary>{natureLabels[s.ref.nature] || '来源记录'} · {s.ref.source_id} · 版本 {s.ref.source_version}</summary><pre className="lp-pre">{s.redacted_text}</pre></details>)}
      {report && <ReportContent report={report} />}
      {current.status === 'claimed' && <><label>给孩子的具体反馈<textarea aria-label="给孩子的具体反馈" value={note} maxLength={8000} onChange={e => setNote(e.target.value)} /></label>
        {current.kind === 'report_review' && report?.allowed_actions.includes('reviewReport') && <><h4>逐条校对报告</h4>{observations.map((o, i) => <fieldset key={i}><legend>观察 {i + 1}</legend><textarea aria-label={`观察 ${i + 1}`} value={o.text} maxLength={8000} onChange={e => { setEdit(true); setObservations(observations.map((old, j) => j === i ? { ...old, text: e.target.value, nature: 'human_review' } : old)); }} /><p>{natureLabels[o.nature]}</p><fieldset><legend>这条观察依据哪些来源？</legend>{sources.filter(id => !disputes.some(d => d.id === id)).map(id => <label className="lp-option" key={id}><input type="checkbox" checked={o.source_ids.includes(id)} onChange={e => { setEdit(true); setObservations(observations.map((old, j) => j === i ? { ...old, source_ids: e.target.checked ? [...old.source_ids, id] : old.source_ids.filter(s => s !== id) } : old)); }} />{id}</label>)}</fieldset></fieldset>)}<button disabled={locked || observations.length >= 100} onClick={() => { setEdit(true); setObservations([...observations, { text: '', nature: 'human_review', source_ids: [] }]); }}>补充一条有来源的观察</button>
          {disputes.length > 0 && <fieldset><legend>孩子提出的异议（处理后再勾选）</legend>{disputes.map(d => <label className="lp-option" key={d.id}><input type="checkbox" checked={resolved.includes(d.id)} onChange={e => setResolved(e.target.checked ? [...resolved, d.id] : resolved.filter(id => id !== d.id))} />{d.note}</label>)}</fieldset>}
          <div className="lp-actions"><button disabled={locked || !note.trim() || !observations.length || observations.some(o => !o.text.trim() || !o.source_ids.length)} onClick={() => review('changes_requested')}>退回，让孩子再核对</button><button className="lp-primary" disabled={locked || !note.trim() || !observations.length || observations.some(o => !o.text.trim() || !o.source_ids.length) || disputes.some(d => !resolved.includes(d.id))} onClick={() => review('approved')}>确认本版本复核通过</button></div></>}
        {current.kind !== 'report_review' && current.allowed_actions.includes('resolveCase') && <><fieldset><legend>本次反馈引用的材料</legend>{sources.map(id => <label className="lp-option" key={id}><input type="checkbox" checked={ids.includes(id)} onChange={e => setIds(e.target.checked ? [...ids, id] : ids.filter(v => v !== id))} />{id}</label>)}</fieldset>
          <label>人工处理结论<select aria-label="人工处理结论" value={decision} onChange={e => setDecision(e.target.value)}>{(current.kind === 'learning_review' ? [['needs_information', '还需要补充说明'], ['needs_practice', '建议补练'], ['passed', '本次学习证据通过']] : current.kind === 'relationship' ? [['rejected', '关系证据不充分'], ['verified', '按核验依据确认关系']] : [['answered', '已给出回复']]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {current.kind === 'learning_review' && findings.map((f, i) => <fieldset key={f.rubric_id}><legend>{f.rubric_id} 人工判断</legend><select aria-label={`${f.rubric_id} 判断`} value={f.verdict} onChange={e => setFindings(findings.map((old, j) => i === j ? { ...old, verdict: e.target.value as ManualFinding['verdict'] } : old))}><option value="unclear">还不清楚</option><option value="needs_practice">需要补练</option><option value="supported">有证据支持</option></select><textarea aria-label={`${f.rubric_id} 依据说明`} value={f.note} onChange={e => setFindings(findings.map((old, j) => i === j ? { ...old, note: e.target.value } : old))} maxLength={8000} /></fieldset>)}
          <button className="lp-primary" disabled={locked || !note.trim() || !ids.length || current.kind === 'learning_review' && (findings.some(f => !f.note.trim()) || decision === 'passed' && findings.some(f => f.verdict !== 'supported'))} onClick={() => writeCase('resolve', { target_revision: evidence?.target_revision, decision, evidence_ids: ids, note, manual_findings: current.kind === 'learning_review' ? findings.map(f => ({ ...f, source_ids: ids })) : [] })}>保存人工反馈</button></>}
        {report?.allowed_actions.includes('publishReport') && <button className="lp-primary" disabled={locked || dirty || !report.review_id} onClick={() => void mutation.run(`/reports/${encode(report.id)}/publications`, { expected_revision: report.revision, review_id: report.review_id, source_hash: report.source_hash }, clear)}>发布已批准的这一版给家长</button>}
        {current.allowed_actions.includes('appendCase') && <button disabled={locked || !note.trim()} onClick={() => writeCase('messages', { message: note, source_ids: [] })}>保存补充说明</button>}
        <details><summary>转交或延长期限</summary>{current.allowed_actions.includes('transferCase') && <><label>接手人员编号<input aria-label="接手人员编号" value={assignee} onChange={e => setAssignee(e.target.value)} /></label><button disabled={locked || !assignee.trim() || !note.trim()} onClick={() => writeCase('transfer', { assignee_id: assignee, reason: note })}>转交并保留原因</button></>}{current.allowed_actions.includes('extendCase') && <><label>新的处理期限<input type="datetime-local" aria-label="新的处理期限" value={due} onChange={e => setDue(e.target.value)} /></label><button disabled={locked || !due || !note.trim()} onClick={() => writeCase('extensions', { new_due_at: new Date(due).toISOString(), reason: note })}>延长期限并保留原因</button></>}</details>
      </>}
      {report?.allowed_actions.includes('revokeReport') && <details><summary>撤回已发布报告</summary><label>撤回原因<textarea aria-label="撤回原因" value={note} onChange={e => setNote(e.target.value)} /></label><button disabled={locked || !note.trim()} onClick={() => void mutation.run(`/reports/${encode(report.id)}/revocations`, { expected_revision: report.revision, reason: note }, () => { selected.current = ''; clear(); })}>确认撤回报告</button></details>}
    </>}
  </section>;
}

export function ReviewAdmin(props: ReviewAdminProps) { return props.session.mode === 'staff' ? <Admin key={`${props.session.id}:${props.session.mode_epoch}`} {...props} /> : null; }
