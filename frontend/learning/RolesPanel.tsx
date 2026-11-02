import { useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Help, ModelRun, Run, TaskCard } from './contracts';
import type { Config } from './types';
import { Notice, useGuard, type SetGuard } from './ui';
import { encode, lessonError, TextField, type Mutation } from './workspace';

const roles = { guide: '小松 · 主向导', tool_guide: '工具向导', creation_coach: '创作教练', review_coach: '检查复盘教练' };
const modes = { static: '准备好的提示', mock: '模拟帮助', live: '真实 AI 帮助', replay: '历史帮助回放' };
export function RolesPanel({ api, run, task, helps, config, mutation: m, setGuard, sourceIds }: {
  api: LearningApi; run: Run; task: TaskCard; helps: Help[]; config: Config; mutation: Mutation; setGuard: SetGuard; sourceIds: Record<Help['role_id'], string[]>;
}) {
  const [role, setRole] = useState<Help['role_id']>('guide'), [level, setLevel] = useState(1);
  const [mode, setMode] = useState<'static' | 'live'>('static'), [question, setQuestion] = useState('');
  const [selected, setSelected] = useState<Help | null>(null), [model, setModel] = useState<ModelRun | null>(null), [error, setError] = useState('');
  const generation = useRef(0);
  const current = selected && helps.find(h => h.id === selected.id) || selected;
  useGuard(setGuard, !!question || m.busy || !!m.pending);
  useEffect(() => { setSelected(null); setModel(null); setError(''); }, [task.id]);
  useEffect(() => {
    const epoch = ++generation.current;
    let stopped = false, timer: ReturnType<typeof setTimeout> | undefined;
    const id = current?.model_run_id;
    if (!id) { setModel(null); return; }
    async function read() {
      try {
        const value = await api.request<ModelRun>(`/model-runs/${encode(id!)}`);
        if (stopped || generation.current !== epoch) return;
        setModel(value); setError('');
        if (['pending', 'running'].includes(value.status)) timer = setTimeout(() => void read(), 2500);
      } catch (e) { if (!stopped && generation.current === epoch) setError(lessonError(e)); }
    }
    setModel(null); void read();
    return () => { stopped = true; ++generation.current; clearTimeout(timer); };
  }, [api, current?.model_run_id]);
  const ask = () => m.run<Help>(`/runs/${encode(run.id)}/help`, {
    expected_revision: run.revision, role_id: role, help_level: level, mode,
    question: mode === 'static' ? '请给我这一步的提示' : question.trim(), source_ids: sourceIds[role],
    task_id: task.id, task_card_version: task.version,
  }, h => { setSelected(h); setQuestion(''); });
  return <section className="lp-card"><h2>卡住了，找个提示</h2><p>先说卡在哪里。向导给你问题和方法，决定怎么做的还是你。</p>
    <div className="lp-role-grid"><label>找谁帮忙<select aria-label="找谁帮忙" value={role} onChange={e => setRole(e.target.value as Help['role_id'])}>{Object.entries(roles).map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>
      <label>提示程度<select aria-label="提示程度" value={level} onChange={e => setLevel(Number(e.target.value))}><option value={1}>先问我一个问题</option><option value={2}>告诉我操作顺序</option><option value={3}>看看局部示例</option></select></label></div>
    {config.live_enabled && <label>这次怎样帮我<select aria-label="这次怎样帮我" value={mode} onChange={e => setMode(e.target.value as 'static' | 'live')}><option value="static">先看准备好的提示</option><option value="live">请 AI 针对我的问题提示</option></select></label>}
    {mode === 'live' && <><TextField label="我卡在哪里" value={question} change={setQuestion} multiline max={1500} /><p>会使用当前任务的资料和你填写的问题；先核对学习授权与可用额度。四个角色可以共用一个模型。</p></>}
    <button disabled={m.locked || !config.learning_enabled || !run.allowed_actions.includes('help') || (mode === 'live' && (!question.trim() || !config.live_enabled))} onClick={() => void ask()}>{mode === 'static' ? '展开这一步提示' : '请向导给我一个提示'}</button>
    {error && <Notice error>{error}</Notice>}
    {current && <div className="lp-notice" aria-live="polite"><p>{roles[current.role_id]} · {modes[current.mode]}{current.help_level === 3 ? ' · 局部示例' : ''}</p>
      {current.text ? <p className="lp-pre">{current.text}</p> : model?.visibility === 'normal' && model.status === 'succeeded' ? <p className="lp-pre">{helpText(model.output_text)}</p> : <p>{model?.status === 'unknown' ? '结果仍在核对，已经通知负责人员。不会自动再问一次。' : model?.status === 'failed' ? '这次没有取得可用提示。你的任务和作品还在。' : '正在读取这次帮助，请稍候。'}</p>}
      {model?.actual_model && <p className="lp-caption">响应模型：{model.actual_model}</p>}
      {current.sources.length > 0 && <details><summary>这次提示参考了什么</summary>{current.sources.map((s, i) => <p key={i}>{s.source_id} · {s.source_version}</p>)}</details>}
    </div>}
    <details><summary>已记录的帮助（{helps.length} 条）</summary>{helps.map(h => <div key={h.id} className="lp-record"><p>{roles[h.role_id]} · {modes[h.mode]} · 提示 {h.help_level}：{h.text || '读取运行记录查看结果'}</p><button disabled={m.busy} onClick={() => setSelected(h)}>查看这次帮助</button></div>)}</details>
  </section>;
}

function helpText(output: string | null) {
  try { const value = JSON.parse(output || ''); return typeof value.text === 'string' ? value.text : '提示内容未读完整，请重新读取当前任务。'; }
  catch { return '提示内容未读完整，请重新读取当前任务。'; }
}
