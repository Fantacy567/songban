// Copyright (c) 2026 2292576833. AI workbench contribution; see COPYRIGHT.md.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Help, ModelRun, Run, TaskCard } from './contracts';
import type { Config } from './types';
import { Notice, useGuard, type SetGuard } from './ui';
import { encode, lessonError, type Mutation } from './workspace';

type ConversationHelp = Help & { question?: string | null; created_at?: string | null };
const roles = { guide: '主向导', tool_guide: '工具向导', creation_coach: '创作教练', review_coach: '检查复盘教练' };
const modes = { static: '准备好的提示', mock: '模拟帮助', live: '真实 AI 回复', replay: '历史回放' };
const shortcuts = ['给我一点提示', '带我一步步做', '看看局部例子'];
// The task workflow chooses a responsibility. A chat message never changes permissions or progress.
export function companionRole(task: Pick<TaskCard, 'id' | 'stage'>): Help['role_id'] {
  if (task.id === 'S3.2') return 'creation_coach';
  if (task.stage === 'create') return 'tool_guide';
  if (task.stage === 'review') return 'review_coach';
  return 'guide';
}
function helpText(output: string | null) {
  try { const value = JSON.parse(output || ''); return typeof value.text === 'string' && value.text.trim() ? value.text : '提示没有读完整，请重新读取这次结果。'; }
  catch { return '提示没有读完整，请重新读取这次结果。'; }
}

function ConversationTurn({ api, help, hidden, onModelState }: { api: LearningApi; help: ConversationHelp; hidden: boolean; onModelState: (id: string, state: string) => void }) {
  const [model, setModel] = useState<ModelRun | null>(null), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  useEffect(() => {
    let stopped = false, timer: ReturnType<typeof setTimeout> | undefined;
    const id = help.model_run_id;
    setModel(null); setError('');
    if (!id) return;
    async function read() {
      try {
        const value = await api.request<ModelRun>(`/model-runs/${encode(id!)}`);
        if (stopped) return;
        if (value.id !== id || value.help_event_id !== help.id) throw new Error('帮助记录不匹配');
        setModel(value); setError(''); onModelState(id!, value.status);
        if (['pending', 'running'].includes(value.status)) timer = setTimeout(() => void read(), 2500);
      } catch (e) { if (!stopped) { setError(lessonError(e)); onModelState(id!, 'unconfirmed'); } }
    }
    void read();
    return () => { stopped = true; clearTimeout(timer); };
  }, [api, help.id, help.model_run_id, onModelState, retry]);
  const response = help.model_run_id
    ? model?.visibility !== 'normal' && model ? '这次回复暂时不能展示，请联系项目支持。'
      : model?.status === 'succeeded' ? helpText(model.output_text)
      : model?.status === 'unknown' ? '这次结果还在核对，先保留你的问题。不会自动重新发送。'
      : model?.status === 'failed' ? '这次没有取得可用回复。你的任务和作品仍然保留。'
      : '正在读取这次回复…'
    : help.text || '这次提示暂时没有读完整。';
  return <li className="lp-conversation-turn" data-help-id={help.id} hidden={hidden}>
    <div className="lp-message lp-message-user"><strong>我</strong><p className="lp-pre">{help.question || '这条历史记录没有可展示的提问。'}</p></div>
    <div className="lp-message lp-message-assistant"><strong>松伴</strong><span className="lp-caption"> · {modes[help.mode]}{help.help_level === 3 ? ' · 局部示例' : ''}</span><p className="lp-pre">{response}</p>
      {error && <Notice error>{error}</Notice>}
      {(error || model?.status === 'unknown') && <button type="button" onClick={() => setRetry(v => v + 1)}>重新读取这次结果</button>}
      <details><summary>这次提示的依据</summary><p>{roles[help.role_id]} · 提示第 {help.help_level} 级 · 任务 {help.task_id}</p>
        <p>提示版本：{help.prompt_version}</p>{model?.actual_model && <p>响应模型：{model.actual_model}</p>}
        {help.sources.map((s, i) => <p key={i}>{s.source_id} · {s.source_version}</p>)}
      </details>
    </div>
  </li>;
}

export function CompanionPanel({ api, run, task, helps, config, mutation: m, setGuard, sourceIds }: {
  api: LearningApi; run: Run; task: TaskCard; helps: Help[]; config: Config; mutation: Mutation; setGuard: SetGuard; sourceIds: Record<Help['role_id'], string[]>;
}) {
  const [question, setQuestion] = useState(''), [mode, setMode] = useState<'static' | 'live'>('static'), [level, setLevel] = useState(1);
  const [receipt, setReceipt] = useState<Help | null>(null), [earlier, setEarlier] = useState(false);
  const [taskChanged, setTaskChanged] = useState(false);
  const [modelStates, setModelStates] = useState<Record<string, string>>({});
  const input = useRef<HTMLTextAreaElement>(null), alive = useRef(true), lastTask = useRef(`${task.id}@${task.version}`);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const key = `${task.id}@${task.version}`;
    if (lastTask.current !== key) { setLevel(1); setTaskChanged(true); lastTask.current = key; }
  }, [task.id, task.version]);
  useEffect(() => { setReceipt(null); setModelStates({}); setEarlier(false); setQuestion(''); setMode('static'); setTaskChanged(false); }, [run.id]);
  const onModelState = useCallback((id: string, state: string) => setModelStates(old => old[id] === state ? old : { ...old, [id]: state }), []);
  useGuard(setGuard, !!question || m.busy || !!m.pending);
  const role = companionRole(task), activeMode = config.live_enabled ? mode : 'static';
  const all = helps.filter(h => h.run_id === run.id);
  if (receipt?.run_id === run.id && !all.some(h => h.id === receipt.id)) all.push(receipt);
  all.sort((a, b) => a.parent_revision - b.parent_revision);
  // Only known terminal runs permit another live request. Reading history never spends model budget.
  const unsettled = all.some(h => h.model_run_id && !['succeeded', 'failed'].includes(modelStates[h.model_run_id] || 'unconfirmed'));
  const locked = m.locked || !config.learning_enabled || !run.allowed_actions.includes('help');
  const ask = () => {
    if (locked || (activeMode === 'live' && (unsettled || !question.trim()))) return;
    const submittedQuestion = question.trim() || shortcuts[level - 1];
    void m.run<Help>(`/runs/${encode(run.id)}/help`, {
      expected_revision: run.revision, role_id: role, help_level: level, mode: activeMode,
      question: submittedQuestion, source_ids: sourceIds[role], task_id: task.id, task_card_version: task.version,
    }, h => { if (alive.current) { setReceipt(h); setQuestion(''); setTaskChanged(false); } });
  };
  return <section className="lp-card lp-companion" aria-label="和松伴聊">
    <div className="lp-companion-heading"><img src="/static/design/pine-mascot.png" alt="" width="36" height="36" /><div><h2>和松伴聊</h2><p className="lp-caption">你来决定怎么做，我陪你试一小步。</p></div></div>
    <p className="lp-companion-goal">这一步：{task.goal}</p>
    {all.length > 8 && <button type="button" onClick={() => setEarlier(v => !v)}>{earlier ? '收起较早的对话' : `查看前面的 ${all.length - 8} 次对话`}</button>}
    <div role="log" aria-label="与松伴的对话更新" aria-live="polite" aria-relevant="additions text"><ol className="lp-conversation" aria-label="与松伴的对话">{all.map((h, i) => <ConversationTurn key={h.id} api={api} help={h} hidden={!earlier && i < all.length - 8} onModelState={onModelState} />)}</ol></div>
    {!all.length && <div className="lp-message lp-message-assistant"><strong>松伴</strong><p>先试试眼前的小任务。不会开始时，点下面的提示；想法和作品都由你来决定。</p><span className="lp-caption">课程引导语</span></div>}
    <form className="lp-composer" onSubmit={e => { e.preventDefault(); if (!locked && !(activeMode === 'live' && unsettled)) ask(); }}>
      <div className="lp-help-shortcuts" aria-label="选择提示方式">{shortcuts.map((text, i) => <button type="button" key={text} disabled={locked} aria-pressed={level === i + 1} onClick={() => { setLevel(i + 1); if (!question.trim()) setQuestion(text); input.current?.focus(); }}>{text}</button>)}</div>
      <label>想问松伴什么<textarea ref={input} aria-label="想问松伴什么" rows={3} maxLength={1500} value={question} disabled={m.busy || !!m.pending} placeholder="例如：怎样让同学一眼看懂活动在哪里？" onChange={e => setQuestion(e.target.value)} /></label>
      {taskChanged && !!question && <p className="lp-caption">步骤已经更新，你还没发送的话仍在这里。先看看当前任务，再决定怎样问。</p>}
      {config.live_enabled && <label>这次怎样帮我<select aria-label="这次怎样帮我" value={activeMode} disabled={locked} onChange={e => setMode(e.target.value as 'static' | 'live')}><option value="static">先看准备好的提示</option><option value="live">请 AI 回应我的问题</option></select></label>}
      <p className="lp-caption">{activeMode === 'static' ? '会记录你的提问并展示本步准备好的提示；这不是针对问题实时生成的 AI 回复。' : '只使用这次提问与本课获准资料。需要有效学习授权和可用额度，不会自动替你保存作品。'}</p>
      {activeMode === 'live' && unsettled && <Notice>之前的回复还在读取或核对。可以先看准备好的提示，等结果确认后再问 AI。</Notice>}
      <button className="lp-primary" type="submit" disabled={locked || (activeMode === 'live' && (unsettled || !question.trim()))}>{m.busy ? '正在记录…' : activeMode === 'static' ? '发送，看看本步提示' : '发送给松伴'}</button>
    </form>
  </section>;
}
