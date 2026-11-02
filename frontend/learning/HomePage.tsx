import { useCallback, useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Course, Home, Run } from './contracts';
import type { Config, Route } from './types';
import { StartPage } from './StartPage';
import { Notice, useGuard, type SetGuard } from './ui';
import { encode, lessonError, MutationNotice, progressLabels, stages, useLessonMutation } from './workspace';
import { runRoute } from './routes';
export function HomePage({ api, learnerId, config, setGuard, navigate }: { api: LearningApi; learnerId: string; config: Config; setGuard: SetGuard; navigate: (route: Route) => Promise<boolean> }) {
  const [home, setHome] = useState<Home | null>(null), [courses, setCourses] = useState<Course[]>([]), [error, setError] = useState(''), [loaded, setLoaded] = useState(false);
  const alive = useRef(true), generation = useRef(0);
  const [createdRun, setCreatedRun] = useState<string | null>(null);
  const load = useCallback(async () => {
    const current = ++generation.current;
    const result = await Promise.allSettled([api.request<Home>(`/learners/${encode(learnerId)}/home`), api.request<{ items: Course[] }>('/courses')]);
    if (!alive.current || current !== generation.current) return;
    setLoaded(true);
    if (result[0].status === 'fulfilled' && result[0].value.learner_id === learnerId) { setHome(result[0].value); setError(''); } else setError(lessonError(result[0].status === 'rejected' ? result[0].reason : new Error()));
    if (result[1].status === 'fulfilled') setCourses(result[1].value.items);
  }, [api, learnerId]);
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; ++generation.current; }; }, [load]);
  const mutation = useLessonMutation(api, load);
  useGuard(setGuard, mutation.busy || !!mutation.pending);
  // Navigate only after the mutation's leave guard has settled.
  useEffect(() => { if (createdRun && !mutation.busy && !mutation.pending) { setCreatedRun(null); void navigate(runRoute(createdRun)); } }, [createdRun, mutation.busy, mutation.pending, navigate]);
  const enrollment = home?.entitlements.find(e => e.status === 'active' && courses.some(c => c.id === e.course_version_id && c.state === 'published'));
  if (!home || (!home.run_id && !enrollment)) return <>{loaded ? <p>{home ? '学习准备 · 三关练习尚未开放' : '课程状态暂时未确认，起点仍可填写。'}</p> : <Notice>正在读取课程状态，你也可以先填写起点。</Notice>}{error && <Notice>{error}</Notice>}{home && !enrollment && <Notice>这节课还没有开启，先填写学习起点，请家长帮忙联系老师。</Notice>}<StartPage api={api} learnerId={learnerId} config={config} setGuard={setGuard} summary edit={() => void navigate('#/learn/start')} /><button onClick={() => void load()}>重新读取课程状态</button></>;
  return <><section className="lp-card lp-current"><p className="lp-eyebrow">我的学习 · 当前任务</p><h2>{home.run_id ? '接着上次的任务做' : courses.find(c => c.id === enrollment?.course_version_id)?.title || '班级活动邀请卡'}</h2><p>{home.current_action.label}</p><p>{config.live_enabled ? '进入任务后选择生成方式；模拟和真实调用会分别标明。' : '这是模拟练习，不会调用真实 AI。'}</p><MutationNotice mutation={mutation} />
    {home.run_id ? <button className="lp-primary" onClick={() => void navigate(runRoute(home.run_id!))}>继续当前任务</button> : <button className="lp-primary" disabled={!config.learning_enabled || mutation.locked || !enrollment || !home.allowed_actions.includes('createRun')} onClick={() => void mutation.run<Run>(`/learners/${encode(learnerId)}/runs`, { expected_revision: home.revision, enrollment_id: enrollment!.id }, run => setCreatedRun(run.id))}>开始三关练习</button>}
    <div className="lp-actions"><button onClick={() => void navigate('#/learn/start')}>调整我的起点</button><button onClick={() => void navigate('#/learn/works')}>查看已保存作品</button></div>
  </section><section className="lp-card"><h2>三关地图</h2><ol className="lp-map">{Object.entries(stages).map(([stage, label]) => <li key={stage}><strong>{label}</strong><span>{progressLabels[home.progress.find(p => p.stage === stage)?.state || 'locked']}</span></li>)}</ol><p>保存留下记录；完成情况以当前服务记录为准。</p></section></>;
}
