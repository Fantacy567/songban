import { createRoot } from 'react-dom/client';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { LearningApi } from './api';
import { FamilyPage } from './FamilyPage';
import { StartPage } from './StartPage';
import { HomePage } from './HomePage';
import { FirstWorkPage } from './FirstWorkPage';
import { CourseHallPage } from './CourseHallPage';
import { RunPage } from './RunPage';
import { WorksPage } from './WorksPage';
import { ReviewAdmin } from './ReviewAdmin';
import { UsageReconciliation } from './UsageReconciliation';
import { parseRoute, validRoute } from './routes';
import { Dialog, Notice, useGuard, type LeaveGuard } from './ui';
import type { MountHandle, MountOptions, Route, Session } from './types';
import './learning.css';
export type { MountHandle, MountOptions, Route } from './types';
interface Bridge { navigate?: MountHandle['navigate']; canLeave?: MountHandle['canLeave'] }
function App({ api, options, bridge }: { api: LearningApi; options: MountOptions; bridge: Bridge }) {
  const identity = useSyncExternalStore(api.subscribe, api.snapshot);
  const readyBoundary = useRef<number | null>(null);
  if (identity.phase === 'ready') readyBoundary.current = identity.boundary;
  const [route, setRoute] = useState<Route>(options.initialRoute && validRoute(options.initialRoute) ? options.initialRoute : '#/learn');
  const learningTarget = useRef<Route>(options.initialRoute && validRoute(options.initialRoute) && !['#/family', '#/learning-admin'].includes(options.initialRoute) ? options.initialRoute : '#/learn');
  const targetLearner = useRef<string | null>(null);
  if (identity.phase === 'ready' && identity.session?.mode === 'learner' && !targetLearner.current) targetLearner.current = identity.session.learner_id;
  const [auth, setAuth] = useState(false), [message, setMessage] = useState(''), [leave, setLeave] = useState<((allow: boolean) => void) | null>(null);
  const guard = useRef<LeaveGuard>({ dirty: false }), heading = useRef<HTMLHeadingElement>(null), leaveRef = useRef<((allow: boolean) => void) | null>(null);
  const setGuard = useCallback((g: LeaveGuard) => { guard.current = g; }, []);
  const canLeave = useCallback(async () => {
    if (!guard.current.dirty) return true;
    if (leaveRef.current) return false;
    return new Promise<boolean>(resolve => { leaveRef.current = resolve; setLeave(() => resolve); });
  }, []);
  const answerLeave = (allow: boolean) => { leaveRef.current?.(allow); leaveRef.current = null; setLeave(null); };
  const navigate = useCallback(async (next: Route) => {
    if (!validRoute(next) || !(await canLeave())) return false;
    if (!['#/family', '#/learning-admin'].includes(next)) { learningTarget.current = next; targetLearner.current = api.snapshot().session?.learner_id || null; }
    setRoute(next); setAuth(false); options.onRouteChange?.(next); return true;
  }, [api, canLeave, options]);
  useEffect(() => { bridge.navigate = navigate; bridge.canLeave = canLeave; return () => { bridge.navigate = undefined; bridge.canLeave = undefined; }; }, [bridge, navigate, canLeave]);
  useEffect(() => { void api.revalidate(); return () => { leaveRef.current?.(false); }; }, [api]);
  useEffect(() => { const before = (e: BeforeUnloadEvent) => { if (guard.current.dirty) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before); }, []);
  useEffect(() => { guard.current = { dirty: false }; answerLeave(false); }, [identity.boundary]);
  useEffect(() => { heading.current?.focus(); }, [route, auth]);
  const session = identity.session, config = identity.config;
  const parsed = parseRoute(route)!;
  const changing = identity.phase === 'checking' || identity.phase === 'loading';
  async function change(kind: 'authenticate' | 'enter-learner' | 'logout', fields: Record<string, unknown> = {}) {
    setMessage(''); setAuth(false);
    const switchedChild = kind === 'enter-learner' && targetLearner.current && targetLearner.current !== fields.learner_id;
    const pendingTarget = !config?.studio_enabled || switchedChild ? '#/learn' : learningTarget.current;
    try { await api.changeIdentity(kind, fields); if (kind === 'enter-learner') { const target = pendingTarget === '#/learn' && config?.studio_enabled ? '#/learn/first' : pendingTarget; learningTarget.current = target; targetLearner.current = String(fields.learner_id); setRoute(target); options.onRouteChange?.(target); } else if (kind === 'logout') { learningTarget.current = '#/learn'; targetLearner.current = null; } }
    catch { setMessage('这次身份操作未确认成功。已重新核对当前会话，请按当前身份继续或重新输入密码。'); }
  }
  return <div data-learning-root="" className={`lp-root${config?.studio_enabled && parsed.page === '#/learn/run' ? ' lp-studio-page' : ''}`}>
    <header className="lp-header"><img src="/static/design/pine-mascot.png" alt="" width="64" height="64" /><div><span className="lp-eyebrow">松伴 · 一起慢慢学</span><h1 tabIndex={-1} ref={heading}>{session?.mode === 'staff' || route === '#/learning-admin' ? '复核待办' : route === '#/family' ? '家庭与授权' : parsed.page === '#/learn/run' ? '做好眼前这一步' : parsed.page === '#/learn/works' ? '看看留下的作品' : parsed.page === '#/learn/courses' ? '找一个想做的小作品' : '找到舒服的开始方式'}</h1></div></header>
    <div className="lp-content">
      {config?.notice && !['#/learn/run', '#/learn/works', '#/learn/first', '#/learn/courses', '#/learning-admin'].includes(parsed.page) && !(config.studio_enabled && parsed.page === '#/learn') && session?.mode !== 'staff' && <Notice>{config.notice}</Notice>}
      {config && !config.learning_enabled && <Notice>学习入口暂未开放，已保存的记录可在授权范围内查看。</Notice>}
      {message && <Notice error>{message}</Notice>}
      {changing && <Notice>正在核对当前身份…</Notice>}
      {identity.phase === 'error' && <section className="lp-card"><Notice error>{identity.notice}</Notice><button className="lp-primary" onClick={() => void api.revalidate()}>重新核对身份</button></section>}
      <div hidden={identity.phase !== 'ready'}>
        <nav className="lp-actions" aria-label="学习准备页面">
          {session?.mode === 'learner' && <><button aria-current={route === '#/learn' || route === '#/learn/first' ? 'page' : undefined} onClick={() => void navigate(config?.studio_enabled ? '#/learn/first' : '#/learn')}>{config?.studio_enabled ? '继续我的作品' : '我的学习起点'}</button><button onClick={() => void navigate('#/learn/start')}>调整帮助方式</button></>}
          {session?.mode === 'learner' && config?.catalog_enabled && <button aria-current={route === '#/learn/courses' ? 'page' : undefined} onClick={() => void navigate('#/learn/courses')}>课程大厅</button>}
          <button onClick={async () => { if (await canLeave()) { setRoute('#/family'); setAuth(session?.mode !== 'manager'); options.onRouteChange?.('#/family'); } }}>家长管理</button>
          {session?.mode === 'staff' && <button onClick={() => void navigate('#/learning-admin')}>我的复核待办</button>}
          {session && <button onClick={async () => { if (await canLeave()) await change('logout'); }}>退出当前身份</button>}
        </nav>
        {readyBoundary.current === identity.boundary && <div key={`${identity.boundary}:${session?.id || 'anonymous'}`}>
          {(!session || auth || (session.mode === 'learner' && route === '#/family')) ? <Login staff={route === '#/learning-admin'} onSubmit={(account, proof) => change('authenticate', { account, proof })} setGuard={setGuard} />
            : session.mode === 'staff' ? <StaffWorkspace api={api} session={session} setGuard={setGuard} />
            : route === '#/learning-admin' ? <Notice>这个账号没有复核权限。请使用本人家庭或学习入口。</Notice>
            : session.mode === 'manager' && config ? <FamilyPage api={api} config={config} setGuard={setGuard} enter={id => change('enter-learner', { learner_id: id })} />
            : session.mode === 'learner' && session.learner_id && config ? parsed.page === '#/learn/run' && parsed.id ? <RunPage key={parsed.id} api={api} learnerId={session.learner_id} id={parsed.id} config={config} setGuard={setGuard} canLeave={canLeave} navigate={navigate} review={parsed.review} />
              : parsed.page === '#/learn/works' ? <WorksPage key={route} api={api} learnerId={session.learner_id} id={parsed.id} version={parsed.version} navigate={navigate} setGuard={setGuard} />
              : route === '#/learn/start' ? <StartPage key={route} api={api} learnerId={session.learner_id} config={config} setGuard={setGuard} edit={() => void navigate('#/learn/start')} />
              : route === '#/learn/courses' ? <CourseHallPage api={api} learnerId={session.learner_id} config={config} setGuard={setGuard} navigate={navigate} />
              : config.studio_enabled && (route === '#/learn/first' || route === '#/learn') ? <FirstWorkPage api={api} learnerId={session.learner_id} config={config} setGuard={setGuard} navigate={navigate} />
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
