// Copyright (c) 2026 2292576833. AI workbench contribution; joint project ownership: COPYRIGHT.md.
import { useEffect, useRef, useState } from 'react';
import type { CompanionAction, CompanionConversation, CompanionProps, CompanionSend, CompanionTurn } from './types';
import './companion.css';

const permitted = new Set<CompanionAction['kind']>(['open_course_hall', 'open_hackathon_hall', 'open_portfolio', 'open_competition_team']);
const contextKey = (p: CompanionProps) => JSON.stringify([p.context.domain, p.context.resource_id || '', p.context.learner_id || '']);
const requestId = () => 'sb_' + crypto.randomUUID();
const modeLabel = { static: '本地指引 · 不是实时AI回复', mock: '模拟回应 · 未调用真实模型', live: '已授权AI回应 · 按实际回执显示' };
const activeStatus = (turn: CompanionTurn) => ['pending', 'running', 'unknown'].includes(turn.status);
function knownRejection(error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  return typeof status === 'number' && status >= 400 && status < 500;
}
function Turn({ turn, onAction }: { turn: CompanionTurn; onAction: CompanionProps['onAction'] }) {
  return <li className="sb-companion-turn">
    <div className="sb-companion-user"><strong>你</strong><p>{turn.question}</p></div>
    <div className="sb-companion-reply"><strong>松伴</strong><p>{turn.visibility === 'restricted' ? '授权已经变化，这条回复暂不可读取。' : turn.status === 'unknown' ? '这次回应的结果还没有确认。先核对原记录，不会自动重新发送。' : turn.status === 'pending' ? '提问已记下，正在等待松伴回应。' : turn.status === 'running' ? '松伴正在回应，请稍等；不会重复发送。' : turn.status === 'failed' ? '这次没有得到可用回应。你的输入保留着，请先核对当前记录。' : turn.text}</p>
      <small>{modeLabel[turn.mode]}</small>
      {turn.actual_model && <small> · 实际模型：{turn.actual_model}</small>}
      {turn.sources.length > 0 && <details><summary>看看提示来自哪里</summary><ul>{turn.sources.map(s => <li key={s.source_domain + ':' + s.source_id}>{s.source_domain} · {s.source_id} · 版本 {s.source_version}</li>)}</ul></details>}
      {turn.status === 'succeeded' && turn.actions.filter(a => permitted.has(a.kind)).map(a => <button type="button" key={a.kind + ':' + a.resource_id} onClick={() => { void onAction(a); }}>{a.label}</button>)}
    </div>
  </li>;
}

/** One mounted instance across both shells; identityKey changes remount it.
 * Context switches retain local drafts only inside that authenticated identity. */
export function Companion(props: CompanionProps) {
  return <CompanionState key={props.identityKey} {...props} />;
}

function CompanionState(props: CompanionProps) {
  const [expanded, setExpanded] = useState(props.presentation === 'embedded');
  const [view, setView] = useState<CompanionConversation | null>(null);
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState<'static' | 'mock' | 'live'>('static');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<CompanionSend | null>(null);
  const drafts = useRef(new Map<string, string>());
  const requests = useRef(new Map<string, CompanionSend>());
  const opens = useRef(new Map<string, string>());
  const generation = useRef(0);
  const key = contextKey(props);
  const active = useRef(true);
  useEffect(() => () => { active.current = false; ++generation.current; drafts.current.clear(); requests.current.clear(); opens.current.clear(); }, []);
  useEffect(() => { props.onDirty?.(props.context.domain !== 'learning' && !props.disabled && (!!question.trim() || !!pending)); }, [props.onDirty, props.context.domain, props.disabled, question, pending]);
  useEffect(() => () => { props.onDirty?.(false); }, [props.onDirty]);

  function adopt(next: CompanionConversation, currentKey: string) {
    setView(next);
    let unresolved = requests.current.get(currentKey);
    const last = next.messages.at(-1);
    if (!unresolved && last && activeStatus(last)) {
      unresolved = { request_id: last.request_id, expected_revision: last.parent_revision - 1, question: last.question, mode: last.mode };
      requests.current.set(currentKey, unresolved); drafts.current.set(currentKey, last.question);
      setQuestion(last.question);
    }
    if (unresolved) {
      const found = next.messages.find(t => t.request_id === unresolved.request_id);
      if (found?.status === 'succeeded') {
        requests.current.delete(currentKey); drafts.current.delete(currentKey);
        setPending(null); setQuestion('');
        setNotice('已读到原来的回应，没有重复发送。');
      } else if (found?.status === 'failed') {
        requests.current.delete(currentKey); setPending(null);
        setNotice('原请求已经结束，没有可用回应。输入已保留，可以核对后选择本地提示。');
      } else {
        setPending(unresolved);
        setNotice(found?.status === 'pending' || found?.status === 'running' ? '正在等原来的回应，不会重新发送。' : found ? '原回应仍待核对，不会自动重新发送。' : '还没读到原回应，不能确定没有收到。请保留输入，稍后核对。');
      }
    }
    if (next.adapter) props.onLearningAdapter?.(next.adapter);
  }

  useEffect(() => {
    active.current = true;
    const captured = ++generation.current;
    setView(null); setMode('static'); setNotice(''); setBusy(false);
    setQuestion(drafts.current.get(key) || ''); setPending(requests.current.get(key) || null);
    if (props.disabled) return;
    if (props.context.domain === 'learning') {
      if (props.context.resource_id) props.onLearningAdapter?.({ kind: 'learning_run', run_id: props.context.resource_id });
      return;
    }
    if (!opens.current.has(key)) opens.current.set(key, requestId());
    setBusy(true);
    void props.transport.open({ request_id: opens.current.get(key)!, context: props.context }).then(next => {
      if (active.current && captured === generation.current) adopt(next, key);
    }).catch(() => {
      if (active.current && captured === generation.current) setNotice('暂时读不到当前身份的松伴记录。请重新读取；未发送的话保留在当前页面。');
    }).finally(() => { if (active.current && captured === generation.current) setBusy(false); });
    return () => { ++generation.current; };
  }, [props.identityKey, key, props.transport, props.disabled]);

  // Poll a known queued/running message only. At most 20 reads per attachment;
  // unknown/failed/identity changes stop polling. No POST is issued by this loop.
  const waiting = view?.messages.find(t => t.request_id === pending?.request_id);
  useEffect(() => {
    if (!view || !waiting || !['pending', 'running'].includes(waiting.status)) return;
    let cancelled = false, attempts = 0;
    const captured = generation.current;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const turn = await props.transport.readMessage(view!.id, waiting!.id);
        if (cancelled || !active.current || captured !== generation.current) return;
        setView(v => v && { ...v, revision: turn.parent_revision, messages: v.messages.map(t => t.id === turn.id ? turn : t) });
        if (turn.status === 'succeeded') {
          requests.current.delete(key); drafts.current.delete(key); setPending(null); setQuestion(''); setNotice('松伴的回应已读到。');
        } else if (turn.status === 'failed') {
          requests.current.delete(key); setPending(null); setNotice('这次没有得到可用回应。输入已保留，请核对后再决定。');
        } else if (turn.status === 'unknown') setNotice('这次结果还未确认，请核对原回应，不会自动重发。');
        else if (++attempts < 20) timer = setTimeout(poll, 1500);
        else setNotice('仍在等原回应。可以稍后点击核对，不会重新发送。');
      } catch { if (!cancelled && captured === generation.current) setNotice('暂时读不到原回应，请稍后手动核对。没有重新发送。'); }
    }
    timer = setTimeout(poll, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [waiting?.id, waiting?.status, props.transport, key]);

  async function readOriginal() {
    const captured = generation.current;
    setBusy(true);
    try {
      const next = view ? await props.transport.read(view.id) : await props.transport.open({ request_id: opens.current.get(key) || requestId(), context: props.context });
      if (active.current && captured === generation.current) { setNotice(''); adopt(next, key); }
    } catch { if (active.current && captured === generation.current) setNotice('仍未读到结果。输入已保留，没有重新发送。'); }
    finally { if (active.current && captured === generation.current) setBusy(false); }
  }
  async function send() {
    if (!view || busy || pending || !question.trim()) return;
    const captured = generation.current;
    const body: CompanionSend = { request_id: requestId(), expected_revision: view.revision, question: question.trim(), mode };
    requests.current.set(key, body); setPending(body); setBusy(true); setNotice('');
    try {
      const turn = await props.transport.send(view.id, body);
      if (!active.current || captured !== generation.current) return;
      setView(v => v && { ...v, revision: turn.parent_revision, messages: [...v.messages.filter(t => t.id !== turn.id), turn] });
      if (turn.status === 'succeeded') {
        requests.current.delete(key); drafts.current.delete(key); setPending(null); setQuestion('');
      } else if (turn.status === 'failed') {
        requests.current.delete(key); setPending(null); setNotice('这次没有得到可用回应，输入已保留。');
      } else setNotice(turn.status === 'unknown' ? '这次结果还未确认，输入已保留。请核对原回应，不要重新发送。' : '提问已保存，正在等原来的回应。');
    } catch (error) {
      if (!active.current || captured !== generation.current) return;
      if (knownRejection(error)) {
        requests.current.delete(key); setPending(null);
        setNotice('这次提问没有被接受，请先重新读取当前身份与记录。你的输入还在。');
      } else setNotice('未确认服务器是否收到，输入已保留。请核对原回应，不会自动重发。');
    } finally { if (active.current && captured === generation.current) setBusy(false); }
  }

  // The host's original learning CompanionPanel is the only course conversation.
  if (props.context.domain === 'learning' || props.disabled) return null;
  const floating = props.presentation !== 'embedded';
  return <aside className={'sb-companion ' + (floating ? 'sb-companion-floating' : 'sb-companion-embedded')} aria-label="松伴陪你做">
    {floating && <button className="sb-companion-toggle" type="button" aria-expanded={expanded} aria-controls="sb-platform-companion" onClick={() => setExpanded(v => !v)}>松伴 · {expanded ? '收起' : '陪我走一步'}</button>}
    <section id="sb-platform-companion" className="sb-companion-panel" hidden={floating && !expanded} aria-label="和松伴聊">
      <header><img src="/static/design/pine-mascot.png" alt="" width="38" height="38" /><div><h2>松伴在这里</h2><p>你来做决定，我陪你试一小步。</p></div></header>
      <p className="sb-companion-mode">{view?.capabilities.notice || '准备好的本地指引，不是实时AI回复。'}</p>
      <div role="log" aria-live="polite" aria-relevant="additions text"><ol>{view?.messages.map(t => <Turn key={t.id} turn={t} onAction={props.onAction} />)}</ol></div>
      {view && !view.messages.length && <p>可以问“我从哪开始？”或“下一步要做什么？”。你的作品与选择由你自己完成。</p>}
      {view?.has_earlier && <p>这里只显示最近100次提问，较早记录仍保存在原会话。</p>}
      <form onSubmit={e => { e.preventDefault(); void send(); }}>
        <label>想问松伴什么<textarea aria-label="想问松伴什么" rows={3} maxLength={1500} value={question} disabled={busy || !!pending} onChange={e => { setQuestion(e.target.value); drafts.current.set(key, e.target.value); }} placeholder="例如：我想做一个小作品，从哪开始？" /></label>
        {(view?.capabilities.mock_available || view?.capabilities.live_available) && <label>这次怎样提示<select aria-label="这次怎样提示" value={mode} disabled={busy || !!pending} onChange={e => setMode(e.target.value as 'static' | 'mock' | 'live')}><option value="static">本地指引</option>{view.capabilities.mock_available && <option value="mock">本地模拟回应</option>}{view.capabilities.live_available && <option value="live">请AI回应这个问题</option>}</select></label>}
        <button className="sb-companion-send" type="submit" disabled={!view || busy || !!pending || !question.trim()}>{busy ? '正在核对…' : '发送，看看提示'}</button>
      </form>
      {notice && <p role="status">{notice}</p>}
      {(pending || notice) && <button type="button" disabled={busy} onClick={() => { void readOriginal(); }}>{pending ? '核对原回应' : '重新读取当前会话'}</button>}
      <small>不会替你投票、过关、发布或生成图片。</small>
    </section>
  </aside>;
}
