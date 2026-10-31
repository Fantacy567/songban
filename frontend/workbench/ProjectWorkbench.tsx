import { useCallback, useEffect, useRef, useState } from 'react';
import { ConversationPanel } from './ConversationPanel';
import { WorkbenchApi, errorText, operationKey, save, saved, dateText } from './songban-adapter';
import type { Context, MountOptions, Session } from './types';

// Goal card, history controls and welcome layout adapted from ai-workbench.tsx.
export function ProjectWorkbench({ options, api }: { options: MountOptions; api: WorkbenchApi }) {
  const scope = `songban:workbench:${encodeURIComponent(options.identityKey)}:${encodeURIComponent(options.teamId || 'personal')}`;
  const [context, setContext] = useState<Context | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true), [creating, setCreating] = useState(false);
  const [error, setError] = useState(''), [denied, setDenied] = useState(false);
  const [renaming, setRenaming] = useState(false), [title, setTitle] = useState(''), [savingTitle, setSavingTitle] = useState(false);
  const renameLock = useRef(false);
  const mounted = useRef(true), creatingLock = useRef(false), readLock = useRef(false);
  const selectedRef = useRef<string | null>(null);
  const mutationEpoch = useRef(0);
  const createKey = useRef(saved<string | null>(`${scope}:create`, null));
  const query = options.teamId ? `?team_id=${encodeURIComponent(options.teamId)}` : '';
  const refresh = useCallback(async () => {
    if (readLock.current || !api.active) return;
    readLock.current = true;
    const epoch = mutationEpoch.current;
    const results = await Promise.allSettled([
      api.request<Context>(`/api/workbench/context${query}`),
      api.request<{ sessions: Session[] }>(`/api/workbench/sessions${query}`),
    ]);
    if (mounted.current && api.active) {
      const failures: string[] = [];
      if (results[0].status === 'fulfilled') setContext(results[0].value);
      else failures.push(errorText(results[0].reason));
      if (results[1].status === 'fulfilled' && epoch === mutationEpoch.current) {
        const list = results[1].value.sessions;
        setSessions(list);
        const previous = selectedRef.current || saved<string | null>(`${scope}:selected`, null);
        const next = list.some(s => s.id === previous) ? previous : list[0]?.id || null;
        selectedRef.current = next; setSelected(next); save(`${scope}:selected`, next);
      } else if (results[1].status === 'rejected') failures.push(errorText(results[1].reason));
      setError(failures.join(' ')); setLoading(false);
    }
    readLock.current = false;
  }, [api, query, scope]);
  useEffect(() => {
    mounted.current = true;
    api.onAccessLost = () => {
      setDenied(true); setContext(null); setSessions([]); setSelected(null);
    };
    api.onContextStale = () => { void refresh(); };
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 30000);
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', visible);
    return () => { mounted.current = false; api.onAccessLost = null; api.onContextStale = null; clearInterval(timer); document.removeEventListener('visibilitychange', visible); };
  }, [api, refresh]);
  async function createSession() {
    if (creatingLock.current || !api.active) return;
    creatingLock.current = true; setCreating(true); setError('');
    mutationEpoch.current++;
    const requestId = createKey.current || operationKey();
    createKey.current = requestId; save(`${scope}:create`, requestId);
    try {
      const { session } = await api.request<{ session: Session }>('/api/workbench/sessions', {
        method: 'POST', body: { request_id: requestId, title: '新的项目讨论', team_id: options.teamId },
      });
      if (!mounted.current || !api.active) return;
      createKey.current = null; save(`${scope}:create`, null);
      setSessions(list => [session, ...list.filter(item => item.id !== session.id)]);
      selectSession(session.id);
    } catch (cause) {
      if (mounted.current && api.active) setError(`${errorText(cause)} 原会话已保留。再次点击新建将核对同一次创建。`);
    } finally { creatingLock.current = false; if (mounted.current && api.active) setCreating(false); }
  }
  function selectSession(id: string) {
    setRenaming(false);
    selectedRef.current = id; setSelected(id); save(`${scope}:selected`, id);
  }
  const updateSession = useCallback((session: Session) => {
    setSessions(list => list.map(item => item.id === session.id ? session : item));
  }, []);
  async function rename() {
    if (!selected || !title.trim() || renameLock.current || !api.active) return;
    const id = selected;
    const key = `${scope}:rename:${id}`;
    const prior = saved<{ request_id: string; title: string } | null>(key, null);
    const command = prior?.title === title.trim() ? prior : { request_id: operationKey(), title: title.trim() };
    save(key, command);
    renameLock.current = true; setSavingTitle(true); setError(''); mutationEpoch.current++;
    try {
      const data = await api.request<{ session: Session }>(`/api/workbench/sessions/${encodeURIComponent(id)}`, { method: 'PATCH', body: command });
      if (!mounted.current || !api.active) return;
      updateSession(data.session);
      save(key, null);
      if (selectedRef.current === id) setRenaming(false);
    } catch (cause) { if (mounted.current && api.active) setError(errorText(cause)); }
    finally { renameLock.current = false; if (mounted.current) setSavingTitle(false); }
  }
  if (denied) return <section className="sbw"><p className="sbw-error" role="alert">登录或团队权限已变化，私人内容已收起。请重新登录或切换到可访问的范围。</p></section>;
  return <section className="sbw" aria-label="项目工作台">
    <header className="sbw-heading"><div><p className="sbw-eyebrow">一点点想清楚，一步步做出来</p><h1>项目工作台</h1><p className="sbw-muted">从一份材料、一个想法，或眼前的一步开始。</p></div><span className="sbw-scope">{context?.team?.name || (options.teamId ? '团队范围' : '个人空间')} · 本人可见</span></header>
    <section className="sbw-goal" aria-label="当前共同方向"><div><span className="sbw-eyebrow">{options.teamId ? '共同方向' : '先把想法留在这里'}</span><p>{context?.direction?.goal || (options.teamId ? '团队还没有确认共同方向，可以先讨论一个小目标。' : '还没有团队也可以讨论，并使用自己的材料。')}</p>{context?.direction?.non_goals && <small>明确不做：{context.direction.non_goals}</small>}</div><button type="button" onClick={() => options.onNavigate(options.teamId ? 'direction' : 'team')}>{options.teamId ? '查看方向 ↗' : '创建或加入小队 ↗'}</button></section>
    {context?.workflow && <section className="sbw-goal" aria-label="项目当前进度"><div><span className="sbw-eyebrow">接着上次的进度</span><p>{context.workflow.next_action.title}</p><small>当前 {context.workflow.total_tasks} 项正式任务，{context.workflow.accepted_tasks} 项成果有同伴检查记录。{context.workflow.next_action.reason}</small></div><button type="button" onClick={() => options.onNavigate(({ overview: 'tasks', plugin: 'tools' } as Record<string, string>)[context.workflow!.next_action.page] || context.workflow!.next_action.page)}>继续当前下一步 ↗</button></section>}
    {options.teamId && <section className="sbw-notice" aria-label="个人与团队空间说明"><p>这里是当前团队范围中的本人讨论。个人空间的材料与讨论仍保留，共享前只有你可见。{Boolean(context?.personal_session_count) && `你在个人空间有 ${context!.personal_session_count} 段讨论。`}</p><div className="sbw-actions"><button type="button" onClick={() => options.onNavigate('work', { teamId: null })}>继续我的个人讨论 ↗</button><button type="button" onClick={() => options.onNavigate('materials', { teamId: null })}>选择个人材料带入团队 ↗</button></div></section>}
    {error && <div className="sbw-error" role="alert">{error}<button type="button" onClick={() => void refresh()}>重新读取</button></div>}
    <div className="sbw-sessionBar"><label>本人会话<select aria-label="本人会话历史" value={selected || ''} onChange={e => selectSession(e.target.value)} disabled={!sessions.length || creating}><option value="" disabled>{loading ? '正在读取…' : '还没有会话'}</option>{sessions.map(s => <option key={s.id} value={s.id}>{s.title} · {dateText(s.updated_at)}</option>)}</select></label><button type="button" onClick={() => void createSession()} disabled={loading || creating || !context}>{creating ? '正在创建…' : '＋ 新会话'}</button><button className="sbw-textButton" type="button" onClick={() => options.onNavigate('tasks')}>任务与统筹 ↗</button></div>
    {selected && !renaming && <button type="button" className="sbw-textButton" onClick={() => { setTitle(sessions.find(s => s.id === selected)?.title || ''); setRenaming(true); }}>重命名当前会话</button>}
    {renaming && <form className="sbw-notice" onSubmit={e => { e.preventDefault(); void rename(); }}><label>会话名称<input value={title} maxLength={120} onChange={e => setTitle(e.target.value)} disabled={savingTitle} autoFocus /></label><div className="sbw-actions"><button disabled={savingTitle || !title.trim()}>保存名称</button><button type="button" disabled={savingTitle} onClick={() => setRenaming(false)}>取消</button></div></form>}
    {loading ? <p className="sbw-empty" role="status">正在读取本人的会话与可用材料…</p> : selected && context ? <ConversationPanel key={selected} sessionId={selected} scope={scope} context={context} api={api} options={options} onSessionChange={updateSession} /> : <div className="sbw-empty"><h2>{options.teamId ? '本团队范围还没有本人讨论' : '给想法一个开始'}</h2><p>新建会话后，可以理资料、想方向，或排下一步。</p><button className="sbw-primary" type="button" disabled={creating || !context} onClick={() => void createSession()}>开始一段讨论</button></div>}
  </section>;
}
