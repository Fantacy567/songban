/*!
 * AI 工作台 — Copyright © 2026 2292576833.
 * AI 工作台负责人：https://github.com/2292576833
 * 松伴项目由 2292576833、Fantacy567、andorwu5-dev 共同拥有，详见 COPYRIGHT.md。
 * 第三方代码及素材保留其原有版权和许可。
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { MessageCard } from './MessageCard';
import { ShareTurnPreview } from './ShareTurnPreview';
import { SpecialistAvatar } from './SpecialistAvatar';
import { ApiError, WorkbenchApi, errorText, operationKey, save, saved, uncertain } from './songban-adapter';
import { allowedPages, roles, sourceNature, type Action, type Context, type Conversation, type Message, type MountOptions, type RoleId, type TurnResult, type Session } from './types';

type Pending = { request_id: string; text: string; role_id: RoleId; source_ids: string[] };
const fields = new Set(['goal', 'rules', 'rubric', 'non_goals', 'deadline']);

// Retained from TeamAssistantPanel: mounted/read/write guards, input preservation and GET recovery.
export function ConversationPanel({ sessionId, scope, context, api, options, onSessionChange }: {
  sessionId: string; scope: string; context: Context; api: WorkbenchApi; options: MountOptions; onSessionChange(session: Session): void;
}) {
  const key = `${scope}:session:${sessionId}`;
  const initialDraft = useRef(saved<{ text: string; role: RoleId; sources: string[] }>(`${key}:draft`, { text: '', role: 'direction', sources: [] })).current;
  const [draft, setDraft] = useState(initialDraft.text);
  const [role, setRole] = useState<RoleId>(initialDraft.role);
  const [selectedSources, setSelectedSources] = useState<string[]>(initialDraft.sources);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [pending, setPending] = useState<Pending | null>(() => saved(`${key}:pending`, null));
  const [loading, setLoading] = useState(true), [refreshing, setRefreshing] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [checked, setChecked] = useState('');
  const [confirmNew, setConfirmNew] = useState(false), [share, setShare] = useState<Message | null>(null);
  const [reviewPrompt, setReviewPrompt] = useState(false);
  const [materialsOpen, setMaterialsOpen] = useState(() => window.matchMedia('(min-width: 901px)').matches);
  const [tasksOpen, setTasksOpen] = useState(false);
  const mounted = useRef(true), activeRead = useRef(false), activeWrite = useRef(false);
  const controller = useRef(new AbortController());
  const thread = useRef<HTMLDivElement>(null), followLatest = useRef(true);
  const inputId = useId(), helpId = useId();
  const draftRef = useRef(draft); draftRef.current = draft;
  const pendingRef = useRef(pending); pendingRef.current = pending;
  const base = `/api/workbench/sessions/${encodeURIComponent(sessionId)}`;
  useEffect(() => {
    const media = window.matchMedia('(min-width: 901px)');
    const resize = () => { setMaterialsOpen(media.matches); setTasksOpen(false); };
    media.addEventListener('change', resize);
    return () => media.removeEventListener('change', resize);
  }, []);

  const refresh = useCallback(async (explicit = false) => {
    if (activeRead.current || !api.active) return;
    activeRead.current = true; if (mounted.current) setRefreshing(true);
    try {
      const data = await api.request<Conversation>(base, { signal: controller.current.signal });
      if (!mounted.current || !api.active) return;
      if (data.session.id !== sessionId) throw new Error('会话信息已变化，请重新读取。');
      setConversation(data); setError('');
      onSessionChange(data.session);
      if (explicit) {
        const latest = data.requests.at(-1);
        const answer = latest && data.messages.some(m => m.role === 'assistant' && m.request_id === latest.request_id);
        const question = latest && data.messages.some(m => m.role === 'user' && m.request_id === latest.request_id);
        const result = !latest ? '还没有发送提问，输入仍为草稿。' : answer ? '本轮提问与回答均已保存。' : `${question ? '本轮提问已保存' : '尚未找到本轮提问'}，${latest.status === 'running' || latest.status === 'pending' ? '回答仍在处理中，请稍后再核对。' : latest.status === 'failed' ? '本次生成未成功，输入已保留。' : '尚未找到回答；结果仍未知，不会自动重发。'}`;
        setChecked(`刚刚核对（${new Date().toLocaleTimeString('zh-CN')}）：${result}`);
      }
      const local = pendingRef.current;
      const record = local && data.requests.find(item => item.request_id === local.request_id);
      if (record && ['succeeded', 'failed', 'unknown'].includes(record.status)) {
        if (record.status === 'succeeded' && draftRef.current.trim() === local.text) {
          setDraft(''); save(`${key}:draft`, { text: '', role: local.role_id, sources: local.source_ids });
        }
        setPending(null); pendingRef.current = null; save(`${key}:pending`, null);
      }
    } catch (cause) {
      if (mounted.current && api.active) {
        if (cause instanceof ApiError && cause.status === 404) { setConversation(null); setShare(null); }
        setError(`${errorText(cause)} 输入已保留。`);
      }
    } finally {
      activeRead.current = false;
      if (mounted.current && api.active) { setLoading(false); setRefreshing(false); }
    }
  }, [api, base, key, sessionId, onSessionChange]);
  useEffect(() => {
    void refresh();
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', visible);
    return () => { mounted.current = false; controller.current.abort(); document.removeEventListener('visibilitychange', visible); };
  }, [refresh]);
  useEffect(() => { save(`${key}:draft`, { text: draft, role, sources: selectedSources }); }, [key, draft, role, selectedSources]);
  useEffect(() => { if (thread.current && followLatest.current) thread.current.scrollTop = thread.current.scrollHeight; }, [conversation?.messages.length, busy]);
  const latest = conversation?.requests.at(-1);
  const running = conversation?.requests.some(item => ['pending', 'running'].includes(item.status)) || false;
  const unresolved = latest?.status === 'unknown' || Boolean(pending && !busy && !running);
  useEffect(() => {
    if (!running && !pending) return;
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
    return () => clearInterval(timer);
  }, [running, pending, refresh]);
  const validSources = selectedSources.filter(id => context.sources.some(source => source.id === id));
  const sourcesChanged = validSources.length !== selectedSources.length;
  const canSend = Boolean(conversation) && context.model.configured && !loading && !busy && !running && draft.trim().length > 0 && draft.trim().length <= 8000 && (!unresolved || confirmNew) && !sourcesChanged;
  async function send() {
    if (!canSend || activeWrite.current) return;
    activeWrite.current = true; setBusy(true); setError(''); setNotice(''); setChecked(''); setConfirmNew(false);
    followLatest.current = true;
    const command: Pending = { request_id: operationKey(), text: draft.trim(), role_id: role, source_ids: validSources };
    setPending(command); pendingRef.current = command; save(`${key}:pending`, command);
    try {
      const result = await api.request<TurnResult>(`${base}/turns`, { method: 'POST', body: command, signal: controller.current.signal });
      if (!mounted.current || !api.active) return;
      if (result.request.status === 'succeeded') {
        if (draftRef.current.trim() === command.text) setDraft('');
        setNotice('回答已保存到本人的会话。');
      } else if (result.request.status === 'failed') setNotice(result.request.error?.message || '本次没有生成可用回答，输入已保留。');
    } catch (cause) {
      if (!mounted.current || !api.active) return;
      if (!uncertain(cause)) { setPending(null); pendingRef.current = null; save(`${key}:pending`, null); }
      setNotice(`${errorText(cause)} 正在核对已保存状态；不会自动重发。`);
    } finally {
      activeWrite.current = false;
      if (mounted.current && api.active) { setBusy(false); await refresh(); }
    }
  }
  function act(action: Action) {
    if (action.type === 'open_page' && action.page && allowedPages.has(action.page)) options.onNavigate(action.page);
    if (action.type === 'prepare_direction' && context.team?.is_captain) {
      const safe: Record<string, string> = {};
      Object.entries(action.fields || {}).forEach(([name, value]) => {
        if (!fields.has(name) || typeof value !== 'string' || value.length > 8000) return;
        if (name === 'deadline' && (!/(Z|[+-]\d{2}:\d{2})$/.test(value) || Number.isNaN(Date.parse(value)))) return;
        safe[name] = value;
      });
      if (Object.keys(safe).length) options.onPrepareDirection(safe);
    }
    if (action.type === 'request_team_review' && context.team?.is_captain) setReviewPrompt(true);
  }
  return <div className="sbw-layout">
    <section className="sbw-main" aria-label="本人讨论">
      <header className="sbw-topbar"><span>本人讨论 <small>· 共享前只有你可见</small></span><button type="button" className="sbw-textButton" onClick={() => void refresh(true)} disabled={refreshing}>{refreshing ? '正在核对…' : '核对保存状态'}</button></header>
      <div className="sbw-thread" ref={thread} onScroll={event => { const el = event.currentTarget; followLatest.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }} aria-label="会话消息" aria-busy={loading}>
        {loading && <p className="sbw-muted" role="status">正在读取历史…</p>}
        {!loading && conversation?.messages.length === 0 && <div className="sbw-welcome"><SpecialistAvatar specialistKey={role} size={42} /><h2>先聊聊你现在的想法</h2><p>说说想解决的问题，或选几份材料一起看。建议可以慢慢改，确认后再交给团队。</p><div className="sbw-examples">{roles.map(item => <button type="button" key={item.id} onClick={() => { setRole(item.id); setDraft(item.prompt); }}>{item.name} ↗</button>)}</div></div>}
        {conversation?.messages.map(message => <div key={message.id}><MessageCard message={message} canPrepare={Boolean(context.team?.is_captain)} canReview={Boolean(context.team?.is_captain)} onAction={act} onShare={() => { setShare(message); setReviewPrompt(false); }} />{share?.id === message.id && <ShareTurnPreview key={message.id} message={message} userMessage={conversation.messages.find(item => item.request_id === message.request_id && item.role === 'user')} api={api} options={options} scope={key} team={context.team} onClose={() => setShare(null)} />}</div>)}
        {(busy || running) && <p className="sbw-notice" role="status">正在生成，本轮请求已提交。离开或刷新页面后可继续核对状态。</p>}
        {latest?.status === 'failed' && <p className="sbw-error" role="alert">本次未生成可用回答：{latest.error?.message || '生成失败'}。输入已保留，可修改后再次发送。</p>}
        {unresolved && <div className="sbw-notice"><p>上一次请求结果尚未确定。请先核对保存状态；新尝试可能重复生成。</p><label className="sbw-check"><input type="checkbox" checked={confirmNew} onChange={e => setConfirmNew(e.target.checked)} />我已核对，明确发起一次新尝试</label></div>}
        {error && <p className="sbw-error" role="alert">{error}</p>}
        {notice && <p className="sbw-notice" role="status">{notice}</p>}
        {checked && <p className="sbw-notice" role="status">{checked}</p>}
        {reviewPrompt && <div className="sbw-notice"><p>先将需要采用的回答共享给团队，再到任务页点击发起统筹。统筹生成的计划仍需队长确认。</p><button type="button" onClick={() => options.onNavigate('tasks')}>已核对共享内容，进入任务与统筹</button><button type="button" className="sbw-textButton" onClick={() => setReviewPrompt(false)}>继续讨论</button></div>}
      </div>
      <form className="sbw-composerWrap" onSubmit={e => { e.preventDefault(); void send(); }}>
        <div className="sbw-rolePicker" aria-label="选择本轮职责">{roles.map(item => <button type="button" key={item.id} aria-pressed={role === item.id} title={item.description} onClick={() => setRole(item.id)}><SpecialistAvatar specialistKey={item.id} size={22} />{item.name}</button>)}</div>
        <label className="sbw-inputLabel" htmlFor={inputId}>这次想一起想清楚什么？</label><textarea id={inputId} value={draft} rows={3} maxLength={8000} onChange={e => setDraft(e.target.value)} placeholder="说说现在的想法、问题，或你卡住的地方…" aria-describedby={helpId} />
        {!context.model.configured && <p className="sbw-notice">模型尚未配置。可以查看历史、整理输入和材料，暂时无法生成新回答。</p>}
        {sourcesChanged && <p className="sbw-error">部分已选材料已不可用。<button type="button" onClick={() => setSelectedSources(validSources)}>移除失效选择</button></p>}
        <div className="sbw-composerMeta"><span id={helpId}>已选 {validSources.length}/10 份材料 · {draft.length}/8000 字</span><button className="sbw-primary" type="submit" disabled={!canSend}>{busy || running ? '正在生成…' : unresolved ? '确认新尝试' : '发送'}</button></div>
        <p className="sbw-footnote">每轮使用一种职责。建议先核对；共享、方向保存与团队统筹分别确认。</p>
      </form>
    </section>
    <aside className="sbw-support" aria-label="本次材料与任务">
      <details className="sbw-supportCard" open={materialsOpen} onToggle={e => setMaterialsOpen(e.currentTarget.open)}><summary>本轮采用的材料 <span>{validSources.length}</span></summary><p className="sbw-muted">只读取你勾选的材料，最多 10 份。</p>{context.sources.length ? <div className="sbw-sourcePicker">{context.sources.map(source => <label className="sbw-sourceOption" key={source.id}><input type="checkbox" checked={validSources.includes(source.id)} disabled={!validSources.includes(source.id) && validSources.length >= 10} onChange={e => setSelectedSources(list => e.target.checked ? [...new Set([...list, source.id])] : list.filter(id => id !== source.id))} /><span>{source.name}<small>{source.scope === 'team' ? '团队共享' : '个人材料'} · v{source.version}{source.nature ? ` · ${sourceNature(source.nature)}` : ''}</small></span></label>)}</div> : <p className="sbw-muted">还没有可选的已解析材料。</p>}<button type="button" className="sbw-textButton" onClick={() => options.onNavigate('materials')}>添加或整理材料 ↗</button></details>
      <details className="sbw-supportCard" open={tasksOpen} onToggle={e => setTasksOpen(e.currentTarget.open)}><summary>我的已确认任务 <span>{context.my_tasks.length}</span></summary>{context.my_tasks.length ? <ul className="sbw-tasks">{context.my_tasks.map((task, i) => <li key={task.task_key || task.key || i}>{task.title || task.name || task.deliverable || '查看任务详情'}</li>)}</ul> : <p className="sbw-muted">{context.team ? '暂时没有分配给你的已确认任务。' : '加入团队并确认计划后，这里会显示你的任务。'}</p>}<button type="button" className="sbw-textButton" onClick={() => options.onNavigate('tasks')}>查看任务与检查 ↗</button></details>
      <div className="sbw-privateNote"><span aria-hidden="true">◌</span><p>这里的讨论属于你。想让队友采用的内容，可以选择回合、编辑摘要后共享。</p><button type="button" className="sbw-textButton" onClick={() => options.onNavigate('library')}>查看已共享记录 ↗</button></div>
    </aside>
  </div>;
}
