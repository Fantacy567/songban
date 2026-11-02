import { useCallback, useEffect, useState } from 'react';
import type { LearningApi } from './api';
import { Notice } from './ui';
import { encode, lessonError, MutationNotice, useLessonMutation } from './workspace';

export interface EntrySummary {
  id: string; revision: number; learner_id: string; status: 'none' | 'offered' | 'confirmed' | 'declined';
  goals: string[]; experiences: string[]; source_version: number | null;
  candidate: { source_version: number; goals: string[]; experiences: string[] } | null;
}
export function SummaryText({ summary }: { summary: Pick<EntrySummary, 'goals' | 'experiences'> }) {
  return <div className="lp-entry-summary"><p><strong>想做的事：</strong>{summary.goals.join('；') || '还没了解，可以边做边聊。'}</p><p><strong>已有经历：</strong>{summary.experiences.join('；') || '还没了解，从简单提示开始。'}</p><p className="lp-caption">这是本人描述，不是能力测评；不会带入原始聊天。</p></div>;
}
export function EntryTransfer({ api, learnerId, learnerName, onDirty }: { api: LearningApi; learnerId: string; learnerName: string; onDirty: (dirty: boolean) => void }) {
  const [entry, setEntry] = useState<EntrySummary | null>(null), [error, setError] = useState(''), [confirmed, setConfirmed] = useState(false);
  const [fields, setFields] = useState<string[]>([]);
  const path = `/learners/${encode(learnerId)}/entry`;
  const load = useCallback(async () => { setEntry(await api.request<EntrySummary>(path)); setError(''); }, [api, path]);
  const m = useLessonMutation(api, load);
  useEffect(() => { let live = true; api.request<EntrySummary>(path).then(e => { if (live) setEntry(e); }).catch(e => { if (live) setError(lessonError(e)); }); return () => { live = false; }; }, [api, path]);
  useEffect(() => { onDirty(confirmed || fields.length > 0 || m.busy || !!m.pending); return () => onDirty(false); }, [confirmed, fields.length, m.busy, m.pending, onDirty]);
  if (error) return <Notice>暂时未读到访谈摘要，可直接进入学习；这不会影响已有作品。<button onClick={() => void load().catch(e => setError(lessonError(e)))}>重新读取摘要</button></Notice>;
  if (!entry?.candidate) return null;
  const candidate = entry.candidate;
  return <details className="lp-entry-transfer"><summary>将已确认的访谈带给{learnerName}（选填）</summary><SummaryText summary={candidate} />
    <p>这份访谈来自当前登录账号。只有它确实描述这位孩子时才关联；孩子还可以选择不采用。</p>
    {(['goals', 'experiences'] as const).map(field => <label className="lp-option" key={field}><input type="checkbox" checked={fields.includes(field)} onChange={e => setFields(e.target.checked ? [...fields, field] : fields.filter(f => f !== field))} />{field === 'goals' ? '想做的事' : '已有经历'}</label>)}
    <label className="lp-option"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我确认这份访谈描述的是{learnerName}</label>
    <MutationNotice mutation={m} /><button disabled={!confirmed || !fields.length || m.locked} onClick={() => void m.run<EntrySummary>(path, { expected_revision: entry.revision, source_version: candidate.source_version, subject_confirmed: true, selected_fields: fields }, () => { setConfirmed(false); setFields([]); })}>提供给孩子确认</button>
    {entry.status !== 'none' && <p role="status">{entry.status === 'confirmed' ? '孩子已采用摘要。' : entry.status === 'declined' ? '孩子选择暂不采用。' : '摘要已保存，等待孩子本人确认。'}</p>}
  </details>;
}
