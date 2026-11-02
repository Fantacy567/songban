import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, errorText, requestId, type LearningApi } from './api';
import type { Answer, Choice, Config, LearnerSelf, SaveStart, Start, Topic } from './types';
import { Notice, useGuard, type SetGuard } from './ui';

export const topics: Topic[] = ['age_band', 'experience', 'interests', 'help_preference', 'mini_attempt_text', 'chosen_start'];
export const labels: Record<Topic, string> = { age_band: '年龄段', experience: '用过 AI 做什么', interests: '感兴趣的事情', help_preference: '希望怎样得到帮助', mini_attempt_text: '读一张小资料卡', chosen_start: '选择开始方式' };
export const choices: Record<Choice, string> = { guided: '带着我做', try_first: '让我先试试', challenge: '我想挑战一下' };
const states = { unanswered: '还没回答', skipped: '这题暂时跳过', answered: '已保存你的回答', accepted_default: '已采用这次建议' };
const showAnswer = (a: Answer) => a.value === null ? states[a.state] : Array.isArray(a.value) ? a.value.join('、') || '暂无兴趣选项' : choices[a.value as Choice] || ({ none: '没试过', some: '用过别人给的提示', regular: '自己改过提示和结果' }[a.value]) || a.value;
export function StartPage({ api, learnerId, config, setGuard, summary = false, edit }: { api: LearningApi; learnerId: string; config: Config; setGuard: SetGuard; summary?: boolean; edit: () => void }) {
  const [start, setStart] = useState<Start | null>(null), [topic, setTopic] = useState<Topic>('age_band');
  const [profile, setProfile] = useState<LearnerSelf | null>(null);
  const [draft, setDraft] = useState<Answer>({ state: 'unanswered', value: null });
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
  const [pending, setPending] = useState<SaveStart | null>(null), [conflict, setConflict] = useState<Start | null>(null);
  const [operationBlocked, setOperationBlocked] = useState(false);
  const alive = useRef(true), lock = useRef(false), title = useRef<HTMLHeadingElement>(null);
  const path = `/learners/${encodeURIComponent(learnerId)}/start`;
  const dirty = !!start && JSON.stringify(start.answers[topic]) !== JSON.stringify(draft);
  const load = useCallback(async () => {
    setError('');
    try {
      const [s, p] = await Promise.all([api.request<Start>(path), api.request<LearnerSelf>(`/learners/${encodeURIComponent(learnerId)}/profile`)]);
      if (!alive.current) return;
      if (s.learner_id !== learnerId || p.id !== learnerId) throw new Error('Learner mismatch');
      setProfile(p);
      const next = s.missing_fields[0] || 'chosen_start'; setStart(s); setTopic(next); setDraft(s.answers[next]);
    } catch (e) { if (alive.current) setError(errorText(e)); }
  }, [api, path, learnerId]);
  useEffect(() => { void load(); return () => { alive.current = false; }; }, [load]);
  useEffect(() => { title.current?.focus(); }, [topic]);
  async function send(body: SaveStart, advance: boolean): Promise<boolean> {
    if (lock.current) return false;
    lock.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const s = await api.request<Start>(path, 'PATCH', body);
      if (!alive.current) return false;
      setStart(s); setPending(null); setConflict(null);
      const next = advance ? topics[Math.min(topics.indexOf(topic) + 1, topics.length - 1)] : topic;
      setTopic(next); setDraft(s.answers[next]); setNotice('这题已保存。'); return true;
    } catch (e) {
      if (!alive.current) return false;
      setError(errorText(e));
      if (e instanceof ApiError && e.code === 'idempotency_conflict') {
        setOperationBlocked(true); setPending(null);
      } else if (e instanceof ApiError && e.status === 409 && e.code === 'revision_conflict') {
        setPending(null);
        try { const latest = await api.request<Start>(path); if (alive.current) setConflict(latest); }
        catch { if (alive.current) setError('暂时无法读取冲突版本，输入已保留，请再次核对最新内容。'); }
      } else if (e instanceof ApiError && e.unknown) setPending(body);
      return false;
    } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  async function save(answer = draft, advance = false): Promise<boolean> {
    if (!start || pending || conflict || operationBlocked || !config.learning_enabled) return false;
    if (answer.state === 'unanswered' || (answer.state === 'answered' && typeof answer.value === 'string' && !answer.value.trim())) {
      setError('先选一个答案，或者点“暂时跳过”。'); return false;
    }
    if (JSON.stringify(answer) === JSON.stringify(start.answers[topic])) {
      // Previously accepted recommendation carries its historical revision: do not
      // resubmit it as a fresh acceptance simply because the user revisits this page.
      if (advance) { const next = topics[Math.min(topics.indexOf(topic) + 1, topics.length - 1)]; setTopic(next); setDraft(start.answers[next]); }
      setNotice('这题已保存。'); return true;
    }
    return send({ request_id: requestId(), expected_revision: start.revision, answers: { [topic]: answer } }, advance);
  }
  useGuard(setGuard, dirty || !!pending || busy, !pending && !conflict && !busy && !operationBlocked ? () => save(draft) : undefined);
  async function retryUnknown() {
    if (!pending) return;
    try {
      // A read first; only an explicit retry sends the original id and exact body.
      await api.request<Start>(path); await send(pending, false);
    } catch (e) { setError(errorText(e)); }
  }
  if (!start) return <section className="lp-card"><h2>读取上次的选择</h2>{error ? <><Notice error>{error}</Notice><button onClick={() => void load()}>重新读取</button></> : <Notice>正在读取上次的学习起点…</Notice>}</section>;
  const recommendation = <div className="lp-notice"><strong>当前建议：{choices[start.recommendation]}</strong><p>{start.recommendation_basis === 'rules'
    ? `根据你保存的${start.recommendation_source_fields.map(t => labels[t]).join('、')}给出规则建议；这不是模型评估。`
    : '先带着你做，你还可以换一种方式。目前的信息还不足以给出更多判断。'}</p><p>{start.effective_start_source === 'conservative_fallback' ? '松伴先提供逐步提示；你还没有确认开始方式。' : `你已确认的开始方式：${choices[start.effective_start]}`}</p></div>;
  const hasSavedContent = topics.some(t => start.answers[t].state !== 'unanswered');
  const hasChosenStart = start.answers.chosen_start.state === 'answered' || start.answers.chosen_start.state === 'accepted_default';
  if (summary) return <section className="lp-card"><p className="lp-eyebrow">{profile?.display_name} · 孩子学习模式</p><h2>{hasChosenStart ? '这是你的学习起点' : '先选适合你的帮助方式'}</h2>{recommendation}
    <p>这里可以保存、查看和调整起点。课程状态可以回到学习首页查看。</p>
    <dl className="lp-summary">{topics.map(t => <div key={t}><dt>{labels[t]}</dt><dd>{showAnswer(start.answers[t])}</dd></div>)}</dl>
    <p>小尝试：{start.mini_attempt_status === 'answered' ? '已保存回答，未作能力评估' : start.mini_attempt_status === 'skipped' ? '你选择了暂时跳过' : '还没尝试'}。</p>
    <button className="lp-primary" onClick={edit}>{hasSavedContent ? '调整我的起点' : '开始回答'}</button></section>;
  const index = topics.indexOf(topic), locked = busy || !!pending || !!conflict || operationBlocked || !config.learning_enabled;
  const radio = (options: [string, string][]) => <div className="lp-options">{options.map(([value, text]) => <label key={value} className="lp-option"><input type="radio" name={topic} checked={draft.value === value} onChange={() => setDraft({ state: 'answered', value })} />{text}</label>)}</div>;
  return <section className="lp-card">
    <p className="lp-eyebrow">起点 · 第 {index + 1} / 6 个主题 · 还有 {start.missing_fields.length} 个主题未回答</p>
    <h2 ref={title} tabIndex={-1}>{labels[topic]}</h2>
    <p>{states[start.answers[topic].state]}{start.saved_at ? ` · 上次保存 ${new Date(start.saved_at).toLocaleString('zh-CN')}` : ''}</p>
    <form onSubmit={e => { e.preventDefault(); if (!(e.nativeEvent as KeyboardEvent).isComposing) void save(draft, true); }}>
      <fieldset disabled={locked}><legend className="lp-sr">{labels[topic]}</legend>
        {topic === 'age_band' && <><p>帮助松伴把话说得更适合你，不表示能力高低。</p>{config.age_band_options.length ? radio(config.age_band_options.map(a => [a, a])) : <p>年龄选项还未配置，可以暂时跳过。</p>}</>}
        {topic === 'experience' && radio([['none', '没试过'], ['some', '用过别人给的提示'], ['regular', '自己改过提示和结果']])}
        {topic === 'interests' && <div className="lp-options">{[...new Set(['故事', '绘画', '科学', '做小工具', ...(Array.isArray(draft.value) ? draft.value : [])])].map(value => <label className="lp-option" key={value}><input type="checkbox" checked={Array.isArray(draft.value) && draft.value.includes(value)} onChange={e => {
          const old = Array.isArray(draft.value) ? draft.value : []; const next = e.target.checked ? [...old, value] : old.filter(x => x !== value);
          setDraft(next.length ? { state: 'answered', value: next } : { state: 'unanswered', value: null });
        }} />{value}</label>)}<label className="lp-option"><input type="checkbox" checked={Array.isArray(draft.value) && draft.value.length === 0} onChange={e => setDraft(e.target.checked ? { state: 'answered', value: [] } : { state: 'unanswered', value: null })} />暂无兴趣选项</label></div>}
        {(topic === 'help_preference' || topic === 'chosen_start') && <>{topic === 'chosen_start' && recommendation}{radio(Object.entries(choices))}</>}
        {topic === 'mini_attempt_text' && <><div className="lp-material"><strong>松果班故事交换会</strong><p>松果班同学 · 2030年5月18日 14:00–15:00<br />松果活动室 · 带一本愿意分享的故事书</p><p>这是练习用的虚构活动，不是真实通知。</p></div>
          <p>读读就好，不用请 AI 回答。这不是考试。</p><label htmlFor="lp-mini">这张邀请卡是给谁的？同学几点到哪里？</label><textarea id="lp-mini" rows={5} maxLength={8000} value={typeof draft.value === 'string' ? draft.value : ''} onChange={e => setDraft({ state: 'answered', value: e.target.value })} /></>}
      </fieldset>
      {dirty && <p role="status">这些修改还没保存。</p>}{notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
      {conflict && <div className="lp-notice"><h3>核对两份内容</h3><p>我还没保存的修改：{showAnswer(draft)}</p><p>最新已保存内容：{showAnswer(conflict.answers[topic])}</p><p>最新建议：{choices[conflict.recommendation]}</p><div className="lp-actions">
        <button type="button" onClick={() => { setStart(conflict); setConflict(null); setError(''); if (draft.state === 'accepted_default') setDraft({ state: 'unanswered', value: null }); }}>以最新版本继续编辑，稍后再保存</button>
        <button type="button" onClick={() => { setStart(conflict); setDraft(conflict.answers[topic]); setConflict(null); setError(''); }}>放弃本题修改，使用已保存内容</button></div></div>}
      {pending && <button type="button" disabled={busy} onClick={() => void retryUnknown()}>核对并重试原保存</button>}
      {operationBlocked && <p>请保留本人输入并联系项目支持核对操作记录；本页已停止继续写入。</p>}
      {error && !pending && !conflict && !operationBlocked && <button type="button" disabled={busy} onClick={async () => { try { setConflict(await api.request<Start>(path)); } catch (e) { setError(errorText(e)); } }}>核对最新内容</button>}
      <div className="lp-actions"><button className="lp-primary" disabled={locked} type="submit">{busy ? '正在保存…' : index < 5 ? '保存并继续' : '保存我的选择'}</button>
        {topic === 'chosen_start' && <button type="button" disabled={locked} onClick={() => void save({ state: 'accepted_default', value: start.recommendation, recommendation_revision: start.recommendation_revision })}>采用当前建议</button>}
        <button type="button" disabled={locked} onClick={() => void save({ state: 'skipped', value: null }, true)}>暂时跳过</button>
      </div>
      <div className="lp-actions"><button type="button" disabled={busy || !!pending || !!conflict || dirty || index === 0} onClick={() => { const t = topics[index - 1]; setTopic(t); setDraft(start.answers[t]); setError(''); }}>上一题</button>
        <button type="button" disabled={busy || !!pending || !!conflict || dirty || index === 5} onClick={() => { const t = topics[index + 1]; setTopic(t); setDraft(start.answers[t]); setError(''); }}>查看下一题</button>
        <button type="button" disabled={locked} onClick={() => void send({ request_id: requestId(), expected_revision: start.revision, answers: { [topic]: { state: 'unanswered', value: null } } }, false)}>清除这题答案</button></div>
    </form>
  </section>;
}
