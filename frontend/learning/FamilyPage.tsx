import { useCallback, useEffect, useRef, useState } from 'react';
import { errorText, type LearningApi } from './api';
import type { Config, Consent, Consents, ConsentText, Family, Scope } from './types';
import { Dialog, Notice, useGuard, useMutation, type SetGuard } from './ui';
import { ParentReports } from './ReportsPanel';

const relationshipLabels = { pending: '关系已声明，待按试点流程确认', verified: '关系已按项目流程确认', rejected: '关系声明未获确认', revoked: '关系授权已撤回' };
const scopeLabels: Record<Scope, string> = { learning: '学习记录', live_model: '真实模型', parent_summary: '家长摘要', report_publication: '报告发布' };
export function FamilyPage({ api, config, setGuard, enter }: { api: LearningApi; config: Config; setGuard: SetGuard; enter: (id: string) => Promise<void> }) {
  const [family, setFamily] = useState<Family | null | undefined>(undefined), [consents, setConsents] = useState<Consents | null>(null);
  const [texts, setTexts] = useState<Record<string, ConsentText>>({}), [error, setError] = useState(''), [loading, setLoading] = useState(true);
  const [name, setName] = useState(''), [relationship, setRelationship] = useState(''), [scopes, setScopes] = useState<Scope[]>([]), [ack, setAck] = useState(false);
  const [entering, setEntering] = useState(false), [revoke, setRevoke] = useState<Consent | null>(null), [reason, setReason] = useState('');
  const [reportDirty, setReportDirty] = useState(false);
  const alive = useRef(true);
  const readGeneration = useRef(0);
  const reload = useCallback(async () => {
    const generation = ++readGeneration.current;
    const current = () => alive.current && generation === readGeneration.current;
    setLoading(true); setError('');
    try {
      const list = await api.request<{ items: Family[]; next_cursor: null }>('/families');
      let f = list.items[0] || null;
      if (f) f = await api.request<Family>(`/families/${encodeURIComponent(f.id)}`);
      let c: Consents | null = null;
      const learner = f?.learners[0];
      if (learner) {
        let collected: Consents = await api.request<Consents>(`/learners/${encodeURIComponent(learner.id)}/consents`);
        const cursors = new Set<string>();
        while (collected.next_cursor) {
          if (cursors.has(collected.next_cursor)) throw new Error('Repeated cursor');
          cursors.add(collected.next_cursor);
          const page: Consents = await api.request<Consents>(`/learners/${encodeURIComponent(learner.id)}/consents?cursor=${encodeURIComponent(collected.next_cursor)}`);
          collected = { ...page, items: [...collected.items, ...page.items] };
        }
        c = collected;
      }
      const versions = [...new Set([config.consent_version, ...(c?.items.map(i => i.consent_version) || [])])];
      const entries = await Promise.all(versions.map(async v => [v, await api.consentText(v)] as const));
      const ts = Object.fromEntries(entries);
      if (c?.items.some(i => ts[i.consent_version]?.text_sha256 !== i.text_sha256)) throw new Error('Historical text mismatch');
      if (current()) { setFamily(f); setConsents(c); setTexts(ts); }
    } catch (e) { if (current()) setError(errorText(e)); throw e; }
    finally { if (current()) setLoading(false); }
  }, [api, config.consent_version]);
  useEffect(() => {
    alive.current = true;
    void reload().catch(() => {});
    return () => { alive.current = false; ++readGeneration.current; };
  }, [reload]);
  const task = useMutation(api, reload);
  useGuard(setGuard, !!name || !!relationship || !!scopes.length || ack || !!reason || reportDirty || !!task.pending || task.busy);
  const learner = family?.learners[0], text = texts[config.consent_version];
  const verified = learner?.guardian_link.status === 'verified' && consents?.relationship_status === 'verified';
  const textApproved = text?.approval_status === 'approved_for_pilot' && text.acceptance_enabled && !!text.approved_at;
  const permitted = verified && textApproved && config.learning_enabled;
  const effective = [...new Set(consents?.items.flatMap(i => i.effective_scopes) || [])];
  const disabled = task.busy || !!task.pending || loading || !!error;
  return <section className="lp-card"><p className="lp-eyebrow">家长管理 · 已重新认证</p><h2>为孩子准备学习</h2>
    <p>只需一个学习称呼，不需要精确生日、学校或家庭地址。</p>
    {loading && <Notice>正在读取本人家庭和授权记录…</Notice>}
    {error && <><Notice error>暂时没读到完整家庭或授权内容，尚不能确认当前状态。</Notice><button onClick={() => void reload().catch(() => {})}>重新读取家庭与授权</button></>}
    {task.error && <Notice error>{task.error}</Notice>}
    {task.pending && <button disabled={task.busy} onClick={() => void task.retry().catch(() => {})}>核对并重试原操作</button>}
    {!loading && !error && family === null && <><p>当前账号还没有家庭档案。</p><button className="lp-primary" disabled={disabled || !config.learning_enabled} onClick={async () => { const ok = await task.run('/families', {}); if (!ok) await reload().catch(() => {}); }}>建立本人家庭</button></>}
    {family && !learner && <form onSubmit={async e => { e.preventDefault(); if (await task.run(`/families/${encodeURIComponent(family.id)}/learners`, { expected_revision: family.revision, display_name: name.trim(), age_band: null, declared_relationship: relationship })) { setName(''); setRelationship(''); } }}>
      <fieldset disabled={disabled || !config.learning_enabled}><legend>填写孩子资料</legend><label htmlFor="lp-name">学习称呼（避免使用实名）</label><input id="lp-name" value={name} maxLength={60} required onChange={e => setName(e.target.value)} />
        <label htmlFor="lp-relation">声明与孩子的关系</label><select id="lp-relation" value={relationship} required onChange={e => setRelationship(e.target.value)}><option value="">请选择</option><option value="父母">父母</option><option value="其他监护人">其他监护人</option></select>
        <p>提交后仅记录你的声明。关系需要按试点流程确认，不会自动获准。</p><button className="lp-primary" disabled={!name.trim() || !relationship}>保存孩子档案</button></fieldset></form>}
    {learner && <><h3>{learner.display_name}</h3><Notice>{relationshipLabels[learner.guardian_link.status]}</Notice>
      {!verified && <p>请联系项目负责人员，按试点流程核对关系。当前页面不能自行确认关系，也不能读取孩子学习记录。</p>}
      <p>当前有效范围：{effective.length ? effective.map(s => scopeLabels[s]).join('、') : '尚无有效学习授权'}。</p>
    {(config.reports_enabled || config.reports_readable) && verified && learner && effective.includes('parent_summary') && api.snapshot().session && <ParentReports api={api} session={api.snapshot().session!} learnerId={learner.id} onDirty={setReportDirty} />}
      <h3>授权内容</h3>
      {text && <><details open><summary>{text.title}</summary><p className="lp-pre">{text.text}</p>{text.scope_purposes.map(p => <p key={p.scope}>{scopeLabels[p.scope]}：{p.purpose}</p>)}<p>{text.notice}</p><p>文本版本：{text.consent_version}</p></details>
        {!textApproved && <Notice>授权内容待确认。当前文本为{ text.approval_status === 'withdrawn' ? '已撤下版本' : '未开放确认的版本'}，不能据此开启正式授权。</Notice>}
        {permitted && <form onSubmit={async e => { e.preventDefault(); if (await task.run(`/learners/${encodeURIComponent(learner.id)}/consents`, { expected_revision: learner.revision, consent_version: text.consent_version, scopes, acknowledged: true })) { setScopes([]); setAck(false); } }}>
          <fieldset disabled={disabled}><legend>选择本次同意的范围</legend>{text.scope_purposes.map(p => <label className="lp-option" key={p.scope}><input type="checkbox" checked={scopes.includes(p.scope)} onChange={e => setScopes(e.target.checked ? [...scopes, p.scope] : scopes.filter(s => s !== p.scope))} />{p.purpose}</label>)}
          <label className="lp-option"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />我已阅读以上版本的授权内容和用途</label><button disabled={!ack || !scopes.length}>确认本次授权</button></fieldset></form>}
      </>}
      <h3>已有授权记录</h3>{consents?.items.length === 0 && <p>尚无可读取的本人授权记录。</p>}
      {consents?.items.map(c => <div className="lp-record" key={c.id}><p>{c.status === 'revoked' ? '已撤回' : '已记录'} · {new Date(c.recorded_at).toLocaleString('zh-CN')}</p><p>当前有效范围：{c.effective_scopes.map(s => scopeLabels[s]).join('、') || '无'}</p>
        <details><summary>查看当时的授权原文（{c.consent_version}）</summary><p className="lp-pre">{texts[c.consent_version]?.text}</p>{texts[c.consent_version]?.scope_purposes.map(p => <p key={p.scope}>{p.purpose}</p>)}</details>
        {c.status === 'active' && <button disabled={disabled} onClick={() => { setRevoke(c); setReason(''); }}>撤回这条授权</button>}</div>)}
      <div className="lp-notice"><p>进入后，这个浏览器的家长管理会退出；回来管理需要重新登录。</p><p>这个账号在其他设备上的旧版登录也可能需要重新登录。</p></div>
      {verified && effective.includes('learning') && config.learning_enabled && <button className="lp-primary" disabled={disabled || reportDirty || ack || scopes.length > 0} onClick={() => setEntering(true)}>进入孩子学习模式</button>}
      {verified && !effective.includes('learning') && <p>尚缺有效的学习授权，确认开放的授权内容后再进入。</p>}
    </>}
    {entering && learner && <Dialog title="进入孩子学习模式" close={() => setEntering(false)}><p>管理内容将收起。返回管理时，需要家长再次输入账号密码。</p><div className="lp-actions"><button onClick={() => setEntering(false)}>取消</button><button className="lp-primary" onClick={() => { setEntering(false); void enter(learner.id); }}>确认进入</button></div></Dialog>}
    {revoke && <Dialog title="撤回这条授权" close={() => { setRevoke(null); setReason(''); }}><p>撤回后，相关学习会话与访问权限将由服务端失效。已保存历史不会因此被当作从未发生。</p><label htmlFor="lp-reason">撤回原因</label><textarea id="lp-reason" maxLength={8000} value={reason} onChange={e => setReason(e.target.value)} /><div className="lp-actions"><button disabled={task.busy} onClick={() => { setRevoke(null); setReason(''); }}>取消</button><button disabled={disabled || !reason.trim()} onClick={async () => { if (await task.run(`/consents/${encodeURIComponent(revoke.id)}/revoke`, { expected_revision: revoke.revision, reason: reason.trim() })) { setRevoke(null); setReason(''); } }}>确认撤回</button></div>{task.error && <Notice error>{task.error}</Notice>}{task.pending && <button disabled={task.busy} onClick={() => void task.retry().catch(() => {})}>核对并重试原操作</button>}</Dialog>}
  </section>;
}
