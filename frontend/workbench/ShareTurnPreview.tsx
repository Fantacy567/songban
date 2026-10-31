import { useEffect, useId, useRef, useState } from 'react';
import { Sources } from './MessageCard';
import { errorText, operationKey, save, saved, uncertain, type WorkbenchApi } from './songban-adapter';
import type { Message, MountOptions, ShareCommand, ShareReceipt, Team } from './types';

// Adapted from ShareSuggestionPreview: select/edit/preview/shared steps, stable payload,
// write lock, mounted guard and focus transition. The source project is never contacted.
export function ShareTurnPreview({ message, userMessage, api, options, scope, team, onClose }: {
  message: Message; userMessage?: Message; api: WorkbenchApi; options: MountOptions; scope: string; team: Team | null; onClose(): void;
}) {
  const key = `${scope}:share:${message.id}`;
  const cached = useRef(saved<{ body: string; teamId: string; pending: ShareCommand | null; receipt: ShareReceipt | null }>(key, { body: message.text.length <= 3500 ? message.text : '', teamId: team?.id || '', pending: null, receipt: null })).current;
  const [body, setBody] = useState(cached.body), [teamId, setTeamId] = useState(cached.teamId);
  const [pending, setPending] = useState<ShareCommand | null>(cached.pending);
  const [receipt, setReceipt] = useState<ShareReceipt | null>(cached.receipt);
  const [step, setStep] = useState<'edit' | 'preview' | 'shared'>(cached.receipt ? 'shared' : cached.pending ? 'preview' : 'edit');
  const [teams, setTeams] = useState<Team[]>(team ? [team] : []);
  const [loading, setLoading] = useState(!team), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const mounted = useRef(true), writeLock = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null), controller = useRef(new AbortController());
  const headingId = useId(), bodyId = useId(), teamIdLabel = useId();
  useEffect(() => {
    if (!team) void api.request<{ teams: Team[] }>('/api/core/me', { signal: controller.current.signal }).then(data => {
      if (mounted.current && api.active) { setTeams(data.teams); setLoading(false); }
    }).catch(cause => { if (mounted.current && api.active) { setError(errorText(cause)); setLoading(false); } });
    heading.current?.focus();
    return () => { mounted.current = false; controller.current.abort(); };
  }, [api, team?.id]);
  useEffect(() => { save(key, { body, teamId, pending, receipt }); }, [key, body, teamId, pending, receipt]);
  function preview() {
    if (!body.trim() || body.length > 3500 || !teams.some(item => item.id === teamId)) return;
    setError(''); setStep('preview'); requestAnimationFrame(() => heading.current?.focus());
  }
  async function publish() {
    if (writeLock.current || !api.active || !teams.some(item => item.id === teamId)) return;
    const command: ShareCommand = pending || { request_id: operationKey(), message_id: message.id, team_id: teamId, summary: body.trim(), selected: true };
    writeLock.current = true; setBusy(true); setError(''); setPending(command);
    save(key, { body, teamId, pending: command, receipt: null });
    try {
      const result = await api.request<ShareReceipt>(`/api/workbench/sessions/${encodeURIComponent(message.session_id)}/share`, { method: 'POST', body: command, signal: controller.current.signal });
      if (!mounted.current || !api.active) return;
      setReceipt(result); setPending(null); setStep('shared');
      save(key, { body, teamId, pending: null, receipt: result });
      try { options.onShared(); } catch { /* A confirmed write remains successful if shell refresh fails. */ }
    } catch (cause) {
      if (!mounted.current || !api.active) return;
      if (uncertain(cause)) setError('共享结果尚未确定。内容和操作标识已保留；点击“核对这次共享”可确认同一次操作，不会另建记录。');
      else { setPending(null); setError(`${errorText(cause)} 摘要已保留。`); }
    } finally { writeLock.current = false; if (mounted.current && api.active) setBusy(false); }
  }
  const locked = busy || Boolean(pending);
  return <section className="sbw-sharePanel" aria-labelledby={headingId} aria-busy={busy}>
    <div className="sbw-panelHeading"><h3 id={headingId} ref={heading} tabIndex={-1}>{step === 'preview' ? '确认共享的回合与摘要' : step === 'shared' ? '已保存到团队记录' : '编辑要交给队友的摘要'}</h3><button type="button" className="sbw-textButton" onClick={onClose} disabled={busy}>收起</button></div>
    <p className="sbw-muted">共享本轮原提问、你编辑的摘要及实际模型／测试来源说明。原助手回复不会随摘要自动共享；其他回合仍属于本人。共享不会自动发起统筹。</p>
    {error && <p className="sbw-error" role="alert">{error}</p>}
    {loading && <p className="sbw-muted" role="status">正在读取你已加入的团队…</p>}
    {!loading && !teams.length && <p className="sbw-notice">还没有可共享的团队。摘要已保留。<button type="button" onClick={() => options.onNavigate('team')}>创建或加入小队</button></p>}
    {step !== 'shared' && <><details className="sbw-details"><summary>本人核对原回答与来源（不自动共享）</summary><p className="sbw-messageText">{message.text}</p><Sources sources={message.sources || []} /></details><label htmlFor={teamIdLabel}>共享到哪个团队？</label><select id={teamIdLabel} value={teamId} disabled={locked || Boolean(team) || step === 'preview'} onChange={e => setTeamId(e.target.value)}><option value="">请选择团队</option>{teams.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></>}
    {step === 'edit' && <form onSubmit={event => { event.preventDefault(); preview(); }}><label htmlFor={bodyId}>本人编辑摘要</label><textarea id={bodyId} rows={5} maxLength={3500} value={body} disabled={locked} onChange={e => setBody(e.target.value)} />{message.text.length > 3500 && <p className="sbw-muted">原回答较长，请选择必要的片段，或写下你要共享的结论。</p>}<small>{body.length}/3500 字</small><div className="sbw-actions"><button className="sbw-primary" disabled={locked || !body.trim() || !teamId || !teams.some(t => t.id === teamId)}>预览共享内容</button></div></form>}
    {step === 'preview' && <><article className="sbw-preview"><small>发给「{teams.find(t => t.id === teamId)?.name || '所选团队'}」</small><h4>本轮原提问（也会共享）</h4><p className="sbw-messageText">{userMessage?.text || '原提问未读取，请收起后重新核对本轮记录。'}</p><h4>本人编辑摘要</h4><p className="sbw-messageText">{body}</p><p className="sbw-muted">实际模型：{message.actual_model || '未知'}{message.mode === 'fixture' ? ' · 模拟测试回答，不代表真实模型效果' : ''}</p><p className="sbw-muted">编辑摘要不会修改上方原提问；如不准备共享原提问，可收起并取消。</p></article><div className="sbw-actions"><button type="button" className="sbw-primary" disabled={busy || loading || !userMessage || !teams.some(t => t.id === teamId)} onClick={() => void publish()}>{busy ? '正在保存…' : pending ? '核对这次共享' : '确认共享到团队'}</button><button type="button" disabled={locked} onClick={() => setStep('edit')}>返回修改</button></div></>}
    {step === 'shared' && receipt && <div className="sbw-notice" role="status"><p>{receipt.notice || '已归档，本次没有触发团队统筹。'}{receipt.duplicate && ' 已恢复同一次共享的回执。'}</p><small>记录：{receipt.note_id}</small><div className="sbw-actions"><button type="button" onClick={() => options.onNavigate('library')}>查看团队记录 ↗</button>{team && <button type="button" onClick={() => options.onNavigate('tasks')}>前往任务与统筹 ↗</button>}</div></div>}
  </section>;
}
