/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md. */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, errorText, requestId, type LearningApi } from '../api';
import type { Config, CourseId, Route, Session } from '../types';
import { Notice, useGuard, type SetGuard } from '../ui';
import { workbenchChanged, workbenchPath, type SessionSummary, type SessionView, type Teacher } from './types';
import './workbench.css';

type ArtifactEdit = { title: string; content: string; source_message_id: string | null };
type RecordEdit = { title: string; summary: string; next_step: string };
type Job = { path: string; body: Record<string, unknown>; action: string };
const emptyArtifact = (): ArtifactEdit => ({ title: '', content: '', source_message_id: null });
const emptyRecord = (): RecordEdit => ({ title: '', summary: '', next_step: '' });
const statuses = { pending: '老师正在准备回应…', running: '老师正在回应…', succeeded: '已回应', failed: '这次回应没有完成', unknown: '结果尚未确认，请先核对，暂不重新发送' };

export function CourseWorkbench({ api, id, session, config, setGuard, navigate, entry, tools, creativeEnabled = false }: {
  api: LearningApi; id: CourseId; session: Session | null; config: Config | null; setGuard: SetGuard;
  navigate: (r: Route) => Promise<boolean>; entry?: ReactNode; tools: ReactNode; creativeEnabled?: boolean;
}) {
  const [view, setView] = useState<SessionView | null>(null), [teacher, setTeacher] = useState<Teacher | null>(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [retry, setRetry] = useState(0);
  const [input, setInput] = useState(''), [mode, setMode] = useState<'mock' | 'live'>('mock');
  const [artifact, setArtifact] = useState<ArtifactEdit>(emptyArtifact), [artifactBase, setArtifactBase] = useState<ArtifactEdit>(emptyArtifact);
  const [record, setRecord] = useState<RecordEdit>(emptyRecord), [recordBase, setRecordBase] = useState<RecordEdit>(emptyRecord);
  const [pending, setPending] = useState<Job | null>(null), [checked, setChecked] = useState(false), [conflict, setConflict] = useState(false);
  const [panel, setPanel] = useState<'chat' | 'result'>('chat'), [collapsed, setCollapsed] = useState(false);
  const [toolsOpened, setToolsOpened] = useState(false);
  const alive = useRef(true), lock = useRef(false), creation = useRef(requestId()), tail = useRef<HTMLDivElement>(null);
  const layout = useRef<HTMLDivElement>(null);
  const learner = session?.mode === 'learner' ? session.learner_id : null;
  const artifactDirty = JSON.stringify(artifact) !== JSON.stringify(artifactBase), recordDirty = JSON.stringify(record) !== JSON.stringify(recordBase);
  const processing = !!view?.messages.some(m => m.status === 'pending' || m.status === 'running');
  const uncertain = !!view?.messages.some(m => m.status === 'unknown');
  const locked = busy || !!pending || conflict || !config?.learning_enabled || !view;
  useGuard(setGuard, !!input.trim() || artifactDirty || recordDirty || busy || !!pending || conflict);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useLayoutEffect(() => {
    const element = layout.current;
    if (!element) return;
    const resize = () => {
      const available = (window.visualViewport?.height || window.innerHeight) - element.getBoundingClientRect().top - (window.innerWidth <= 600 ? 84 : 16);
      element.style.setProperty('--wb-height', `${Math.max(320, available)}px`);
    };
    resize(); window.addEventListener('resize', resize); window.visualViewport?.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); window.visualViewport?.removeEventListener('resize', resize); };
  }, [view?.id, error, pending, conflict, panel]);
  function validate(next: SessionView) {
    if (next.course_id !== id || !next.id || next.teacher.course_id !== id) throw new Error('课程会话不匹配');
    return next;
  }
  function adopt(next: SessionView) {
    validate(next);
    setView(old => !old || old.id !== next.id || next.revision >= old.revision ? next : old);
    setTeacher(next.teacher);
  }
  function fillArtifact(next: SessionView) {
    const selected = next.artifact_versions.find(v => v.id === next.selected_artifact_id);
    const value = selected ? { title: selected.title, content: selected.content, source_message_id: selected.source_message_id } : emptyArtifact();
    setArtifact(value); setArtifactBase(value);
  }
  function fillRecord(next: SessionView) {
    const value = next.record ? { title: next.record.title, summary: next.record.summary, next_step: next.record.next_step } : emptyRecord();
    setRecord(value); setRecordBase(value);
  }
  useEffect(() => {
    let active = true; setError('');
    if (!learner) {
      void api.publicTeachers().then(data => { if (active) setTeacher(data.teachers.find(t => t.course_id === id) || null); }).catch(e => { if (active) setError(errorText(e)); });
      return () => { active = false; };
    }
    setBusy(true);
    // Read existing work even when learning writes are paused. Creating a session never calls a model.
    void api.platform<{ items: SessionSummary[] }>(`${workbenchPath}/sessions`).then(async data => {
      if (!active) throw new Error('页面已离开');
      const existing = data.items.find(item => item.course_id === id);
      return existing ? api.platform<SessionView>(`${workbenchPath}/sessions/${encodeURIComponent(existing.id)}`)
        : api.platform<SessionView>(`${workbenchPath}/sessions`, 'POST', { request_id: creation.current, course_id: id });
    }).then(validate).then(next => {
      if (!active) return; adopt(next); fillArtifact(next); fillRecord(next);
      setMode(next.capabilities.mock ? 'mock' : 'live'); workbenchChanged();
    }).catch(e => { if (active) setError(errorText(e)); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [api, id, learner, retry]);
  const sessionPath = view ? `${workbenchPath}/sessions/${encodeURIComponent(view.id)}` : '';
  useEffect(() => {
    if (!view || !processing || busy || pending || conflict) return;
    let active = true, timer: number;
    const poll = async () => {
      try {
        const next = validate(await api.platform<SessionView>(sessionPath));
        if (!active) return;
        adopt(next);
        if (next.messages.some(m => m.status === 'pending' || m.status === 'running')) timer = window.setTimeout(poll, 1800);
      } catch (e) { if (active) setError(errorText(e)); }
    };
    timer = window.setTimeout(poll, 1800);
    return () => { active = false; window.clearTimeout(timer); };
  }, [api, sessionPath, view?.revision, processing, busy, pending, conflict]);
  useEffect(() => { if (view?.messages.length) tail.current?.scrollIntoView({ block: 'nearest' }); }, [view?.messages.length, view?.messages.at(-1)?.status]);
  async function perform(job: Job) {
    if (lock.current) return; lock.current = true; setBusy(true); setError('');
    try {
      const next = validate(await api.platform<SessionView>(job.path, 'POST', job.body));
      if (!alive.current) return;
      adopt(next); setPending(null); setChecked(false); setConflict(false);
      if (job.action === 'messages') setInput('');
      if (job.action === 'artifacts' || job.action === 'select-artifact') fillArtifact(next);
      if (job.action === 'record-draft' || job.action === 'record-confirm') fillRecord(next);
      workbenchChanged();
    } catch (e) {
      if (!alive.current) return; setError(errorText(e));
      if (e instanceof ApiError && e.unknown) { setPending(job); setChecked(false); }
      else if (e instanceof ApiError && e.status === 409) { setConflict(true); setChecked(false); setPending(null); }
    } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  function write(action: string, body: Record<string, unknown> = {}) {
    if (locked || !view) return;
    void perform({ path: `${sessionPath}/${action}`, action, body: { ...body, request_id: requestId(), expected_revision: view.revision } });
  }
  async function reconcile() {
    if (!view || lock.current) return; lock.current = true; setBusy(true); setError('');
    try {
      const next = validate(await api.platform<SessionView>(sessionPath));
      if (!alive.current) return; adopt(next); setChecked(true);
    } catch (e) { if (alive.current) setError(errorText(e)); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  const canSend = !locked && !processing && !uncertain && !!input.trim() && !!view?.capabilities[mode];
  return <section className="wb-page" aria-label="课程老师工作台" aria-busy={busy}>
    <header className="wb-heading"><div><p className="lp-eyebrow">和老师一起试一试</p><h1>{teacher?.name || '课程老师'}</h1>{teacher && <details className="wb-goal"><summary>本课目标</summary><p>{teacher.goal}</p></details>}</div><button aria-label="返回 AI 教学大厅" onClick={() => void navigate('#/learn/courses')}>课程大厅</button></header>
    {!learner && <><p className="wb-opening">{teacher?.opening}</p>{session?.mode === 'staff' ? <Notice>当前为工作人员身份，可以阅读课程介绍。</Notice> : entry}</>}
    {error && <Notice error>{error}</Notice>}
    {learner && !view && <><Notice>{busy ? '正在恢复和老师的对话…' : '暂时没能恢复对话。以前保存的内容仍会保留。'}</Notice>{!busy && <button onClick={() => setRetry(n => n + 1)}>重新读取老师会话</button>}</>}
    {(pending || conflict) && <section className="wb-recovery" aria-label="核对保存结果"><p>{pending ? '这次结果尚未确认。先读回服务器记录，再用相同操作编号核对，避免重复发送。' : '另一处更新了这次会话。先读取最新内容，你的输入仍会保留。'}</p><button disabled={busy} onClick={() => void reconcile()}>核对服务器结果</button>{checked && pending && <button disabled={busy} onClick={() => void perform(pending)}>使用原请求编号核对操作</button>}{checked && conflict && <><p>已读取最新会话版本 {view?.revision}。检查下方对话和已保存版本后再继续。</p><button disabled={busy} onClick={() => { setConflict(false); setChecked(false); }}>已核对，继续编辑</button></>}</section>}
    {view && <>
      <div className="wb-view-switch" aria-label="工作区切换"><button aria-pressed={panel === 'chat'} onClick={() => setPanel('chat')}>对话</button><button aria-pressed={panel === 'result'} onClick={() => { setPanel('result'); setCollapsed(false); }}>成果与记录</button><button className="wb-collapse" onClick={() => setCollapsed(v => !v)}>{collapsed ? '展开成果' : '收起成果'}</button></div>
      <div ref={layout} className={`wb-layout${collapsed ? ' wb-result-collapsed' : ''}`} data-panel={panel}>
        <section className="wb-chat" aria-label="与课程老师对话">
          <div className="wb-messages" tabIndex={0} role="log" aria-live="polite" aria-relevant="additions text" aria-label="对话内容"><article className="wb-bubble wb-teacher"><strong>{view.teacher.name}</strong><p className="wb-text">{view.teacher.opening}</p></article>
            {!view.messages.length && <div className="wb-suggestions" aria-label="试试这样开始">{view.teacher.suggestions.map(text => <button type="button" key={text} disabled={locked || !!input} onClick={() => setInput(text)}>{text}</button>)}</div>}
            {view.messages.map(message => <div className="wb-turn" key={message.id}><article className="wb-bubble wb-user"><strong>我</strong><p className="wb-text">{message.user_text}</p></article><article className="wb-bubble wb-teacher"><strong>{view.teacher.name}</strong><span className="wb-model">{message.mode === 'mock' ? '模拟示范 · 非实时模型' : `在线模型${message.actual_model ? ` · ${message.actual_model}` : ' · 等待结果'}`}</span>{message.assistant_text && <p className="wb-text">{message.assistant_text}</p>}<p role="status">{statuses[message.status]}</p>
              {message.artifact && <div className="wb-candidate"><h3>成果候选：{message.artifact.title}</h3><pre className="wb-text">{message.artifact.content}</pre><button disabled={locked || artifactDirty} onClick={() => { setArtifact({ ...message.artifact!, source_message_id: message.id }); setPanel('result'); setCollapsed(false); }}>编辑这份成果</button>{artifactDirty && <p>先保存或放弃编辑区的修改，再选择另一份候选。</p>}</div>}
              {message.status === 'failed' && <button disabled={locked || !!input} onClick={() => setInput(message.user_text)}>取回这次输入</button>}
              {message.status === 'unknown' && <button disabled={busy} onClick={() => void reconcile()}>核对老师回应</button>}
            </article></div>)}<div ref={tail}/>
          </div>
          <form className="wb-composer" onSubmit={event => { event.preventDefault(); if (canSend) write('messages', { content: input.trim(), mode }); }}>
            <label htmlFor="wb-message">告诉老师你想试什么</label><textarea id="wb-message" aria-label="告诉老师你想试什么，也可以随时改主意" rows={2} maxLength={4000} value={input} disabled={busy || !!pending} onChange={e => setInput(e.target.value)} placeholder="可以提要求、追问，也可以随时改主意。"/>
            <div className="wb-send-row"><label><span className="lp-sr">回应方式</span><select aria-label="回应方式" value={mode} disabled={locked} onChange={e => setMode(e.target.value as 'mock' | 'live')}><option value="mock" disabled={!view.capabilities.mock}>模拟示范</option><option value="live" disabled={!view.capabilities.live}>在线老师</option></select></label><details className="wb-mode-info"><summary aria-label="查看回应方式说明">说明</summary><p>{mode === 'mock' ? '模拟示范不会调用真实模型。' : '发送后由已配置的在线模型回应。'}{!view.capabilities.live && (view.capabilities.reason || '在线老师暂未配置。')}</p></details><button className="lp-primary" type="submit" disabled={!canSend}>{processing ? '等待老师回应…' : '发送给老师'}</button></div>
            {processing && error && <button type="button" disabled={busy} onClick={() => void reconcile()}>重新读取回应</button>}
          </form>
        </section>
        <aside className="wb-results" aria-label="成果与探索记录"><h2>我的成果</h2><p>先试着修改，满意后保存一个版本。这里只预览文字。</p>
          <fieldset disabled={locked}><label>成果标题<input aria-label="成果标题" value={artifact.title} maxLength={160} onChange={e => setArtifact(a => ({ ...a, title: e.target.value }))}/></label><label>成果内容<textarea aria-label="成果内容" rows={8} value={artifact.content} maxLength={16000} onChange={e => setArtifact(a => ({ ...a, content: e.target.value }))}/></label><div className="lp-actions"><button className="lp-primary" disabled={!artifactDirty || !artifact.title.trim() || !artifact.content.trim()} onClick={() => write('artifacts', artifact)}>保存成果版本</button>{artifactDirty && <button onClick={() => setArtifact(artifactBase)}>放弃成果修改</button>}</div></fieldset>
          <p role="status">{artifactDirty ? '成果有未保存的修改' : view.selected_artifact_id ? '当前成果版本已保存' : '还没有保存成果版本'}</p>
          <details><summary>已保存的版本（{view.artifact_versions.length}）</summary>{view.artifact_versions.map((version, index) => <article className="wb-version" key={version.id}><h3>版本 {index + 1} · {version.title}</h3><pre className="wb-text">{version.content}</pre><button disabled={locked || artifactDirty || version.id === view.selected_artifact_id} onClick={() => write('select-artifact', { version_id: version.id })}>{version.id === view.selected_artifact_id ? '正在使用这个版本' : `选回版本 ${index + 1}`}</button></article>)}</details>
          <section className="wb-record-editor"><h2>留下这次探索</h2><p>记录你试过什么、自己的想法和下一步；可以先有探索记录，再慢慢做作品。</p>
            {view.confirmed_record && view.record?.status === 'draft' && <details><summary>上次确认的记录仍保留在作品集</summary><h3>{view.confirmed_record.title}</h3><p className="wb-text">{view.confirmed_record.summary}</p><p>{view.confirmed_record.next_step}</p></details>}
            <button disabled={locked || processing || uncertain || recordDirty || (!view.messages.length && !view.artifact_versions.length)} onClick={() => write('record-draft')}>{view.record ? '根据新尝试生成记录草稿' : '生成探索记录草稿'}</button>
            {view.record && <><p>{view.record.method === 'evidence' ? '根据已有消息与成果整理，不是模型评价。' : '模型协助整理，请按自己的意思修改。'}{view.record.status === 'confirmed' ? '当前记录已经由你确认。需要修改时，先生成新的草稿，原确认版本会保留。' : '草稿尚未进入作品集。'}</p><fieldset disabled={locked || view.record.status === 'confirmed'}><label>记录标题<input aria-label="记录标题" value={record.title} maxLength={160} onChange={e => setRecord(r => ({ ...r, title: e.target.value }))}/></label><label>这次我试了什么<textarea aria-label="这次我试了什么" rows={4} value={record.summary} maxLength={6000} onChange={e => setRecord(r => ({ ...r, summary: e.target.value }))}/></label><label>下次想试<input aria-label="下次想试" value={record.next_step} maxLength={2000} onChange={e => setRecord(r => ({ ...r, next_step: e.target.value }))}/></label><button className="lp-primary" disabled={!record.title.trim() || !record.summary.trim() || (view.record.status === 'confirmed' && !recordDirty)} onClick={() => write('record-confirm', record)}>确认记录，存入作品集</button>{recordDirty && <button onClick={() => setRecord(recordBase)}>放弃记录修改</button>}</fieldset><p role="status">{recordDirty ? '记录有未确认的修改' : view.record.status === 'confirmed' ? '已确认保存，可从作品集继续这次探索。' : '请读一读，再修改或确认。'}</p></>}
            <button onClick={() => void navigate('#/portfolio')}>打开作品集</button>
          </section>
        </aside>
      </div>
    </>}
    <details className="wb-tools" onToggle={event => { if (event.currentTarget.open) setToolsOpened(true); }}><summary>动手试 / 参考材料（含以前的课程记录）</summary>{creativeEnabled && teacher?.tools.includes('creative-studio') && <button onClick={() => void navigate('#/learn/create')}>进入编程创作工作台</button>}{toolsOpened && tools}</details>
  </section>;
}
