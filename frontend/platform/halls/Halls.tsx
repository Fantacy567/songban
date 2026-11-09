// Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { HallAction, HallActionHandler, HallButton, HallCover, HallCourse, HallViewProps, HackathonHallState, HackathonIntroState, LearningHallState } from './types';
import './halls.css';

const illustration = '/static/platform/illustrations/';
const imagePaths = ['/static/platform/illustrations/', '/static/learning/covers/'];
function safeCover(src?: string) {
  return !!src && imagePaths.some(prefix => src.startsWith(prefix)) && !/[\\\s?#\u0000-\u001f]/.test(src) && !src.includes('..');
}
function Cover({ cover, title, fallback }: { cover?: HallCover; title: string; fallback: string }) {
  const src = safeCover(cover?.src) ? cover!.src : fallback;
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return <figure className="ph-cover">
    {failed ? <div className="ph-cover-fallback" role="img" aria-label={`${title}：示意图暂时没有加载`}><span aria-hidden="true">松</span><strong>{title}</strong><p>图片暂未加载，仍可继续查看。</p></div>
      : <img src={src} alt={cover?.alt || `${title}的课程示意图`} width="900" height="600" loading="lazy" onError={() => setFailed(true)} />}
    <figcaption>{cover?.label || '松伴原创示意图'}</figcaption>
  </figure>;
}
function useAction(onAction: HallActionHandler) {
  const locked = useRef(false), alive = useRef(true);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function run(action: HallAction) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError('');
    try { await onAction(action); }
    catch { if (alive.current) setError('这次还没有打开成功。已有记录仍保留，可以再试或请松伴解释下一步。'); }
    finally { locked.current = false; if (alive.current) setBusy(false); }
  }
  return { busy, error, run };
}
type Actions = ReturnType<typeof useAction>;
function ActionButton({ item, actions, secondary = false }: { item: HallButton; actions: Actions; secondary?: boolean }) {
  return <button type="button" className={secondary ? 'ph-button ph-button-secondary' : 'ph-button'} disabled={actions.busy || item.disabled} onClick={() => void actions.run(item.action)}>{item.label}<span aria-hidden="true">↗</span></button>;
}
function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className={`ph-notice${error ? ' ph-notice-error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>;
}
function groups(courses: readonly HallCourse[]) {
  const result = new Map<string, { stage: HallCourse['stage']; courses: HallCourse[] }>();
  for (const course of courses) {
    if (course.state !== 'published' && course.state !== 'trial') continue;
    if (!result.has(course.stage.id)) result.set(course.stage.id, { stage: course.stage, courses: [] });
    result.get(course.stage.id)!.courses.push(course);
  }
  return [...result.values()].sort((a, b) => (a.stage.order || 0) - (b.stage.order || 0));
}

export function LearningHall({ state, onAction }: { state: LearningHallState; onAction: HallActionHandler }) {
  const actions = useAction(onAction), stages = groups(state.courses);
  return <section data-platform-halls="" className="ph-shell" aria-labelledby="ph-ai-title" aria-busy={state.status === 'loading'}>
    <header className="ph-page-header"><p className="ph-eyebrow">AI 教学大厅</p><h1 id="ph-ai-title">先做一件小作品，<br />再多学一小步。</h1><p>看看想做出的样子，选一节合适的课。松伴会陪你想、做、改。</p></header>
    {state.resume && <aside className="ph-resume"><div><span className="ph-eyebrow">接着上次做</span><h2>{state.resume.title}</h2><p>{state.resume.description}</p></div><ActionButton item={state.resume.action} actions={actions} /></aside>}
    {state.notice && <Notice>{state.notice}</Notice>}
    {state.status === 'loading' && <Notice>正在读取课程和你可以继续的作品…</Notice>}
    {state.status === 'error' && <><Notice error>{state.error || '课程暂时没有读完整，已保存作品仍保留。'}</Notice><ActionButton secondary item={{ label: '重新读取课程', action: { type: 'retry', page: 'ai' } }} actions={actions} /></>}
    {actions.error && <Notice error>{actions.error}</Notice>}
    {state.status === 'ready' && !stages.length && <div className="ph-empty"><h2>课程还在准备中。</h2><p>准备好后，这里会出现能实际做出作品的课程。已有作品可以继续查看。</p>{!state.resume && <ActionButton secondary item={{ label: '请家长帮我准备', action: { type: 'prepare-learning' } }} actions={actions} />}</div>}
    {state.status === 'ready' && <div className="ph-stages">{stages.map(({ stage, courses }, i) => <section className="ph-stage" key={stage.id} aria-labelledby={`ph-stage-${i}`}>
      <header className="ph-stage-header"><span className="ph-stage-number" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span><div><h2 id={`ph-stage-${i}`}>{stage.title}</h2>{stage.description && <p>{stage.description}</p>}</div></header>
      <div className="ph-course-grid">{courses.map(course => <article className="ph-course-card" key={course.id} data-course-version={course.id}>
        <Cover cover={course.cover} title={course.title} fallback={illustration+'course-work.svg'} />
        <div className="ph-card-body"><h3>{course.title}</h3><p className="ph-card-goal">{course.goal}</p>{course.experience && <p className="ph-caption">{course.experience}</p>}{course.statusLabel && <span className="ph-status">{course.statusLabel}</span>}
          {(course.preparation || course.steps?.length) && <details><summary>这节课会怎么做？</summary>{course.steps?.length ? <ol>{course.steps.map((step, n) => <li key={n}>{step}</li>)}</ol> : null}{course.preparation && <p><strong>开始前：</strong>{course.preparation}</p>}<p className="ph-caption">按自己的节奏练习；封面是教学插画，不是你的已完成作品。</p></details>}
          {course.action ? <ActionButton item={course.action} actions={actions} /> : <p className="ph-unavailable">{course.unavailableReason || '这节课的准备状态还需要核对。'}</p>}
        </div>
      </article>)}</div>
    </section>)}</div>}
  </section>;
}

function practiceAction(state: Pick<HackathonHallState, 'practice' | 'practiceEnabled'> | HackathonIntroState): HallButton {
  return state.practice ? { label: '继续上次的实践', action: { type: 'resume-practice', teamId: state.practice.teamId }, disabled: state.practiceEnabled === false }
    : { label: '开始我的第一次实践', action: { type: 'begin-practice' }, disabled: state.practiceEnabled === false };
}

export function HackathonHall({ state, onAction }: { state: HackathonHallState; onAction: HallActionHandler }) {
  const actions = useAction(onAction), start = practiceAction(state);
  return <section data-platform-halls="" className="ph-shell" aria-labelledby="ph-hackathon-title" aria-busy={state.status === 'loading'}>
    <header className="ph-page-header"><p className="ph-eyebrow">黑客松教学大厅</p><h1 id="ph-hackathon-title">先认识黑客松，<br />再一起做点什么。</h1><p>从一个小队的故事开始，看看大家怎样找到问题、动手尝试、分享作品。</p></header>
    {state.status === 'loading' && <Notice>正在核对你上次的实践，已有记录不会重新创建。</Notice>}
    {state.status === 'error' && <><Notice error>{state.error || '这次还没读到完整的实践记录，可以先认识黑客松。'}</Notice><ActionButton secondary item={{ label: '重新读取实践记录', action: { type: 'retry', page: 'hackathon' } }} actions={actions} /></>}
    {actions.error && <Notice error>{actions.error}</Notice>}
    <div className="ph-hackathon-grid">
      <article className="ph-entry-card" data-hackathon-entry="intro"><Cover title="认识黑客松" cover={{ src: illustration+'hackathon-intro.svg', alt: '虚构小队示意：同学围在桌旁，用便签和草图讨论一个小问题。', label: '松伴原创示意图 · 虚构小队' }} fallback={illustration+'hackathon-intro.svg'} />
        <div className="ph-card-body"><p className="ph-step-label">第一步 · 先了解</p><h2>认识黑客松</h2><p>黑客松是什么？大家会做什么？跟着一个小队的故事，先看明白。</p><ActionButton item={{ label: '先了解黑客松', action: { type: 'hackathon-intro' } }} actions={actions} /></div>
      </article>
      <article className="ph-entry-card" data-hackathon-entry="practice"><Cover title="跟松伴开始一次实践" cover={{ src: illustration+'hackathon-practice.svg', alt: '虚构实践示意：同学分工制作小原型，再向伙伴展示自己的想法。', label: '松伴原创示意图 · 虚构实践' }} fallback={illustration+'hackathon-practice.svg'} />
        <div className="ph-card-body"><p className="ph-step-label">第二步 · 动手试试</p><h2>跟松伴开始一次实践</h2><p>了解赛事、找到伙伴、选出方向，一步步做出作品，再把它讲清楚。</p>
          {state.practice && <div className="ph-current-practice"><strong>{state.practice.title}</strong><span>当前：{state.practice.stageLabel}</span></div>}
          <ActionButton item={{ ...start, disabled: start.disabled || state.status !== 'ready' }} actions={actions} />
          {state.preparationNotice && <p className="ph-caption">{state.preparationNotice}</p>}
        </div>
      </article>
    </div>
    <p className="ph-hall-note">第一次来，可以先从第一张卡的故事开始；已有实践就接着原来的记录继续。</p>
  </section>;
}

const story = [
  { title: '先找到一个想改善的小问题', body: '小松和同学发现：班里的故事交换会，大家总记不清时间和要带的东西。他们想做一张说得清楚的邀请卡。' },
  { title: '和伙伴一起，做出能看见的小作品', body: '有人找资料，有人写内容，有人做页面，也有人帮忙检查。作品可以很小，关键是先让一个具体想法有形状。' },
  { title: '松伴给提示，你来决定和动手', body: '不知道怎么开始时，可以问松伴；得到候选后，自己对照资料、选择、保存并修改。AI 的回复也需要核对。' },
  { title: '把作品讲给别人听', body: '告诉伙伴：你们发现了什么问题，做了什么，哪里可以试用，还有哪些没做好。能说明一次自己的修改，也是一份收获。' },
  { title: '再看一眼这场活动的要求', body: '每场活动的年龄、时间、地点、组队和提交要求可能不同。故事只是示例，正式实践前要回到本场赛事资料核对。' },
] as const;

export function HackathonIntro({ state, onAction }: { state: HackathonIntroState; onAction: HallActionHandler }) {
  const actions = useAction(onAction), next = practiceAction(state);
  return <section data-platform-halls="" className="ph-shell ph-intro" aria-labelledby="ph-intro-title">
    <ActionButton secondary item={{ label: '返回黑客松教学大厅', action: { type: 'hackathon-hall' } }} actions={actions} />
    <header className="ph-page-header"><p className="ph-eyebrow">认识黑客松</p><h1 id="ph-intro-title">把一个想法，<br />和伙伴一起做出来。</h1><p>黑客松是一段一起发现问题、尝试做作品、展示想法的实践。先跟小松的小队看一看。</p></header>
    <div className="ph-intro-layout"><Cover title="小松的小队故事" cover={{ src: illustration+'hackathon-intro.svg', alt: '小松的小队围桌讨论邀请卡，桌上摆着草图和便签。', label: '教学示例 · 不是真实活动记录' }} fallback={illustration+'hackathon-intro.svg'} />
      <ol className="ph-story">{story.map((part, i) => <li key={part.title}><span className="ph-story-number" aria-hidden="true">{i + 1}</span><div><h2>{part.title}</h2><p>{part.body}</p></div></li>)}</ol>
    </div>
    <section className="ph-next"><div><p className="ph-eyebrow">准备好试一试了吗？</p><h2>下一步，看看怎样开始。</h2><p>松伴会沿着当前阶段给你指引；组队、选题和作品仍由你与伙伴来决定。</p></div><ActionButton item={{ ...next, label: state.practice ? next.label : '我想试一试' }} actions={actions} /></section>
    {state.preparationNotice && <Notice>{state.preparationNotice}</Notice>}{actions.error && <Notice error>{actions.error}</Notice>}
  </section>;
}

export function HallView({ state, onAction }: HallViewProps) {
  if (state.page === 'ai') return <LearningHall state={state} onAction={onAction} />;
  if (state.page === 'hackathon') return <HackathonHall state={state} onAction={onAction} />;
  return <HackathonIntro state={state} onAction={onAction} />;
}
