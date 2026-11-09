import { createRoot } from 'react-dom/client';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { LearningApi } from './api';
import { LearningEntry } from './LearningEntry';
import { FamilyPage } from './FamilyPage';
import { StartPage } from './StartPage';
import { HomePage } from './HomePage';
import { FirstWorkPage } from './FirstWorkPage';
import { CourseHallPage } from './CourseHallPage';
import { PlatformHallPage } from './PlatformHallPage';
import { CourseSeriesPage } from './CourseSeriesPage';
import { PlatformPortfolioPage } from './PlatformPortfolioPage';
import { PlatformNavigation } from './PlatformNavigation';
import { CreativeStudio } from '../creative-studio';
import type { WorkDetail } from '../platform/portfolio';
import { RunPage } from './RunPage';
import { WorksPage } from './WorksPage';
import { ReviewAdmin } from './ReviewAdmin';
import { UsageReconciliation } from './UsageReconciliation';
import { creativeRoute, parseRoute, validRoute } from './routes';
import { Dialog, Notice, useGuard, type LeaveGuard } from './ui';
import type { CourseId, MountHandle, MountOptions, Route, Session } from './types';
import './learning.css';
import './platform.css';
export type { MountHandle, MountOptions, Route } from './types';
interface Bridge { navigate?: MountHandle['navigate']; canLeave?: MountHandle['canLeave'] }
const entryGuard = () => {};
const platformEnabled = !!document.querySelector('meta[name="songban-platform"]');
const creativeEnabled = document.querySelector('meta[name="songban-creative-studio"]')?.getAttribute('content') === '1';
const serverAdminEnabled = !!document.querySelector('meta[name="songban-server-admin"]');
const demoLearningEnabled = document.querySelector('meta[name="songban-learning-demo-entry"]')?.getAttribute('content') === '1';
const childDemoRoute = (route: Route): Route => demoLearningEnabled && route === '#/family'
  ? creativeEnabled ? '#/learn/create' : '#/learn/first' : route;
function App({ api, options, bridge }: { api: LearningApi; options: MountOptions; bridge: Bridge }) {
  const identity = useSyncExternalStore(api.subscribe, api.snapshot);
  const readyBoundary = useRef<number | null>(null);
  if (identity.phase === 'ready') readyBoundary.current = identity.boundary;
  const initialRoute = childDemoRoute(options.initialRoute && validRoute(options.initialRoute) ? options.initialRoute : '#/learn');
  const [route, setRoute] = useState<Route>(initialRoute);
  const learningTarget = useRef<Route>(!['#/family', '#/learning-admin'].includes(initialRoute) ? initialRoute : '#/learn');
  const courseReturn = useRef<Route | null>(null);
  const targetLearner = useRef<string | null>(null);
  if (identity.phase === 'ready' && identity.session?.mode === 'learner' && !targetLearner.current) targetLearner.current = identity.session.learner_id;
  const [auth, setAuth] = useState(false), [message, setMessage] = useState(''), [leave, setLeave] = useState<((allow: boolean) => void) | null>(null);
  const [switchingIdentity, setSwitchingIdentity] = useState(false);
  const [currentWork, setCurrentWork] = useState<WorkDetail | null>(null);
  const guard = useRef<LeaveGuard>({ dirty: false }), heading = useRef<HTMLHeadingElement>(null), leaveRef = useRef<((allow: boolean) => void) | null>(null);
  const pageGuard = useRef<LeaveGuard>({ dirty: false }), companionDirty = useRef(false);
  const setGuard = useCallback((g: LeaveGuard) => { pageGuard.current = g; guard.current = { dirty: g.dirty || companionDirty.current, save: companionDirty.current ? undefined : g.save }; }, []);
  const setCreativeDirty = useCallback((dirty: boolean) => setGuard({ dirty }), [setGuard]);
  const creativeSelected = useCallback((id: string | null) => {
    // The studio already completed the current operation / guarded selection.
    // Updating its bookmark must not open a second leave dialog during receipt.
    const next = id ? creativeRoute(id) : '#/learn/create'; learningTarget.current = next;
    targetLearner.current = api.snapshot().session?.learner_id || null;
    setRoute(next); options.onRouteChange?.(next);
  }, [api, options]);
  const canLeave = useCallback(async () => {
    if (!guard.current.dirty) return true;
    if (leaveRef.current) return false;
    return new Promise<boolean>(resolve => { leaveRef.current = resolve; setLeave(() => resolve); });
  }, []);
  const answerLeave = (allow: boolean) => { leaveRef.current?.(allow); leaveRef.current = null; setLeave(null); };
  const navigate = useCallback(async (next: Route) => {
    next = childDemoRoute(next);
    if (!validRoute(next) || !(await canLeave())) return false;
    if (parseRoute(next)?.page === '#/learn/course') courseReturn.current = next;
    if (parseRoute(learningTarget.current)?.page === '#/learn/course' && parseRoute(next)?.page === '#/learn/create') courseReturn.current = learningTarget.current;
    if (!['#/family', '#/learning-admin'].includes(next)) { learningTarget.current = next; targetLearner.current = api.snapshot().session?.learner_id || null; }
    setRoute(next); setAuth(false); options.onRouteChange?.(next); return true;
  }, [api, canLeave, options]);
  useEffect(() => { bridge.navigate = navigate; bridge.canLeave = canLeave; return () => { bridge.navigate = undefined; bridge.canLeave = undefined; }; }, [bridge, navigate, canLeave]);
  useEffect(() => { if (demoLearningEnabled && options.initialRoute === '#/family') options.onRouteChange?.(initialRoute); }, [options, initialRoute]);
  useEffect(() => { void api.revalidate(); return () => { leaveRef.current?.(false); }; }, [api]);
  useEffect(() => { const before = (e: BeforeUnloadEvent) => { if (guard.current.dirty) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before); }, []);
  useEffect(() => { guard.current = { dirty: false }; pageGuard.current = { dirty: false }; companionDirty.current = false; setCurrentWork(null); answerLeave(false); }, [identity.boundary]);
  useEffect(() => { heading.current?.focus(); }, [route, auth]);
  const session = identity.session, config = identity.config;
  const parsed = parseRoute(route)!;
  const changing = identity.phase === 'checking' || identity.phase === 'loading';
  const platformHall = platformEnabled && ['#/learn/courses', '#/hackathon', '#/hackathon/intro'].includes(route);
  const platformPortfolio = platformEnabled && route === '#/portfolio' && !!session && session.mode !== 'staff';
  const creativePage = creativeEnabled && parsed.page === '#/learn/create';
  const seriesPage = parsed.page === '#/learn/course' && !!parsed.id;
  const platformContent = !auth && (platformHall || platformPortfolio || creativePage || seriesPage);
  const identityKey = `${identity.boundary}:${session?.id || 'anonymous'}:${session?.mode_epoch || 0}`;
  async function change(kind: 'authenticate' | 'enter-learner' | 'logout' | 'demo-start', fields: Record<string, unknown> = {}) {
    if (switchingIdentity) return;
    setSwitchingIdentity(true); setMessage(''); setAuth(false);
    const switchedChild = kind === 'enter-learner' && targetLearner.current && targetLearner.current !== fields.learner_id;
    const pendingTarget = parseRoute(learningTarget.current)?.page === '#/learn/course' ? learningTarget.current : !config?.studio_enabled || switchedChild ? '#/learn' : learningTarget.current;
    try { await api.changeIdentity(kind, fields); if (kind === 'enter-learner' || kind === 'demo-start') { const target = pendingTarget === '#/learn' && config?.studio_enabled ? '#/learn/first' : pendingTarget; learningTarget.current = target; targetLearner.current = api.snapshot().session?.learner_id || null; setRoute(target); options.onRouteChange?.(target); } else if (kind === 'logout') { learningTarget.current = '#/learn'; targetLearner.current = null; } }
    catch { setMessage('这次身份操作未确认成功。已重新核对当前会话，请按当前身份继续；若还缺学习授权，请到学习准备中核对。'); }
    finally { setSwitchingIdentity(false); }
  }
  return <div data-learning-root="" className={`lp-root${platformEnabled ? ' lp-unified-shell' : ''}${seriesPage ? ' lp-workbench-page' : ''}${(config?.studio_enabled && parsed.page === '#/learn/run') || creativePage ? ' lp-studio-page' : ''}${creativePage ? ' lp-creative-page' : ''}`}>
    {platformEnabled && <><PlatformNavigation key={identityKey} api={api} session={session} route={route} disabled={changing || switchingIdentity} navigate={navigate} /><header className="lp-platform-header"><div className="lp-platform-brand"><img src="/static/design/pine-mascot.png" alt="" width="43" height="43" /><span>松伴 SONGBAN</span></div></header></>}
    {!platformContent && <header className="lp-header"><img src="/static/design/pine-mascot.png" alt="" width="64" height="64" /><div><span className="lp-eyebrow">松伴 · 一起慢慢学</span><h1 tabIndex={-1} ref={heading}>{session?.mode === 'staff' || route === '#/learning-admin' ? '复核待办' : route === '#/family' ? '家庭与授权' : parsed.page === '#/learn/run' ? '做好眼前这一步' : parsed.page === '#/learn/works' ? '看看留下的作品' : parsed.page === '#/learn/courses' ? '找一个想做的小作品' : '找到舒服的开始方式'}</h1></div></header>}
    <div className="lp-content">
      {config?.notice && !platformContent && !['#/learn/run', '#/learn/works', '#/learn/first', '#/learn/courses', '#/learning-admin'].includes(parsed.page) && !(config.studio_enabled && parsed.page === '#/learn') && session?.mode !== 'staff' && <Notice>{config.notice}</Notice>}
      {config && !config.learning_enabled && <Notice>学习入口暂未开放，已保存的记录可在授权范围内查看。</Notice>}
      {message && <Notice error>{message}</Notice>}
      {changing && <Notice>正在核对当前身份…</Notice>}
      {identity.phase === 'error' && <section className="lp-card"><Notice error>{identity.notice}</Notice><button className="lp-primary" onClick={() => void api.revalidate()}>重新核对身份</button></section>}
      <div hidden={identity.phase !== 'ready'}>
        {platformEnabled && <details className="lp-account-menu" key={route}><summary>账号与学习设置</summary><nav className="lp-actions" aria-label="学习准备页面">
          {session?.mode === 'learner' && <><button onClick={() => void navigate(config?.studio_enabled ? '#/learn/first' : '#/learn')}>继续我的作品</button><button onClick={() => void navigate('#/learn/start')}>调整帮助方式</button></>}
          {!demoLearningEnabled && session?.mode === 'manager' && <button onClick={() => void navigate('#/family')}>家庭资料</button>}
          {session?.mode === 'staff' && <button onClick={() => void navigate('#/learning-admin')}>我的复核待办</button>}
          {serverAdminEnabled && session && ['manager', 'staff'].includes(session.mode) && <a href="/server-admin" onClick={async event => { if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return; event.preventDefault(); if (await canLeave()) location.assign('/server-admin'); }}>服务端管理</a>}
          {session && <button onClick={async () => { if (await canLeave()) await change('logout'); }}>退出当前身份</button>}
        </nav></details>}
        {!platformEnabled && <nav className="lp-actions" aria-label="学习准备页面">
          {session?.mode === 'learner' && <><button aria-current={route === '#/learn' || route === '#/learn/first' ? 'page' : undefined} onClick={() => void navigate(config?.studio_enabled ? '#/learn/first' : '#/learn')}>{config?.studio_enabled ? '继续我的作品' : '我的学习起点'}</button><button onClick={() => void navigate('#/learn/start')}>调整帮助方式</button></>}
          {session?.mode === 'learner' && config?.catalog_enabled && <button aria-current={route === '#/learn/courses' ? 'page' : undefined} onClick={() => void navigate('#/learn/courses')}>课程大厅</button>}
          {!demoLearningEnabled && <button onClick={async () => { if (await canLeave()) { setRoute('#/family'); setAuth(session?.mode !== 'manager'); options.onRouteChange?.('#/family'); } }}>家长管理</button>}
          {session?.mode === 'staff' && <button onClick={() => void navigate('#/learning-admin')}>我的复核待办</button>}
          {serverAdminEnabled && session && ['manager', 'staff'].includes(session.mode) && <a href="/server-admin" onClick={async event => { if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return; event.preventDefault(); if (await canLeave()) location.assign('/server-admin'); }}>服务端管理</a>}
          {session && <button onClick={async () => { if (await canLeave()) await change('logout'); }}>退出当前身份</button>}
        </nav>}
        {readyBoundary.current === identity.boundary && <div key={`${identity.boundary}:${session?.id || 'anonymous'}`}>
          {creativePage && courseReturn.current && <button onClick={()=>void navigate(courseReturn.current!)}>返回刚才的课程</button>}
          {seriesPage && !auth ? <CourseSeriesPage key={`${identityKey}:${parsed.id}`} api={api} id={parsed.id as CourseId} session={session} config={config} setGuard={setGuard} navigate={navigate} creativeEnabled={creativeEnabled} entry={<LearningEntry api={api} session={session} route={route} demo={demoLearningEnabled} busy={switchingIdentity} startDemo={()=>change('demo-start')} enter={id=>change('enter-learner',{learner_id:id})} navigate={navigate} setGuard={entryGuard}/>}/>
            : platformHall && !auth ? <PlatformHallPage api={api} session={session} config={config} page={route==='#/hackathon'?'hackathon':route==='#/hackathon/intro'?'hackathon-intro':'ai'} navigate={navigate} canLeave={canLeave} setGuard={setGuard} creativeEnabled={creativeEnabled}/>
            : (platformEnabled || demoLearningEnabled) && !auth && !['#/family', '#/learning-admin'].includes(route) && (!session || session.mode === 'manager') && !platformPortfolio
              ? <LearningEntry api={api} session={session} route={route} demo={demoLearningEnabled} busy={switchingIdentity} startDemo={() => change('demo-start')} enter={id => change('enter-learner', {learner_id:id})} navigate={navigate} setGuard={setGuard}/>
            : (!session || auth || (session.mode === 'learner' && route === '#/family')) ? <Login staff={route === '#/learning-admin'} onSubmit={(account, proof) => change('authenticate', { account, proof })} setGuard={setGuard} />
            : session.mode === 'staff' ? <StaffWorkspace api={api} session={session} setGuard={setGuard} />
            : route === '#/learning-admin' ? <Notice>这个账号没有复核权限。请使用本人家庭或学习入口。</Notice>
            : platformPortfolio && (session.mode === 'learner' || session.mode === 'manager') ? <PlatformPortfolioPage api={api} session={session} identityKey={identityKey} navigate={navigate} canLeave={canLeave} setGuard={setGuard} onCurrentWork={setCurrentWork} creativeEnabled={creativeEnabled} />
            : session.mode === 'manager' && config ? <FamilyPage api={api} config={config} setGuard={setGuard} enter={id => change('enter-learner', { learner_id: id })} />
            : session.mode === 'learner' && session.learner_id && config ? parsed.page === '#/learn/create' ? creativeEnabled ? <CreativeStudio key={parsed.id || 'new-idea'} api={api} identityKey={identityKey} learnerId={session.learner_id} initialProjectId={parsed.id} onProjectChange={creativeSelected} onDirty={setCreativeDirty} beforeTransition={canLeave} onOpenPortfolio={() => void navigate('#/portfolio')} /> : <Notice>编程创作工作台暂未开放，已保存的课程和作品仍可从原入口查看。</Notice>
              : parsed.page === '#/learn/run' && parsed.id ? <RunPage key={parsed.id} api={api} learnerId={session.learner_id} id={parsed.id} config={config} setGuard={setGuard} canLeave={canLeave} navigate={navigate} review={parsed.review} />
              : parsed.page === '#/learn/works' || (!platformEnabled && route === '#/portfolio') ? <WorksPage key={route} api={api} learnerId={session.learner_id} id={parsed.id} version={parsed.version} navigate={navigate} setGuard={setGuard} />
              : route === '#/learn/start' ? <StartPage key={route} api={api} learnerId={session.learner_id} config={config} setGuard={setGuard} edit={() => void navigate('#/learn/start')} />
              : route === '#/learn/courses' ? <CourseHallPage api={api} learnerId={session.learner_id} config={config} setGuard={setGuard} navigate={navigate} />
              : (platformEnabled || config.studio_enabled) && (route === '#/learn/first' || route === '#/learn') ? <FirstWorkPage api={api} learnerId={session.learner_id} config={config} setGuard={setGuard} navigate={navigate} creativeEnabled={creativeEnabled} />
              : <HomePage api={api} learnerId={session.learner_id} config={config} setGuard={setGuard} navigate={navigate} />
            : <Notice>这个会话不提供家庭管理视图。请使用获准的管理入口，或重新认证家长账号。</Notice>}
        </div>}
      </div>
    </div>
    {leave && <Dialog title="这些修改还没保存" close={() => answerLeave(false)}><p>留在这里继续填写，或确认后离开。未保存内容仅在当前页面保留。</p><div className="lp-actions"><button autoFocus onClick={() => answerLeave(false)}>留在这里</button>{guard.current.save && <button className="lp-primary" onClick={async () => { if (await guard.current.save?.()) answerLeave(true); }}>保存后离开</button>}<button onClick={() => answerLeave(true)}>放弃本次修改</button></div></Dialog>}
  </div>;
}
function StaffWorkspace({ api, session, setGuard }: { api: LearningApi; session: Session; setGuard: (g: LeaveGuard) => void }) {
  const [reviewDirty, setReviewDirty] = useState(false), [usageDirty, setUsageDirty] = useState(false);
  useGuard(setGuard, reviewDirty || usageDirty);
  return <><ReviewAdmin api={api} session={session} onDirty={setReviewDirty} />{session.scopes.includes('usage_reconcile') && <UsageReconciliation api={api} onDirty={setUsageDirty} />}</>;
}
function Login({ onSubmit, setGuard, staff = false }: { staff?: boolean; onSubmit: (account: string, proof: string) => Promise<void>; setGuard: (g: LeaveGuard) => void }) {
  const [account, setAccount] = useState(''), [proof, setProof] = useState('');
  useEffect(() => { setGuard({ dirty: !!account || !!proof }); return () => setGuard({ dirty: false }); }, [account, proof, setGuard]);
  return <section className="lp-card"><h2>{staff ? '请复核人员重新认证' : '请家长重新认证'}</h2><p>{staff ? '仅已获准且被分配的人员可以处理材料。' : '使用已有账号和密码进入家庭管理。返回管理需要再次认证。'}</p><form onSubmit={e => { e.preventDefault(); const secret = proof; setProof(''); void onSubmit(account.trim(), secret); }}>
    <label htmlFor="lp-account">已有账号</label><input id="lp-account" required maxLength={100} autoComplete="username" value={account} onChange={e => setAccount(e.target.value)} />
    <label htmlFor="lp-password">密码</label><input id="lp-password" required type="password" maxLength={8000} autoComplete="current-password" value={proof} onChange={e => setProof(e.target.value)} />
    <button className="lp-primary" disabled={!account.trim() || !proof}>重新认证并进入管理</button></form></section>;
}
const mounts = new WeakMap<HTMLElement, MountHandle>();
export function mount(host: HTMLElement, options: MountOptions = {}): MountHandle {
  mounts.get(host)?.unmount();
  const api = new LearningApi(options), root = createRoot(host), bridge: Bridge = {};
  let active = true;
  root.render(<App api={api} options={options} bridge={bridge} />);
  const handle: MountHandle = {
    navigate: route => bridge.navigate?.(route) || Promise.resolve(false),
    canLeave: () => bridge.canLeave?.() || Promise.resolve(true), revalidate: api.revalidate,
    unmount() { if (!active) return; active = false; api.dispose(); root.unmount(); mounts.delete(host); options.onUnmount?.(); },
  };
  mounts.set(host, handle); return handle;
}
declare global { interface Window { SongbanLearning: { mount: typeof mount } } }
window.SongbanLearning = { mount };
