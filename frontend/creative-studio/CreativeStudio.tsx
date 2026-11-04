// Copyright (c) 2026 2292576833. AI workbench contribution; joint project ownership: COPYRIGHT.md.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, errorText, requestId } from '../learning/api';
import type { CreativeStudioProps, StudioList, StudioPreview, StudioProject } from './types';
import { previewDocumentUrl } from './preview';
import './studio.css';

const base = '/studio/projects';
const route = (id: string) => `${base}/${encodeURIComponent(id)}`;
const activeJob = (p: StudioProject | null) => p?.jobs.some(job => job.state === 'queued' || job.state === 'running') || false;
const unresolved = (p: StudioProject | null) => p?.jobs.some(job => job.state === 'unknown') || false;
const actorNames = { child: '我的修改', ai: '松伴协助', system: '起始文件' };
const jobNames = { queued: '已排队，等待松伴', running: '松伴正在修改作品', succeeded: '这次协助已完成', failed: '这次协助未完成', unknown: '这次结果还待核对' };

export function CreativeStudio(props: CreativeStudioProps) {
  return <StudioIdentity key={props.identityKey} {...props} />;
}
function StudioIdentity({ api, learnerId, initialProjectId, onProjectChange, onDirty, beforeTransition, onOpenPortfolio }: CreativeStudioProps) {
  const [projects, setProjects] = useState<StudioProject[]>([]), [project, setProject] = useState<StudioProject | null>(null);
  const [runtime, setRuntime] = useState({ available: false, reason: '' });
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [idea, setIdea] = useState(''), [question, setQuestion] = useState('');
  const [selectedFile, setSelectedFile] = useState('index.html'), [drafts, setDrafts] = useState<Record<string, string>>({});
  const [explanation, setExplanation] = useState(''), [prediction, setPrediction] = useState(''), [observation, setObservation] = useState(''), [contribution, setContribution] = useState('');
  const [tab, setTab] = useState<'chat' | 'preview' | 'code'>('chat'), [rightTab, setRightTab] = useState<'preview' | 'code'>('preview');
  const [preview, setPreview] = useState<StudioPreview | null>(null), [previewError, setPreviewError] = useState(''), [run, setRun] = useState(0), [pollPaused, setPollPaused] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const alive = useRef(true), sequence = useRef(0), projectRef = useRef<StudioProject | null>(null);
  const first = useRef(initialProjectId), input = useRef<HTMLTextAreaElement>(null);
  const fileDirty = !!project && project.files.some(file => (drafts[file.path] ?? file.content) !== file.content);
  const dirty = !!idea.trim() || !!question.trim() || fileDirty || !!explanation.trim() || !!prediction.trim() || !!observation.trim() || !!contribution.trim() || uncertain || activeJob(project);
  const pending = activeJob(project), unknown = unresolved(project);
  const locked = busy || pending || uncertain;
  useEffect(() => { onDirty?.(dirty); return () => onDirty?.(false); }, [dirty, onDirty]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++sequence.current; projectRef.current = null; }; }, []);

  const accept = useCallback((next: StudioProject, resetFiles = true) => {
    projectRef.current = next; setProject(next); setRuntime(next.runtime);
    setProjects(items => [next, ...items.filter(item => item.id !== next.id)]);
    if (resetFiles) setDrafts(Object.fromEntries(next.files.map(file => [file.path, file.content])));
  }, []);

  useEffect(() => {
    const captured = ++sequence.current; setLoading(true);
    void api.platform<StudioList>(base).then(async list => {
      if (!alive.current || sequence.current !== captured) return;
      setProjects(list.items); setRuntime(list.runtime);
      if (first.current) {
        const data = await api.platform<StudioProject>(route(first.current));
        if (alive.current && sequence.current === captured) accept(data);
      }
    }).catch(e => { if (alive.current && sequence.current === captured) setError(errorText(e)); })
      .finally(() => { if (alive.current && sequence.current === captured) setLoading(false); });
  }, [api, accept]);

  useEffect(() => {
    if (!project?.current_version_id) { setPreview(null); return; }
    let valid = true; setPreview(null); setPreviewError('');
    void api.platform<StudioPreview>(route(project.id) + '/preview').then(value => {
      if (valid && value.version_id === project.current_version_id) setPreview(value);
    }).catch(e => { if (valid) setPreviewError(errorText(e)); });
    return () => { valid = false; };
  }, [api, project?.id, project?.current_version_id, run]);

  useEffect(() => {
    if (!pending || !project || pollPaused) return;
    const id = project.id; let valid = true, attempts = 0, timer = 0;
    const check = async () => {
      try {
        const next = await api.platform<StudioProject>(route(id));
        if (!valid || !alive.current || projectRef.current?.id !== id) return;
        accept(next);
        if (!activeJob(next)) return;
        if (++attempts >= 40) { setPollPaused(true); return; }
        timer = window.setTimeout(check, 1500);
      } catch (e) { if (valid) { setError(errorText(e)); setPollPaused(true); } }
    };
    timer = window.setTimeout(check, 1000);
    return () => { valid = false; window.clearTimeout(timer); };
  }, [api, accept, pending, project?.id, pollPaused]);

  function clearDrafts() { setIdea(''); setQuestion(''); setExplanation(''); setPrediction(''); setObservation(''); setContribution(''); setError(''); setNotice(''); setUncertain(false); setPollPaused(false); }
  async function mayLeave() {
    if (!dirty) return true;
    return beforeTransition ? await beforeTransition() : window.confirm('这里还有未保存的文字或待核对的操作。确定离开当前作品吗？');
  }
  async function select(id: string | null) {
    if (busy || id === project?.id || !(await mayLeave())) return;
    const captured = ++sequence.current; setBusy(true); clearDrafts(); setPreview(null);
    try {
      if (!id) { projectRef.current = null; setProject(null); setDrafts({}); setTab('chat'); onProjectChange?.(null); return; }
      const data = await api.platform<StudioProject>(route(id));
      if (alive.current && sequence.current === captured) { accept(data); onProjectChange?.(id); }
    } catch (e) { if (alive.current && sequence.current === captured) setError(errorText(e)); }
    finally { if (alive.current && sequence.current === captured) setBusy(false); }
  }
  async function create() {
    if (busy || !idea.trim()) return;
    const captured = sequence.current; setBusy(true); setError('');
    try {
      const result = await api.platform<StudioProject>(base, 'POST', { request_id: requestId(), title: idea.trim().slice(0, 45), idea: idea.trim(), ...(learnerId ? { learner_id: learnerId } : {}) });
      if (alive.current && captured === sequence.current) { accept(result); clearDrafts(); onProjectChange?.(result.id); }
    } catch (e) {
      if (alive.current && captured === sequence.current) { setError(errorText(e)); if (!(e instanceof ApiError) || e.unknown) setUncertain(true); }
    } finally { if (alive.current && captured === sequence.current) setBusy(false); }
  }
  async function change(action: 'messages' | 'files' | 'restore' | 'archive', extra: Record<string, unknown>) {
    if (!project || locked || (action === 'messages' && unknown)) return;
    const id = project.id, captured = sequence.current; setBusy(true); setError(''); setNotice('');
    try {
      const data = await api.platform<StudioProject>(route(id) + '/' + action, 'POST', { request_id: requestId(), expected_revision: project.revision, ...extra });
      if (!alive.current || captured !== sequence.current) return;
      accept(data);
      if (action === 'messages') { setQuestion(''); setPollPaused(false); }
      if (action === 'files') { setExplanation(''); setNotice('修改已经保存为新版本。运行后再看看是否符合你的猜想。'); }
      if (action === 'restore') setNotice('已根据选择的版本恢复作品，保留了之前的记录。');
      if (action === 'archive') { setContribution(''); setPrediction(''); setObservation(''); setNotice('当前版本已保存到私人作品集。作品保存不会自动判定课程通过。'); }
    } catch (e) {
      if (!alive.current || captured !== sequence.current) return;
      setError(errorText(e));
      if (!(e instanceof ApiError) || e.unknown) setUncertain(true);
    } finally { if (alive.current && captured === sequence.current) setBusy(false); }
  }
  async function recheck() {
    if (busy) return;
    const captured = sequence.current; setBusy(true); setError('');
    try {
      if (project) {
        const next = await api.platform<StudioProject>(route(project.id));
        if (alive.current && captured === sequence.current) { accept(next, !fileDirty); setUncertain(false); setPollPaused(false); setNotice('已读取保存记录。请对照版本和对话，再决定下一步。'); }
      } else {
        const list = await api.platform<StudioList>(base);
        if (alive.current && captured === sequence.current) { setProjects(list.items); setRuntime(list.runtime); setNotice('已读取作品列表。若刚创建的作品已经出现，请从左侧打开；不会自动重复创建。'); }
      }
    } catch (e) { if (alive.current && captured === sequence.current) setError(errorText(e)); }
    finally { if (alive.current && captured === sequence.current) { setBusy(false); setLoading(false); } }
  }
  const currentFile = project?.files.find(file => file.path === selectedFile) || project?.files[0];
  const draft = currentFile ? drafts[currentFile.path] ?? currentFile.content : '';
  const currentVersion = project?.versions.find(version => version.id === project.current_version_id);
  function showHint(text: string) { setQuestion(text); setTab('chat'); input.current?.focus(); }
  return <section className="scs-studio" aria-label="创作工作台" data-mobile-tab={tab}>
    <header className="scs-header"><div><p className="scs-eyebrow">我的创作空间</p><h1>{project ? project.title : '从一个小想法开始。'}</h1><p>{project ? '说清想法，试着运行，再做一次自己的修改。' : '和松伴一起，把想法做成能点击、能尝试的小作品。'}</p></div><span className="scs-private">私人作品 · 保存后可继续</span></header>
    <div className="scs-status" aria-live="polite">{loading && <p>正在读取你的创作记录…</p>}{error && <p className="scs-error" role="alert">{error}</p>}{notice && <p>{notice}</p>}{(error || uncertain || pollPaused || unknown) && <button className="scs-link" onClick={() => void recheck()} disabled={busy}>核对已保存记录</button>}</div>
    <nav className="scs-mobile-tabs" aria-label="工作区切换"><button aria-pressed={tab === 'chat'} onClick={() => setTab('chat')}>和松伴聊</button><button disabled={!project} aria-pressed={tab === 'preview'} onClick={() => { setTab('preview'); setRightTab('preview'); }}>看我的作品</button><button disabled={!project} aria-pressed={tab === 'code'} onClick={() => { setTab('code'); setRightTab('code'); }}>动手改代码</button></nav>
    <div className="scs-grid">
      <aside className="scs-sidebar" aria-label="作品和文件"><button className="scs-new" disabled={busy || loading} onClick={() => void select(null)}>＋ 新想法</button><h2>我的作品</h2>{!projects.length && !loading && <p className="scs-muted">第一个想法会保存在这里。</p>}<ul className="scs-projects">{projects.map(item => <li key={item.id}><button aria-current={project?.id === item.id ? 'page' : undefined} disabled={busy} onClick={() => void select(item.id)}>{item.title}</button></li>)}</ul>
        {project && <><h2>作品里的文件</h2><ul className="scs-files">{project.files.map(file => <li key={file.path}><button aria-pressed={currentFile?.path === file.path} onClick={() => { setSelectedFile(file.path); setRightTab('code'); setTab('code'); }}>{file.path}<small>{file.path === 'index.html' ? '页面内容' : file.path === 'style.css' ? '颜色和排版' : '点击后的动作'}</small></button></li>)}</ul><div className="scs-goal"><span>这次小目标</span><p>让作品先完成一件你能亲手检查的小事。</p><p className="scs-muted">运行前猜一猜，运行后对照结果。</p></div><details className="scs-history"><summary>以前的版本（{project.versions.length}）</summary>{[...project.versions].sort((a, b) => b.number - a.number).map(version => <div key={version.id}><strong>第 {version.number} 版 · {actorNames[version.actor]}</strong><p>{version.explanation}</p>{version.id === project.current_version_id ? <span>当前版本</span> : <button disabled={locked || fileDirty} onClick={() => void change('restore', { version_id: version.id })}>从第 {version.number} 版恢复</button>}</div>)}</details></>}
      </aside>
      <main className="scs-chat"><div className="scs-companion-title"><span className="scs-avatar" aria-hidden="true">松</span><div><h2>松伴陪你做</h2><p>每次想清楚一小步。</p></div></div>
        {!project ? <form className="scs-start" onSubmit={e => { e.preventDefault(); void create(); }}><h2>你想做一个什么作品？</h2><p>可以先说一句话，比如“我想做一个点击小树就能计分的小游戏”。</p><label htmlFor="scs-idea">我的小想法</label><textarea id="scs-idea" value={idea} onChange={e => setIdea(e.target.value)} maxLength={2000} disabled={busy || uncertain || loading} placeholder="我想做……，让它可以……" required rows={5}/><div className="scs-examples"><button type="button" disabled={busy || uncertain} onClick={() => setIdea('我想做一个点击小树就能计分的小游戏。')}>点击计分小游戏</button><button type="button" disabled={busy || uncertain} onClick={() => setIdea('我想做一张介绍家乡的网页，点击按钮能切换景点。')}>介绍家乡的小网页</button></div><button className="scs-primary" disabled={busy || loading || uncertain || !idea.trim()}>保存想法，开始创作</button><p className="scs-muted">这一步只建立你的作品。AI 修改由你点击发送后才开始。</p></form> : <>
          <div className="scs-dialogue" aria-label="创作对话">{!project.messages.length && <div className="scs-welcome"><p>我们先把“{project.idea}”缩小成能试的一小步。</p><p>告诉松伴：谁会用它，想看到什么，点一下以后发生什么。</p><small>开始指引 · 固定教学提示</small></div>}{project.messages.map(message => <article className={'scs-message scs-message-' + message.role} key={message.id}><strong>{message.role === 'user' ? '我' : '松伴'}</strong><p>{message.text}</p>{message.role === 'assistant' && <small>{message.job_id ? 'AI 协助内容 · 需要运行和核对' : '开始指引 · 固定教学提示'}</small>}</article>)}{project.jobs.length > 0 && <div className="scs-job" role="status">{jobNames[project.jobs[0].state]}{pending && <p>可以等待保存完成；无需反复发送同一句话。</p>}{unknown && <p>这次 AI 结果还待核对，可以继续手工修改和保存；暂不重新发送模型请求。</p>}{project.jobs[0].state === 'failed' && <p>原作品仍然保留，可先查看代码和已保存版本。</p>}</div>}</div>
          <div className="scs-prompts"><button disabled={locked} onClick={() => showHint('先给我一个小提示，让我自己试试。')}>给我一点提示</button><button disabled={locked} onClick={() => showHint('请用简单的话解释当前代码，并问我一个可以通过运行来验证的问题。')}>这段代码做了什么</button><button disabled={locked} onClick={() => showHint('我试了一次，但结果与猜想不同。请先问我看到了什么，再帮我找到原因。')}>和猜的不一样</button></div>
          <form className="scs-composer" onSubmit={e => { e.preventDefault(); if (runtime.available && !fileDirty) void change('messages', { text: question.trim() }); }}><label htmlFor="scs-question">告诉松伴，你想试哪一步</label><textarea ref={input} id="scs-question" value={question} maxLength={4000} rows={3} onChange={e => setQuestion(e.target.value)} disabled={locked} placeholder="例如：按钮每点一次，分数增加 1。我想先试一试。"/><div className="scs-compose-actions"><span>{!runtime.available ? 'AI 编程运行环境暂未就绪；仍可编辑、保存和运行已有代码。' : '松伴按你的想法协助编程，你来运行和判断。'}</span><button className="scs-primary" disabled={locked || unknown || !runtime.available || fileDirty || !question.trim()}>{pending ? '正在处理…' : '发送给松伴'}</button></div>{fileDirty && <p className="scs-muted">先保存你正在改的代码，再让松伴接着修改。</p>}</form>
        </>}
      </main>
      <section className="scs-output" aria-label="作品区"><div className="scs-output-heading"><div className="scs-output-tabs"><button aria-pressed={rightTab === 'preview'} onClick={() => { setRightTab('preview'); setTab('preview'); }}>作品预览</button><button disabled={!project} aria-pressed={rightTab === 'code'} onClick={() => { setRightTab('code'); setTab('code'); }}>代码</button></div>{project && <span>第 {currentVersion?.number || 1} 版</span>}</div>
        {!project ? <div className="scs-empty-preview"><span aria-hidden="true">✦</span><h2>你的作品会出现在这里</h2><p>先保存一个想法，再一起让它动起来。</p></div> : rightTab === 'preview' ? <><div className="scs-runbar"><span>{fileDirty ? '预览显示已保存版本' : '在这里点击和试用'}</span><button disabled={busy || pending} onClick={() => setRun(value => value + 1)}>重新运行</button></div>{preview ? <iframe key={`${preview.version_id}:${run}`} title="我的作品运行预览" sandbox="allow-scripts" referrerPolicy="no-referrer" src={previewDocumentUrl(project.id, preview.version_id)}/> : <div className="scs-preview-wait">{previewError || '正在读取已保存的作品…'}</div>}<p className="scs-preview-note">这是受限的网页预览。运行成功后，还要检查它是否按你的想法工作。</p></> : <div className="scs-editor"><label htmlFor="scs-code">{currentFile?.path || '选择一个文件'}</label><textarea id="scs-code" className="scs-code" spellCheck={false} aria-label={`${currentFile?.path || '文件'}代码`} value={draft} onChange={e => { if (currentFile) setDrafts(values => ({ ...values, [currentFile.path]: e.target.value })); }} disabled={locked || !currentFile}/><label htmlFor="scs-explanation">你改了什么，想试什么？</label><input id="scs-explanation" value={explanation} maxLength={1000} onChange={e => setExplanation(e.target.value)} disabled={locked} placeholder="例如：把每次加 1 分改成加 2 分。"/><button className="scs-primary" disabled={locked || !fileDirty || !explanation.trim()} onClick={() => void change('files', { files: project.files.map(file => ({ path: file.path, content: drafts[file.path] ?? file.content })), explanation: explanation.trim() })}>保存我的修改</button></div>}
        {project && <div className="scs-observe"><h2>试一试，再说说</h2><p>这些是你的学习记录，不是考试。和松伴一起检查真实结果。</p><label htmlFor="scs-predict">运行前：你猜会发生什么？</label><input id="scs-predict" value={prediction} onChange={e => setPrediction(e.target.value)} disabled={locked} maxLength={600} placeholder="点一次按钮，数字会增加……"/><label htmlFor="scs-observed">运行后：实际发生了什么？</label><input id="scs-observed" value={observation} onChange={e => setObservation(e.target.value)} disabled={locked} maxLength={600} placeholder="我点了三次，看到了……"/><label htmlFor="scs-contribution">这次我做的选择或修改</label><textarea id="scs-contribution" value={contribution} onChange={e => setContribution(e.target.value)} disabled={locked} maxLength={1000} rows={2} placeholder="哪些是我决定、修改和验证的？哪些得到过帮助？"/><button className="scs-primary" disabled={locked || fileDirty || !contribution.trim()} onClick={() => void change('archive', { contribution: [prediction.trim() && '运行前的猜想：' + prediction.trim(), observation.trim() && '实际观察：' + observation.trim(), '我的选择与帮助记录：' + contribution.trim()].filter(Boolean).join('\n') })}>保存到我的作品集</button>{project.archive && <p className="scs-saved">{project.archive.version_id === project.current_version_id ? '当前版本已归档到私人作品集。' : '作品集里保存的是较早版本。'}{onOpenPortfolio && <button className="scs-link" onClick={onOpenPortfolio}>查看作品集</button>}</p>}</div>}
      </section>
    </div>
  </section>;
}
