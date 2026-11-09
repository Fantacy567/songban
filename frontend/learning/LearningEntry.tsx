import { useEffect, useState } from 'react';
import type { LearningApi } from './api';
import type { Family, Route, Session } from './types';
import { Notice, useGuard, type SetGuard } from './ui';

/** A learning destination never embeds the family management password form. */
export function LearningEntry({ api, session, route, demo, busy, startDemo, enter, navigate, setGuard }: {
  api: LearningApi; session: Session | null; route: Route; demo: boolean; busy: boolean;
  startDemo: () => Promise<void>; enter: (id: string) => Promise<void>;
  navigate: (route: Route) => Promise<boolean>; setGuard: SetGuard;
}) {
  const [account, setAccount] = useState<'checking' | 'signed-in' | 'anonymous'>('checking');
  const [families, setFamilies] = useState<Family[]>([]), [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  useGuard(setGuard, busy);
  useEffect(() => {
    if (demo) return;
    let live = true;
    const controller = new AbortController();
    if (session?.mode === 'manager') {
      setLoading(true);
      void api.request<{items: Family[]}>('/families').then(data => { if (live) setFamilies(data.items); })
        .catch(() => { if (live) setFailed(true); }).finally(() => { if (live) setLoading(false); });
    } else {
      // This read only chooses an explanation. It never grants a learning identity.
      const token = localStorage.getItem('studio-token') || sessionStorage.getItem('studio-token');
      if (!token) setAccount('anonymous');
      else void fetch('/api/core/me', { headers: { Authorization: `Bearer ${token}` },
        credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: controller.signal })
        .then(result => { if (live) setAccount(result.ok ? 'signed-in' : 'anonymous'); })
        .catch(() => { if (live) setAccount('anonymous'); });
    }
    return () => { live = false; controller.abort(); };
  }, [api, session?.id, demo]);
  const learners = families.flatMap(family => family.learners);
  return <section className="lp-card lp-learning-entry" aria-label="开始学习">
    <p className="lp-eyebrow">和松伴一起动手</p>
    <h2>{demo ? '从一个小想法，开始创作' : session?.mode === 'manager' ? '选择这次的学习者' : '准备好，就从这里开始'}</h2>
    {demo ? <><p>使用已准备好的虚构学习资料，和松伴做一个小作品。已有的演示作品会保留。</p>
      <button className="lp-primary" disabled={busy} onClick={() => void startDemo()}>{busy ? '正在打开作品…' : '开始体验'}</button>
    </> : session?.mode === 'manager' ? <>
      <p>选好后进入孩子的学习空间，继续刚才想做的作品。</p>
      {loading && <Notice>正在读取已准备的学习者…</Notice>}
      {failed && <Notice error>暂时没读到学习资料，可以在学习准备中重新核对。</Notice>}
      {learners.map(learner => <div className="lp-record" key={learner.id}><h3>{learner.display_name}</h3>
        {learner.guardian_link.status === 'verified'
          ? <button className="lp-primary" disabled={busy} onClick={() => void enter(learner.id)}>以这位学习者继续</button>
          : <p>这位学习者还需要完成学习准备。</p>}</div>)}
      {!loading && !failed && !learners.length && <p>还没有准备好的学习者。请家长先完成资料与学习授权。</p>}
      <button onClick={() => void navigate('#/family')}>完成学习准备</button>
    </> : <>
      <p>{account === 'signed-in' ? '账号已登录，还需要确认这次使用的学习身份。请家长完成一次学习准备，之后可以继续这里的作品。'
        : '登录后继续这个作品。第一次学习时，请家长帮助准备学习身份与授权。'}</p>
      {account !== 'signed-in' && <a className="lp-primary" href={`/#/login?next=${encodeURIComponent('/learning-prep' + route)}`}>登录并继续</a>}
      <button onClick={() => void navigate('#/family')}>{account === 'signed-in' ? '完成学习准备' : '已有学习账号，完成学习准备'}</button>
    </>}
  </section>;
}
