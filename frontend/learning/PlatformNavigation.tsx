import { useEffect, useState } from 'react';
import type { Route, Session } from './types';
import type { LearningApi } from './api';
import { courseRoute } from './routes';
import { workbenchPath, type SessionSummary } from './workbench/types';

const entries = [
  { route: '#/learn/courses', label: 'AI 教学大厅', short: 'AI 教学', path: 'M4 4h6a3 3 0 0 1 2 1 3 3 0 0 1 2-1h6v15h-6a3 3 0 0 0-2 1 3 3 0 0 0-2-1H4z M12 5v15' },
  { route: '#/hackathon', label: '黑客松教学大厅', short: '黑客松', path: 'M5 21V3 M5 4c5-4 9 4 14 0v10c-5 4-9-4-14 0' },
  { route: '#/portfolio', label: '作品集', short: '作品集', path: 'M3 5h18v15H3z M3 15l5-5 5 5 3-3 5 5 M16 8h.01' },
] as const;

export function PlatformNavigation({ route, disabled, navigate, api, session }: {
  route: Route; disabled: boolean; navigate: (route: Route) => Promise<boolean>; api: LearningApi; session: Session | null;
}) {
  const [recent, setRecent] = useState<SessionSummary[]>([]), [failed, setFailed] = useState(false), [refresh, setRefresh] = useState(0);
  useEffect(() => { const changed = () => setRefresh(n => n + 1); window.addEventListener('songban-workbench-changed', changed); return () => window.removeEventListener('songban-workbench-changed', changed); }, []);
  useEffect(() => {
    let active = true; setFailed(false);
    if (session?.mode !== 'learner' || disabled) { setRecent([]); return; }
    void api.platform<{ items: SessionSummary[] }>(`${workbenchPath}/sessions`).then(data => { if (active) setRecent(data.items.slice(0, 7)); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [api, session?.id, session?.mode_epoch, session?.mode, disabled, route, refresh]);
  return <><aside className="lp-platform-sidebar" aria-label="松伴导航">
    <button className="lp-sidebar-brand" aria-label="返回 AI 教学大厅" disabled={disabled} onClick={() => void navigate('#/learn/courses')}><img src="/static/design/pine-mascot.png" alt=""/>松伴</button>
    <button className="wb-new" disabled={disabled} onClick={() => void navigate('#/learn/first')}>＋ 新探索</button>
    <nav className="sp-primary-nav" aria-label="主导航">
      {entries.map(item => <button key={item.route} disabled={disabled} title={item.label} aria-label={item.label}
        aria-current={(item.route === '#/learn/courses' ? route.startsWith('#/learn') : route.startsWith(item.route)) ? 'page' : undefined}
        onClick={() => void navigate(item.route)}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={item.path} /></svg>
        <span>{item.label}</span>
      </button>)}
    </nav>
    <details className="wb-recent" open><summary>最近会话</summary>{failed ? <button disabled={disabled} onClick={() => setRefresh(n => n + 1)}>重新读取最近会话</button> : recent.length ? recent.map(item => <button key={item.id} disabled={disabled} aria-current={route === courseRoute(item.course_id) ? 'page' : undefined} onClick={() => void navigate(courseRoute(item.course_id))}>{item.title}</button>) : <p>{session?.mode === 'learner' ? '从一门课程开始探索' : '进入学习后继续上次对话'}</p>}</details>
  </aside><details className="wb-mobile-recent"><summary><img src="/static/design/pine-mascot.png" alt="松伴"/>新探索 / 最近会话</summary><div className="wb-mobile-recent-menu"><button disabled={disabled} onClick={() => void navigate('#/learn/first')}>＋ 新探索</button>{recent.map(item => <button key={item.id} disabled={disabled} onClick={() => void navigate(courseRoute(item.course_id))}>{item.title}</button>)}{failed && <button disabled={disabled} onClick={() => setRefresh(n => n + 1)}>重新读取最近会话</button>}</div></details></>;
}
