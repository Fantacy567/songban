// Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import type { Assistance, CompetitionDecisionInput, CompetitionLink, CompetitionLinkInput, CompetitionLinks, CompetitionSource, CompetitionSources, ExternalWorkInput, ExternalWorkVersionInput, PortfolioPageProps, WorkDetail, WorkList, WorkOutput, WorkSummary } from './types';
import './portfolio.css';

const encode = encodeURIComponent;
const originNames = { learning: '学习作品', competition: '参赛记录与贡献', external: '工具创作' };
const assistanceNames: Record<Assistance, string> = { none_reported: '本人填写：没有使用 AI 帮助', assisted: '有 AI 帮助，自己做过选择或修改', generated: '包含 AI 直接生成的内容', unknown: '帮助情况尚未说明' };
const linkStates = { offered: '等孩子核对', accepted: '孩子已确认收录', declined: '孩子未接受', revoked: '已撤回收录' };
function safeLink(value: string | null) {
  if (!value || /[\\\u0000-\u0020]/.test(value)) return null;
  try { const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? u.href : null; } catch { return null; }
}
function safeAsset(value: string | null | undefined) {
  if (value?.startsWith('blob:')) { try { return new URL(value).origin === location.origin ? value : null; } catch { return null; } }
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u0020]/.test(value)) return null;
  return value.startsWith('/api/platform/v1/') || value.startsWith('/static/') ? value : null;
}
function requestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return 'portfolio-' + [...crypto.getRandomValues(new Uint8Array(16))].map(n => n.toString(16).padStart(2, '0')).join('');
}
function errorStatus(e: unknown) { return typeof e === 'object' && e !== null && 'status' in e ? Number(e.status) : 0; }
function errorMessage(e: unknown) {
  const status = errorStatus(e);
  return status === 401 || status === 403 ? '当前身份或授权需要重新核对，请家长帮忙。'
    : status === 409 ? '另一处记录已经更新。你的输入仍在这里，请先看当前记录再决定。'
    : status === 422 ? '这些内容还不能保存，请检查文字、链接和所选来源。'
    : status === 429 ? '操作有些频繁，请稍后由你再次操作。' : '暂时没有读到完整记录，可以再读取一次。';
}
function scope<T extends { learner_id: string }>(value: T, learnerId: string): T {
  if (value.learner_id !== learnerId) throw Object.assign(new Error('Scope mismatch'), { status: 403 });
  return value;
}
function date(value: string) { const d = new Date(value); return Number.isNaN(d.getTime()) ? '时间待核对' : d.toLocaleString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) { return <div className={`pf-notice${error ? ' pf-error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>; }
function Outputs({ values }: { values: WorkOutput[] }) {
  return <div className="pf-outputs">{values.length ? values.map((output, i) => <section key={i} className="pf-output"><h3>{output.label}</h3>{output.kind === 'text' ? <div className="pf-text-output">{output.text || '这一版没有可读文字。'}</div> : safeLink(output.url) ? <><a className="pf-out-link" href={safeLink(output.url)!} target="_blank" rel="noopener noreferrer">打开实际作品 ↗</a><p className="pf-caption">将打开外部网站；链接由本人提供，平台未运行或独立核验。</p></> : <p>这个链接暂时无法安全打开，仍保留作品说明。</p>}</section>) : <p>暂时没有可读的产物；已有来源说明仍保留。</p>}</div>;
}
function WorkCover({ work, getAssetUrl }: Pick<PortfolioPageProps, 'getAssetUrl'> & { work: WorkSummary }) {
  const src = safeAsset(work.cover_asset_id ? getAssetUrl?.(work.cover_asset_id) : null);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  const text = work.actual_outputs.find(output => output.kind === 'text' && output.text)?.text;
  if (src && !failed) return <figure className="pf-cover"><img src={src} alt={`${work.title}的封面图；实际产物请在详情查看`} onError={() => setFailed(true)} loading="lazy" width="900" height="600" /><figcaption>作品封面 · 不是实际产物核验</figcaption></figure>;
  if (text) return <div className="pf-cover pf-text-preview" aria-label={`${work.title}的已保存文字预览`}><span className="pf-cover-label">已保存文字 · 排版预览</span><div aria-hidden="true">{text}</div><span className="pf-preview-foot">打开查看完整内容</span></div>;
  return <div className="pf-cover pf-illustrated-cover" role="img" aria-label={`${work.title}的松伴示意封面；实际作品通过详情中的链接打开`}><svg aria-hidden="true" width="120" height="150" viewBox="0 0 100 130"><path d="M49 4 20 43h16L10 79h25L10 112h30v15h19v-15h31L64 79h25L62 43h16Z" fill="#d0e94d"/><ellipse cx="39" cy="79" rx="9" ry="15" fill="#fffdf7"/><ellipse cx="60" cy="79" rx="9" ry="15" fill="#fffdf7"/><ellipse cx="41" cy="82" rx="4" ry="7" fill="#30362a"/><ellipse cx="62" cy="82" rx="4" ry="7" fill="#30362a"/></svg><strong aria-hidden="true">{work.title}</strong><span className="pf-cover-label">松伴示意封面 · 打开链接看实际作品</span>{failed && <span className="pf-preview-foot">封面暂未加载，作品仍保留。</span>}</div>;
}
type ExternalDraft = Omit<ExternalWorkInput, 'request_id'>;
type ExternalForm = { kind: 'external'; draft: ExternalDraft; original: string; workId?: string; expectedRevision?: number };
type OfferForm = { kind: 'offer'; projectId: string; sourceRevision: number; refs: string[]; title: string; summary: string; contribution: string; original: string };
type Editor = ExternalForm | OfferForm;
type Pending = { path: string; body: ExternalWorkInput | ExternalWorkVersionInput | CompetitionLinkInput | CompetitionDecisionInput; kind: 'external' | 'offer' | 'decision'; workId?: string };
const emptyDraft: ExternalDraft = { title: '', summary: '', url: '', tool_name: '', contribution: '', ai_assistance: 'unknown' };
function editorValue(editor: Editor | null) { if (!editor) return ''; if (editor.kind === 'external') return JSON.stringify(editor.draft); const { original, ...values } = editor; return JSON.stringify(values); }

export function PortfolioPage(props: PortfolioPageProps) {
  return <PortfolioSession key={`${props.identityKey}:${props.learnerId}:${props.mode}`} {...props} />;
}
function PortfolioSession({ transport, learnerId, mode, onOpenLearning, onOpenCompetition, onOpenStudio, onDirty, getAssetUrl, onCurrentWork, renderImageTools, refreshToken = 0, beforeTransition }: PortfolioPageProps) {
  const base = `/learners/${encode(learnerId)}`;
  const alive = useRef(true), locked = useRef(false), listGeneration = useRef(0), detailGeneration = useRef(0);
  const dirtyCallback = useRef(onDirty), workCallback = useRef(onCurrentWork);
  const appliedRefresh = useRef(refreshToken);
  dirtyCallback.current = onDirty; workCallback.current = onCurrentWork;
  const [items, setItems] = useState<WorkSummary[]>([]), [links, setLinks] = useState<CompetitionLink[]>([]), [sources, setSources] = useState<CompetitionSource[]>([]);
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState(''), [linksError, setLinksError] = useState(''), [sourceError, setSourceError] = useState('');
  const [opened, setOpened] = useState<WorkDetail | null>(null), [versionId, setVersionId] = useState(''), [opening, setOpening] = useState(false), [detailError, setDetailError] = useState('');
  const [editor, setEditor] = useState<Editor | null>(null), [pending, setPending] = useState<Pending | null>(null), [busy, setBusy] = useState(false), [unknown, setUnknown] = useState(false);
  const [mutationError, setMutationError] = useState(''), [notice, setNotice] = useState(''), [conflict, setConflict] = useState(false), [sourcesLoading, setSourcesLoading] = useState(false), [sourcesLoaded, setSourcesLoaded] = useState(false);
  const dirty = !!editor && editorValue(editor) !== editor.original || busy || !!pending;
  useEffect(() => { onDirty?.(dirty); }, [dirty, onDirty]);
  useEffect(() => { workCallback.current?.(opened); }, [opened]);
  useEffect(() => () => { workCallback.current?.(null); }, []);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++listGeneration.current; ++detailGeneration.current; dirtyCallback.current?.(false); }; }, []);
  const readWorks = useCallback(async () => {
    const generation = ++listGeneration.current; setLoading(true); setLoadError('');
    const results = await Promise.allSettled([transport<WorkList>(`${base}/works`), transport<CompetitionLinks>(`${base}/competition-source-links`)]);
    if (!alive.current || generation !== listGeneration.current) return;
    if (results[0].status === 'fulfilled') {
      try { const current = results[0].value.items.map(work => scope(work, learnerId)); setItems(current); setOpened(previous => previous?.origin === 'competition' && !current.some(work => work.id === previous.id) ? null : previous); }
      catch (e) { setItems([]); setOpened(null); setLoadError(errorMessage(e)); }
    } else { setItems([]); if ([401, 403, 404].includes(errorStatus(results[0].reason))) setOpened(null); setLoadError(errorMessage(results[0].reason)); }
    if (results[1].status === 'fulfilled') {
      try { setLinks(results[1].value.items.map(link => scope(link, learnerId))); setLinksError(''); }
      catch (e) { setLinks([]); setLinksError(errorMessage(e)); }
    } else { setLinks([]); setLinksError(errorStatus(results[1].reason) === 403 ? '比赛来源需要有效的学习及家长摘要授权；当前作品列表仍按实际权限显示。' : errorMessage(results[1].reason)); }
    setLoading(false);
  }, [base, learnerId, transport]);
  useEffect(() => { void readWorks(); }, [readWorks]);
  useEffect(() => {
    if (appliedRefresh.current === refreshToken || editor || pending || busy) return;
    appliedRefresh.current = refreshToken;
    void readWorks(); if (opened) void readDetail(opened.id);
  }, [refreshToken, editor, pending, busy, readWorks]);
  async function readDetail(workId: string, conflictRead = false) {
    const generation = ++detailGeneration.current; setOpening(true); setDetailError('');
    try {
      const work = scope(await transport<WorkDetail>(`${base}/works/${encode(workId)}`), learnerId);
      if (alive.current && generation === detailGeneration.current) { setOpened(work); setVersionId(work.current_version.id); if (conflictRead) setConflict(true); }
    } catch (e) { if (alive.current && generation === detailGeneration.current) { setOpened(null); setDetailError(errorMessage(e)); } }
    finally { if (alive.current && generation === detailGeneration.current) setOpening(false); }
  }
  async function readSources() {
    if (mode !== 'manager' || sourcesLoading) return;
    setSourcesLoading(true); setSourceError('');
    try { const result = await transport<CompetitionSources>(`${base}/competition-sources`); if (alive.current) { setSources(result.items); setSourcesLoaded(true); } }
    catch (e) { if (alive.current) { setSources([]); setSourceError(errorMessage(e)); } }
    finally { if (alive.current) setSourcesLoading(false); }
  }
  async function newExternal(work?: WorkDetail) {
    if (beforeTransition && !(await beforeTransition())) return;
    const draft: ExternalDraft = work ? { title: work.title, summary: work.summary, url: work.actual_outputs.find(o => o.kind === 'external_link')?.url || '', tool_name: work.provenance.source_label, contribution: work.contribution, ai_assistance: work.provenance.ai_assistance } : { ...emptyDraft };
    if (!work) setOpened(null);
    setEditor({ kind: 'external', draft, original: JSON.stringify(draft), workId: work?.id, expectedRevision: work?.revision }); setMutationError(''); setNotice(''); setConflict(false);
  }
  async function newOffer(source: CompetitionSource) {
    if (beforeTransition && !(await beforeTransition())) return;
    const value = { kind: 'offer' as const, projectId: source.project_id, sourceRevision: source.source_revision, refs: [] as string[], title: '', summary: '', contribution: '' };
    setOpened(null); setEditor({ ...value, original: JSON.stringify(value) }); setMutationError(''); setConflict(false);
  }
  async function execute(value: Pending) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setPending(value); setUnknown(false); setMutationError(''); setNotice('');
    try {
      const result = scope(await transport<WorkDetail | CompetitionLink>(value.path, 'POST', value.body), learnerId);
      if (!alive.current) return;
      setPending(null); setEditor(null); setConflict(false);
      if (value.kind === 'external') { const work = result as WorkDetail; setOpened(work); setVersionId(work.current_version.id); setNotice('已保存到私人作品集。保存作品不表示通过学习检查或公开发布。'); }
      else { if (value.kind === 'decision') setOpened(null); setNotice(value.kind === 'offer' ? '已提出来源，等孩子核对；还没有作为孩子作品收录。' : '已记录你的选择，作品集以当前可访问记录为准。'); }
      await readWorks();
    } catch (e) {
      if (!alive.current) return;
      const status = errorStatus(e);
      if (!status || status >= 500) { setUnknown(true); setMutationError('这次保存结果还没确认。内容和操作编号已保留；请先核对刚才的保存，不要再新建一份。'); }
      else {
        setPending(null); setMutationError(errorMessage(e));
        if ([401, 403].includes(status)) { setItems([]); setLinks([]); setOpened(null); setSources([]); }
        if (status === 409) {
          setConflict(true);
          if (value.kind === 'external' && value.workId) await readDetail(value.workId, true);
          else { await readWorks(); if (value.kind === 'offer') await readSources(); }
        }
      }
    } finally { locked.current = false; if (alive.current) setBusy(false); }
  }
  function submitExternal(event: FormEvent) {
    event.preventDefault();
    if (editor?.kind !== 'external' || pending || busy || conflict) return;
    if (!safeLink(editor.draft.url)) { setMutationError('请填写不含账号密码的 HTTP 或 HTTPS 作品链接。'); return; }
    const body = { request_id: requestId(), ...editor.draft, ...(editor.workId ? { expected_revision: editor.expectedRevision! } : {}) };
    void execute({ kind: 'external', workId: editor.workId, path: editor.workId ? `${base}/external-works/${encode(editor.workId)}/versions` : `${base}/external-works`, body });
  }
  function submitOffer(event: FormEvent) {
    event.preventDefault();
    if (editor?.kind !== 'offer' || pending || busy || conflict || !editor.refs.length) return;
    void execute({ kind: 'offer', path: `${base}/competition-source-links`, body: { request_id: requestId(), project_id: editor.projectId, expected_source_revision: editor.sourceRevision, selected_refs: [...editor.refs], title: editor.title, summary: editor.summary, contribution: editor.contribution } });
  }
  function decide(link: CompetitionLink, decision: CompetitionDecisionInput['decision']) {
    if (pending || busy || mode !== 'learner') return;
    void execute({ kind: 'decision', path: `${base}/competition-source-links/${encode(link.id)}/decision`, body: { request_id: requestId(), expected_revision: link.revision, decision } });
  }
  function closeEditor() { if (!pending && !busy) { setEditor(null); setConflict(false); setMutationError(''); } }
  async function closeDetail() { if (beforeTransition && !(await beforeTransition())) return; ++detailGeneration.current; setOpened(null); setDetailError(''); }
  const selectedVersion = opened?.versions.find(version => version.id === versionId);
  const currentOutputs = selectedVersion?.actual_outputs || opened?.actual_outputs || [];
  const actionsDisabled = busy || !!pending;
  const offerSource = editor?.kind === 'offer' ? sources.find(source => source.project_id === editor.projectId) : null;
  const changeExternal = (field: keyof ExternalDraft, value: string) => { if (editor?.kind === 'external') setEditor({ ...editor, draft: { ...editor.draft, [field]: value } }); };
  const changeOffer = (field: 'title' | 'summary' | 'contribution', value: string) => { if (editor?.kind === 'offer') setEditor({ ...editor, [field]: value }); };

  return <section data-platform-portfolio="" className="pf-shell" aria-labelledby="pf-title">
    <header className="pf-page-header"><div><p className="pf-eyebrow">作品集 · 默认私有</p><h1 id="pf-title">把做过的尝试，<br />留给未来的自己看。</h1><p>学习、比赛和工具创作，都留下真实的内容与自己做过的部分。</p></div>{mode === 'learner' && !editor && <button className="pf-primary" disabled={actionsDisabled} onClick={() => newExternal()}>添加工具作品 ＋</button>}</header>
    {notice && <Notice>{notice}</Notice>}
    {mutationError && <Notice error>{mutationError}</Notice>}
    {unknown && pending && <div className="pf-reconcile"><button className="pf-primary" disabled={busy} onClick={() => void execute(pending)}>核对刚才的保存</button><p>只核对原来的操作与内容。等待核对期间暂不修改表单。</p></div>}
    {busy && <Notice>正在保存并读取回执，请稍等…</Notice>}
    {conflict && editor?.kind === 'external' && opened && <Notice>已读到当前作品 v{opened.current_version.number}。你的未保存内容仍在表单里。<button className="pf-secondary" onClick={() => { setEditor({ ...editor, expectedRevision: opened.revision }); setConflict(false); setMutationError(''); }}>使用当前版本号，保留我的输入</button></Notice>}
    {conflict && editor?.kind === 'external' && !opened && <Notice error>{detailError || '当前版本还没读到，你的输入仍保留。'}<button className="pf-secondary" disabled={opening} onClick={() => editor.workId && void readDetail(editor.workId, true)}>重新读取当前作品</button></Notice>}
    {conflict && editor?.kind === 'offer' && offerSource && <Notice>比赛来源需要重新核对。<button className="pf-secondary" onClick={() => { setEditor({ ...editor, sourceRevision: offerSource.source_revision, refs: [] }); setConflict(false); setMutationError(''); }}>使用最新来源，重新勾选</button></Notice>}
    {conflict && editor?.kind === 'offer' && !offerSource && <Notice error>{sourceError || '比赛来源暂时无法读取，请保留输入后重新核对。'}<button className="pf-secondary" disabled={sourcesLoading} onClick={() => void readSources()}>重新读取当前来源</button></Notice>}

    {editor?.kind === 'external' && <form className="pf-editor" onSubmit={submitExternal}><h2>{editor.workId ? '给作品保存一个新版本' : '添加我用工具做的作品'}</h2><p>只保存链接与说明，不抓取或运行外部网站。写清楚自己做了什么，也可以写还没做好的地方。</p><fieldset disabled={actionsDisabled}><label>作品名称<input value={editor.draft.title} required maxLength={120} onChange={e => changeExternal('title', e.target.value)} /></label><label>这是一个什么作品？<textarea aria-label="这是一个什么作品？" value={editor.draft.summary} required maxLength={2000} onChange={e => changeExternal('summary', e.target.value)} /></label><label>实际作品链接<input type="url" inputMode="url" autoCapitalize="none" autoCorrect="off" spellCheck={false} value={editor.draft.url} required maxLength={2048} placeholder="https://…" onChange={e => changeExternal('url', e.target.value)} /></label><label>用了哪个工具？<input value={editor.draft.tool_name} required maxLength={80} placeholder="记不清时，可以写‘未知’" onChange={e => changeExternal('tool_name', e.target.value)} /></label><label>我自己做了什么？哪些地方有人帮忙？<textarea aria-label="我自己做了什么？哪些地方有人帮忙？" value={editor.draft.contribution} required maxLength={2000} onChange={e => changeExternal('contribution', e.target.value)} /></label><label>AI 帮助情况<select aria-label="AI 帮助情况" value={editor.draft.ai_assistance} onChange={e => changeExternal('ai_assistance', e.target.value)}><option value="unknown">还没说明 / 不确定</option><option value="none_reported">本人填写：没有使用 AI 帮助</option><option value="assisted">AI 有帮助，我也做过选择或修改</option><option value="generated">包含 AI 直接生成的内容</option></select></label></fieldset><div className="pf-actions"><button className="pf-primary" type="submit" disabled={actionsDisabled || conflict}>{editor.workId ? '保存为私人新版本' : '保存到私人作品集'}</button><button className="pf-secondary" type="button" disabled={actionsDisabled} onClick={closeEditor}>放弃未保存内容并返回</button></div></form>}

    {editor?.kind === 'offer' && <form className="pf-editor" onSubmit={submitOffer}><h2>提出比赛来源，交给孩子核对</h2><p>这些记录属于当前实际认证账号。请选择确实与这个孩子有关的部分；提议本身不证明是孩子的经历，也不会自动收录。</p><p><strong>{offerSource?.name || '来源暂时不可访问'}</strong> · 来源版本 {editor.sourceRevision}</p><fieldset disabled={actionsDisabled}><legend>选择本人来源（最多 12 条）</legend>{offerSource?.available_refs.map(source => <label className="pf-source-choice" key={source.ref}><input type="checkbox" checked={editor.refs.includes(source.ref)} disabled={!editor.refs.includes(source.ref) && editor.refs.length >= 12} onChange={e => setEditor({ ...editor, refs: e.target.checked ? [...editor.refs, source.ref] : editor.refs.filter(ref => ref !== source.ref) })} /><span><strong>{source.label}</strong><span className="pf-source-text">{source.text}</span></span></label>)}<label>给这份经历起个名称<input value={editor.title} required maxLength={120} onChange={e => changeOffer('title', e.target.value)} /></label><label>这份经历包含什么？<textarea aria-label="这份经历包含什么？" value={editor.summary} required maxLength={2000} onChange={e => changeOffer('summary', e.target.value)} /></label><label>孩子具体做了哪部分？帮助情况是什么？<textarea aria-label="孩子具体做了哪部分？帮助情况是什么？" value={editor.contribution} required maxLength={2000} onChange={e => changeOffer('contribution', e.target.value)} /></label></fieldset><div className="pf-actions"><button className="pf-primary" type="submit" disabled={actionsDisabled || conflict || !editor.refs.length}>提出给孩子核对</button><button className="pf-secondary" type="button" disabled={actionsDisabled} onClick={closeEditor}>放弃未保存内容并返回</button></div></form>}

    {!editor && <>
      {opening && <Notice>正在读取这件作品的当前内容与历史…</Notice>}
      {detailError && <Notice error>{detailError}<button className="pf-secondary" onClick={() => { setDetailError(''); setOpened(null); }}>返回作品列表</button></Notice>}
      {opened && <article className="pf-detail"><button className="pf-secondary" onClick={() => void closeDetail()}>返回我的作品集</button><div className="pf-detail-heading"><p className="pf-eyebrow">{originNames[opened.origin]} · 私人保存</p><h2>{opened.title}</h2><p>{opened.summary}</p></div><div className="pf-detail-grid"><div><h2 className="pf-section-title">实际保存的内容</h2>{selectedVersion && <p className="pf-caption">v{selectedVersion.number} · {date(selectedVersion.created_at)}{selectedVersion.id !== opened.current_version.id ? ' · 历史产物，当前说明与贡献不会倒写为历史记录。' : ' · 当前版本'}</p>}<Outputs values={currentOutputs} /></div><aside className="pf-provenance"><h3>来源与本人贡献</h3><p>{opened.provenance.source_label}</p><p className="pf-source-text">{opened.contribution}</p><p>{assistanceNames[opened.provenance.ai_assistance]}</p><p className="pf-caption">{opened.available_actions.includes('open_studio') ? '代码版本由系统保存；观察与本人贡献为学习者自述，不自动代表已掌握。' : opened.origin === 'competition' ? '这是一份来源提议经过孩子确认后的参赛记录，不表示孩子独立完成整个团队作品。' : opened.origin === 'learning' ? '保存版本与学习检查是两件事；检查和报告请回到原课程查看。' : '链接与说明由本人填写，平台未独立核验或运行外部作品。'}</p><label>查看哪个版本？<select aria-label="查看哪个版本？" value={versionId} onChange={e => setVersionId(e.target.value)}>{opened.versions.map(version => <option value={version.id} key={version.id}>v{version.number}{version.id === opened.current_version.id ? ' · 当前' : ' · 历史'} · {date(version.created_at)}</option>)}</select></label><div className="pf-actions">{mode === 'learner' && opened.available_actions.includes('open_studio') && onOpenStudio && <button className="pf-primary" disabled={actionsDisabled} onClick={() => void Promise.resolve(onOpenStudio(opened.source_ref.id)).catch(() => setDetailError('这次未能打开创作空间，已归档内容仍保留。'))}>回到创作工作台</button>}{opened.origin === 'learning' && opened.available_actions.includes('open_learning') && <button className="pf-primary" disabled={actionsDisabled} onClick={() => void Promise.resolve(onOpenLearning(undefined, opened.source_ref.id)).catch(() => setDetailError('这次还没有打开课程，作品内容仍保留。'))}>回到这节课</button>}{opened.origin === 'competition' && opened.available_actions.includes('open_competition') && onOpenCompetition && <button className="pf-secondary" disabled={actionsDisabled} onClick={() => void Promise.resolve(onOpenCompetition(opened.source_ref.id)).catch(() => setDetailError('暂时无法打开原比赛，已有来源说明仍保留。'))}>回到原比赛</button>}{mode === 'learner' && opened.origin === 'external' && opened.available_actions.includes('save_version') && versionId === opened.current_version.id && <button className="pf-primary" disabled={actionsDisabled} onClick={() => newExternal(opened)}>修改说明 / 保存新版本</button>}</div></aside></div>{mode === 'learner' && !opened.available_actions.includes('open_studio') && renderImageTools && <section className="pf-image-tools" aria-label="这件作品的图片工具">{renderImageTools(opened)}</section>}</article>}
      {!opened && !opening && <>
        {loading && <Notice>正在读取有权查看的作品…</Notice>}{loadError && <Notice error>{loadError}</Notice>}
        {!loading && !loadError && !items.length && <div className="pf-empty"><h2>第一个作品，可以从一次小尝试开始。</h2><p>保存过的学习作品会出现在这里；也可以由孩子添加工具创作的实际链接。</p>{mode === 'learner' && <button className="pf-primary" onClick={() => void Promise.resolve(onOpenLearning()).catch(() => setLoadError('学习入口暂时未打开，可以稍后再试。'))}>去学习，开始一个作品</button>}</div>}
        <div className="pf-gallery">{items.map(work => <article key={work.id} data-work-id={work.id} className="pf-work"><button className="pf-open-work" aria-label={`打开作品：${work.title}`} disabled={actionsDisabled} onClick={() => void readDetail(work.id)}><WorkCover work={work} getAssetUrl={getAssetUrl} /><span className="pf-work-meta">{originNames[work.origin]} · 私人保存 · v{work.current_version.number}</span><h2>{work.title}</h2><p>{work.summary}</p></button></article>)}</div>
        <button className="pf-secondary pf-refresh" disabled={loading} onClick={() => void readWorks()}>重新读取作品与来源</button>
      </>}
      <section className="pf-link-section" aria-labelledby="pf-links-title"><h2 id="pf-links-title">比赛来源，先核对再收录</h2><p>只收录你实际做过的部分。接受、拒绝或撤回只改变作品集，不修改原比赛记录。</p>{linksError && <Notice error>{linksError}</Notice>}{!links.length && !linksError && <p className="pf-caption">目前没有需要核对的来源提议。</p>}{links.map(link => <article className="pf-link-record" key={link.id} data-source-link={link.id}><div className="pf-link-heading"><h3>{link.title}</h3><span>{linkStates[link.state]}</span></div><p>{link.summary}</p><p><strong>来源：</strong>{link.source_label}</p><p className="pf-source-text"><strong>提出的本人贡献：</strong>{link.contribution}</p><details><summary>查看来源原文与产物</summary>{link.sources.map(source => <section className="pf-source-preview" key={source.ref}><h4>{source.label}</h4><p className="pf-source-text">{source.text}</p><Outputs values={source.outputs} /></section>)}</details>{mode === 'learner' && <div className="pf-actions">{link.state === 'offered' && <><button className="pf-primary" disabled={actionsDisabled} onClick={() => decide(link, 'accept')}>这是我的经历，确认收录</button><button className="pf-secondary" disabled={actionsDisabled} onClick={() => decide(link, 'decline')}>不是 / 暂不收录</button></>}{(link.state === 'offered' || link.state === 'accepted') && <button className="pf-secondary" disabled={actionsDisabled} onClick={() => decide(link, 'revoke')}>撤回这份来源</button>}</div>}</article>)}</section>
      {mode === 'manager' && <section className="pf-manager-sources"><h2>从当前账号的比赛记录提出来源</h2><p>请选择与这位孩子有关的本人记录，写清孩子实际做过的部分，再交给孩子确认。</p><button className="pf-secondary" disabled={sourcesLoading || actionsDisabled} onClick={() => void readSources()}>{sourcesLoading ? '正在读取本人来源…' : '读取当前账号可提出的来源'}</button>{sourceError && <Notice error>{sourceError}</Notice>}{sourcesLoaded && !sources.length && !sourceError && <p>当前账号没有可提出的比赛来源。不会自动使用其他账号或队友记录。</p>}{sources.map(source => <article className="pf-source-summary" key={source.project_id}><h3>{source.name}</h3><p>{source.available_refs.length ? `${source.available_refs.length} 条当前账号的本人进展或任务可核对。任务安排不代表已经完成。` : '目前没有可提出的本人进展或任务。'}</p><button className="pf-secondary" disabled={actionsDisabled || !source.available_refs.length} onClick={() => newOffer(source)}>选择来源并写贡献</button></article>)}</section>}
    </>}
    <p className="pf-privacy-note">这里只有当前身份有权查看的私人记录。保存、确认来源与公开展示分别处理；当前没有公开发布功能。</p>
  </section>;
}
