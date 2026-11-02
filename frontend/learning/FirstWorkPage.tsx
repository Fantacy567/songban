import { useCallback, useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Course, Home, Run } from './contracts';
import type { Config, Route } from './types';
import { SummaryText, type EntrySummary } from './EntrySummary';
import { Notice, useGuard, type SetGuard } from './ui';
import { encode, lessonError, MutationNotice, readPages, useLessonMutation } from './workspace';
import { runRoute } from './routes';

/** Entry preparation never fabricates questionnaire answers, identity or grants. */
export function FirstWorkPage({ api, learnerId, config, setGuard, navigate }: { api: LearningApi; learnerId: string; config: Config; setGuard: SetGuard; navigate: (r: Route) => Promise<boolean> }) {
  const [home, setHome] = useState<Home | null>(null), [courses, setCourses] = useState<Course[]>([]), [entry, setEntry] = useState<EntrySummary | null>(null);
  const [error, setError] = useState(''), [created, setCreated] = useState<string | null>(null);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const g = ++generation.current;
    try {
      const [h, e] = await Promise.all([api.request<Home>(`/learners/${encode(learnerId)}/home`), api.request<EntrySummary>(`/learners/${encode(learnerId)}/entry`)]);
      if (g !== generation.current) return;
      if (h.learner_id !== learnerId || e.learner_id !== learnerId) throw new Error('Scope mismatch');
      setHome(h); setEntry(e); setError('');
      // Existing work remains readable when the public catalogue is paused.
      if (!h.run_id) { const cs = await readPages<Course>(api, '/courses'); if (g === generation.current) setCourses(cs); }
    } catch (e) { if (g === generation.current) setError(lessonError(e)); throw e; }
  }, [api, learnerId]);
  useEffect(() => { void load().catch(() => {}); return () => { ++generation.current; }; }, [load]);
  const m = useLessonMutation(api, load);
  useGuard(setGuard, m.busy || !!m.pending);
  useEffect(() => { if (created && !m.busy && !m.pending) { setCreated(null); void navigate(runRoute(created)); } }, [created, m.busy, m.pending, navigate]);
  // Existing work is a read-only resume, never an automatic generation.
  useEffect(() => { if (home?.run_id && !error && entry && entry.status !== 'offered') void navigate(runRoute(home.run_id)); }, [home?.run_id, entry?.status, error, navigate]);
  // This entry promises the invitation course. A future published course must
  // not silently replace it merely because its grant happens to sort first.
  const enrollment = home?.entitlements.find(e => e.status === 'active' && e.course_version_id === 'invitation-course@0.1.0' && courses.some(c => c.id === e.course_version_id && c.state === 'published'));
  async function begin() {
    if (home?.run_id) { setCreated(home.run_id); return; }
    if (!home || !enrollment) return;
    await m.run<Run>(`/learners/${encode(learnerId)}/runs`, { expected_revision: home.revision, enrollment_id: enrollment.id }, run => setCreated(run.id));
  }
  return <section className="lp-card lp-first-work"><p className="lp-eyebrow">AI学习 · 你的第一个小作品</p><h2>{entry?.status === 'offered' ? '这是你刚才聊过的想法吗？' : home?.run_id ? '接着做你的作品' : '跟松伴做一张邀请卡'}</h2>
    <p>先想一想，再做出来，最后亲手改一改。松伴会陪你走过每一步。</p>
    {error && <><Notice error>{error}</Notice><button onClick={() => void load().catch(() => {})}>重新读取学习准备</button></>}
    {!home && !error && <Notice>正在恢复你的学习记录…</Notice>}
    <MutationNotice mutation={m} />
    {entry?.status === 'offered' ? <><SummaryText summary={entry} /><div className="lp-actions"><button className="lp-primary" disabled={m.locked || !config.learning_enabled} onClick={() => void m.run(`/learners/${encode(learnerId)}/entry/confirm`, { expected_revision: entry.revision, decision: 'accept' })}>这是我的想法，继续</button><button disabled={m.locked || !config.learning_enabled} onClick={() => void m.run(`/learners/${encode(learnerId)}/entry/confirm`, { expected_revision: entry.revision, decision: 'decline' })}>暂不采用，从简单提示开始</button></div></>
      : home && <>{entry?.status === 'confirmed' && <details><summary>我确认的起点</summary><SummaryText summary={entry} /></details>}
        {home.run_id || enrollment ? <><p>先试着做一张“班级活动邀请卡”。刚才的兴趣可以帮助松伴理解你，本课仍以邀请卡为作品。</p><button className="lp-primary" disabled={m.locked || !!error || !config.learning_enabled || (!home.run_id && !home.allowed_actions.includes('createRun'))} onClick={() => void begin()}>{home.run_id ? '继续我的作品' : '开始我的第一个作品'}</button></>
          : <Notice>这节课还没有开启。请家长在管理页确认课程资格或联系项目支持；不用再填写问卷。<button onClick={() => void navigate('#/family')}>请家长帮我准备</button></Notice>}
      </>}
    <div className="lp-actions"><button onClick={() => void navigate('#/learn/start')}>调整帮助方式（选填）</button><button onClick={() => void navigate('#/learn/works')}>查看我的作品</button></div>
  </section>;
}
