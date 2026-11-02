import { useCallback, useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Course, Home, Run } from './contracts';
import type { Config, Route } from './types';
import { Notice, useGuard, type SetGuard } from './ui';
import { encode, lessonError, readPages } from './workspace';
import { runRoute } from './routes';
import { coursePresentation, type CoursePresentation } from './course-covers';
import './course-hall.css';

function Cover({ presentation, title }: { presentation: CoursePresentation; title: string }) {
  const [failed, setFailed] = useState(false);
  return <figure className="lp-course-cover">
    {failed ? <div className="lp-course-cover-fallback" role="img" aria-label={`${title}：示例封面暂时没有加载`}><span aria-hidden="true">松</span><strong>{title}</strong><p>示例图暂时没有加载，仍可查看课程。</p></div>
      : <img src={presentation.image} alt={presentation.alt} width="900" height="600" loading="lazy" onError={() => setFailed(true)} />}
    <figcaption>课程作品示例 · 虚构活动</figcaption>
  </figure>;
}

/** Read-only catalogue; starting/resuming still uses the existing first-work workflow. */
export function CourseHallPage({ api, learnerId, config, setGuard, navigate }: { api: LearningApi; learnerId: string; config: Config; setGuard: SetGuard; navigate: (route: Route) => Promise<boolean> }) {
  const [courses, setCourses] = useState<Course[]>([]), [home, setHome] = useState<Home | null>(null), [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true), [courseError, setCourseError] = useState(''), [homeError, setHomeError] = useState(''), [runError, setRunError] = useState(''), [navigating, setNavigating] = useState(false);
  const generation = useRef(0), navigationLock = useRef(false);
  useGuard(setGuard, false);
  const load = useCallback(async () => {
    const epoch = ++generation.current;
    if (!config.catalog_enabled) { setLoading(false); return; }
    setLoading(true); setCourseError(''); setHomeError(''); setRunError(''); setHome(null); setRun(null); setCourses([]);
    const [courseResult, homeResult] = await Promise.allSettled([readPages<Course>(api, '/courses'), api.request<Home>(`/learners/${encode(learnerId)}/home`)]);
    if (epoch !== generation.current) return;
    if (courseResult.status === 'fulfilled') setCourses(courseResult.value.filter(c => c.state === 'published' && coursePresentation(c.id)));
    else setCourseError(lessonError(courseResult.reason));
    if (homeResult.status === 'fulfilled' && homeResult.value.learner_id === learnerId) {
      const h = homeResult.value; setHome(h);
      if (h.run_id) {
        try {
          const current = await api.request<Run>(`/runs/${encode(h.run_id)}`);
          if (epoch !== generation.current) return;
          if (current.id !== h.run_id || current.learner_id !== learnerId) throw new Error('Scope mismatch');
          setRun(current);
        } catch (e) { if (epoch === generation.current) setRunError(lessonError(e)); }
      }
    } else setHomeError(homeResult.status === 'rejected' ? lessonError(homeResult.reason) : '暂时无法核对本人的学习记录，请重新读取。');
    if (epoch === generation.current) setLoading(false);
  }, [api, learnerId, config.catalog_enabled]);
  useEffect(() => { void load(); return () => { ++generation.current; }; }, [load]);
  async function go(target: Route) {
    if (navigationLock.current) return;
    navigationLock.current = true; setNavigating(true);
    try { await navigate(target); } finally { navigationLock.current = false; setNavigating(false); }
  }
  const ownHome = home?.learner_id === learnerId ? home : null;
  const ownRun = run?.learner_id === learnerId ? run : null;
  if (!config.catalog_enabled) return <section className="lp-card"><h2>课程大厅还没有开放</h2><p>已经开始的作品仍可从原入口继续。</p><button onClick={() => void go('#/learn/first')}>回到我的作品</button></section>;
  return <section className="lp-course-hall" aria-labelledby="lp-course-hall-title" aria-busy={loading}>
    <header className="lp-course-hall-heading"><p className="lp-eyebrow">AI学习 · 课程大厅</p><h2 id="lp-course-hall-title">下一个小作品，从这里开始。</h2><p>看看作品的样子，选一个想试的小任务。松伴陪你想、做、改。</p></header>
    <div className="lp-actions"><button onClick={() => void go('#/learn/first')} disabled={navigating}>回到我的创作</button><button onClick={() => void go('#/learn/works')} disabled={navigating}>查看我的作品</button></div>
    {ownHome?.run_id && <aside className="lp-course-resume"><div><strong>你还有一件可以打开的作品</strong><p>查看上次保存的作品和记录。</p></div><button className="lp-primary" disabled={navigating} onClick={() => void go(runRoute(ownHome.run_id!))}>打开上次的作品</button></aside>}
    {loading && <Notice>正在读取课程和你的学习记录…</Notice>}
    {courseError && <Notice error>课程目录暂时没有读完整。{courseError}</Notice>}
    {homeError && <Notice error>还没有确认你的学习资格或进度。{homeError}</Notice>}
    {runError && <Notice>上次作品的详细进度暂未读全，课程卡不会猜测是否完成。{runError}</Notice>}
    {(courseError || homeError || runError) && <button onClick={() => void load()} disabled={loading}>重新读取课程大厅</button>}
    {!loading && !courseError && !courses.length && <div className="lp-course-empty"><h3>课程还在准备中</h3><p>这里会展示已开放、可以做出作品的课程。已有作品可从上方继续查看。</p></div>}
    <div className="lp-course-grid">{courses.map(course => {
      const presentation = coursePresentation(course.id)!;
      const current = ownRun?.course_version_id === course.id ? ownRun : null;
      const completed = !!current?.progress.length && current.progress.every(p => p.state === 'passed');
      const waiting = current?.progress.some(p => p.state === 'pending_review');
      const enrolled = ownHome?.entitlements.some(e => e.learner_id === learnerId && e.course_version_id === course.id && e.status === 'active');
      const canStart = !ownHome?.run_id && enrolled && config.learning_enabled && ownHome?.allowed_actions.includes('createRun');
      const status = current ? completed ? '已经完成' : waiting ? '等待老师反馈' : '正在创作' : homeError || runError ? '学习状态待核对' : !config.learning_enabled ? '学习暂时暂停' : canStart ? '可以开始' : '请家长帮忙准备';
      const target: Route = current ? completed && current.current_artifact_id ? `#/learn/works?id=${encode(current.current_artifact_id)}` : runRoute(current.id) : '#/learn/first';
      const label = current ? completed ? '看看我的作品' : '继续创作' : canStart ? '开始这个作品' : '';
      return <article className="lp-course-card" key={course.id} data-course-version={course.id}>
        <Cover presentation={presentation} title={course.title} />
        <div className="lp-course-body"><span className="lp-course-status">{status}</span><h3>{course.title}</h3><p className="lp-course-goal">{presentation.goal}</p><p className="lp-caption">{presentation.experience}</p>
          <details><summary>这节课会怎么做？</summary><ol>{presentation.steps.map(step => <li key={step}>{step}</li>)}</ol><p><strong>开始前：</strong>{presentation.preparation}</p><p>按自己的节奏练习，完成时间因人而异。</p><p className="lp-caption">示例展示本课支持的卡片格式。开始创作后，这里会留下你自己的想法。</p></details>
          {label ? <button className="lp-primary" disabled={loading || navigating} onClick={() => void go(target)}>{label}</button>
            : homeError || runError ? <p>读到本人记录后，才能确认从哪一步开始。</p>
              : !config.learning_enabled ? <p>新的学习操作暂时暂停，已保存作品按原权限保留。</p>
                : ownHome?.run_id ? <p>先从上方打开已有作品；不同课程的进度不会混在一起。</p>
                  : <><p>这节课还需要家长确认学习准备和课程资格。</p><button disabled={navigating || loading} onClick={() => void go('#/family')}>请家长帮我准备</button></>}
        </div>
      </article>;
    })}</div>
  </section>;
}
