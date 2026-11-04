import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, errorText, requestId } from './api';
import type { LearningApi } from './api';
import type { WorkDetail } from '../platform/portfolio/types';
import { Notice } from './ui';

export interface PlatformImageConfig { enabled: boolean; images_available: boolean; image_modes: { sample: boolean; live: boolean }; notice: string }
type ImageState = 'queued' | 'dispatching' | 'unknown' | 'received' | 'stored' | 'storage_failed' | 'archived' | 'archive_conflict' | 'failed' | 'cancelled';
export interface PlatformImageJob {
  id: string; revision: number; mode: 'sample' | 'live'; source: 'local_sample' | 'doubao' | 'test_fixture' | null;
  purpose: 'work_cover' | 'illustration' | 'course_cover'; learner_id: string | null; target_id: string; target_version: string; slot: string;
  state: ImageState; asset_id: string | null; binding_revision: number | null; actual_model: string | null;
  error_code: string | null; can_recover: boolean; usage: { unit: 'images'; reserved: number; settled: number; status: 'sample' | 'held' | 'settled' | 'released'; notice: string };
  created_at: string; updated_at: string;
}
interface ImageBinding { purpose: 'work_cover' | 'illustration' | 'course_cover'; slot: string; binding_revision: number; target_version: string; asset_id: string; mode: 'sample' | 'live'; source: 'local_sample' | 'doubao' | 'test_fixture'; created_at: string }
interface WorkImages { target_id: string; target_version: string; cover_asset_id: string | null; items: ImageBinding[] }
interface Pending { path: string; body: Record<string, unknown>; kind: 'create' | 'recover' }
const states: Record<ImageState, string> = { queued: '已排队，正在等待处理', dispatching: '正在等待图片服务', unknown: '结果还未确认，请核对原任务', received: '已收到图片，准备保存', stored: '图片已存储，正在关联作品', storage_failed: '图片已收到，保存还需恢复', archived: '已自动保存到这件作品', archive_conflict: '图片已保留，作品版本已变化', failed: '这次没有生成可用图片', cancelled: '这次图片任务已取消' };
const polling = new Set<ImageState>(['queued', 'dispatching', 'received', 'stored']);
const unresolved = new Set<ImageState>(['queued', 'dispatching', 'unknown', 'received', 'stored', 'storage_failed', 'archive_conflict']);
function PrivateImage({ url, label }: { url: string | null; label: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return url && !failed ? <img src={url} alt={label} onError={() => setFailed(true)} /> : <p>图片暂未读到，保存记录仍保留。</p>;
}
export function PlatformImagePanel({ api, work, identityKey, onDirty, onImagesChanged, assetUrl, loadAsset }: {
  api: LearningApi; work: WorkDetail; identityKey: string; onDirty: (dirty: boolean) => void; onImagesChanged: () => void;
  assetUrl: (id: string) => string | null; loadAsset: (id: string) => Promise<void>;
}) {
  return <ImagePanel key={`${identityKey}:${work.id}:${work.current_version.id}`} api={api} work={work} onDirty={onDirty} onImagesChanged={onImagesChanged} assetUrl={assetUrl} loadAsset={loadAsset} />;
}
function ImagePanel({ api, work, onDirty, onImagesChanged, assetUrl, loadAsset }: Omit<Parameters<typeof PlatformImagePanel>[0], 'identityKey'>) {
  const alive = useRef(true), generation = useRef(0), lock = useRef(false), notified = useRef('');
  const callbacks = useRef({ onDirty, onImagesChanged }); callbacks.current = { onDirty, onImagesChanged };
  const [config, setConfig] = useState<PlatformImageConfig | null>(null), [images, setImages] = useState<WorkImages | null>(null), [jobs, setJobs] = useState<PlatformImageJob[]>([]), [job, setJob] = useState<PlatformImageJob | null>(null);
  const [prompt, setPrompt] = useState(''), [purpose, setPurpose] = useState<'work_cover' | 'illustration'>('work_cover'), [mode, setMode] = useState<'sample' | 'live'>('sample');
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [pending, setPending] = useState<Pending | null>(null), [waitingReceipt, setWaitingReceipt] = useState(false);
  const [pollNotice, setPollNotice] = useState('');
  const base = `/learners/${encodeURIComponent(work.learner_id)}/works/${encodeURIComponent(work.id)}`;
  function validateJob(value: PlatformImageJob) { if (value.target_id !== work.id || value.learner_id !== work.learner_id) throw new ApiError(403, 'scope_mismatch', '图片归属需要重新核对'); return value; }
  const read = useCallback(async () => {
    const current = ++generation.current; setLoading(true); setError('');
    const result = await Promise.allSettled([api.platform<PlatformImageConfig>('/config'), api.platform<WorkImages>(`${base}/images`), api.platform<{ items: PlatformImageJob[] }>(`${base}/image-jobs`)]);
    if (!alive.current || current !== generation.current) return;
    if (result[0].status === 'fulfilled') { setConfig(result[0].value); setMode(value => result[0].status === 'fulfilled' && result[0].value.image_modes[value] ? value : result[0].status === 'fulfilled' && result[0].value.image_modes.sample ? 'sample' : 'live'); }
    else { setConfig(null); setError(errorText(result[0].reason)); }
    if (result[1].status === 'fulfilled' && result[1].value.target_id === work.id && result[1].value.target_version === work.current_version.id) {
      setImages(result[1].value); result[1].value.items.forEach(item => { void loadAsset(item.asset_id).catch(() => {}); });
    } else { setImages(null); setError('当前作品的图片与版本尚未核对完整。请重新读取，不会自动生成。'); }
    if (result[2].status === 'fulfilled') {
      try {
        const values = result[2].value.items.map(validateJob); setJobs(values);
        const currentJobs = values.filter(value => value.target_version === work.current_version.id);
        setJob(currentJobs.find(value => unresolved.has(value.state)) || currentJobs[0] || null);
      } catch { setJobs([]); setJob(null); setError('图片任务归属需要重新核对。'); }
    } else { setJobs([]); setJob(null); setError('图片任务还没读完整，暂不发起新生成。可以重新读取原记录。'); }
    setLoading(false);
  }, [api, base, work.id, work.learner_id, work.current_version.id, loadAsset]);
  useEffect(() => { alive.current = true; void read(); return () => { alive.current = false; ++generation.current; callbacks.current.onDirty(false); }; }, [read]);
  const dirty = !!prompt || busy || !!pending || !!job && unresolved.has(job.state);
  useEffect(() => { callbacks.current.onDirty(dirty); }, [dirty]);
  useEffect(() => {
    if (!job?.asset_id) return;
    void loadAsset(job.asset_id).catch(() => {});
    if (job.state === 'archived') {
      const key = `${job.id}:${job.binding_revision}`;
      if (notified.current !== key) { notified.current = key; if (!images?.items.some(item => item.asset_id === job.asset_id)) void read(); callbacks.current.onImagesChanged(); }
    }
  }, [job?.asset_id, job?.state, job?.id, job?.binding_revision, loadAsset]);
  useEffect(() => {
    if (!job || !polling.has(job.state)) return;
    let cancelled = false, reads = 0; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = validateJob(await api.platform<PlatformImageJob>(`/image-jobs/${encodeURIComponent(job!.id)}`));
        if (cancelled || !alive.current) return;
        setJob(value);
        if (polling.has(value.state) && ++reads < 20) timer = setTimeout(poll, 1500);
        else if (polling.has(value.state)) setPollNotice('图片还在处理中，可以稍后核对原任务。没有重新生成。');
      } catch { if (!cancelled && alive.current) setPollNotice('暂时读不到原图片任务，可以点击重新读取。没有重新生成。'); }
    }
    timer = setTimeout(poll, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [api, job?.id, job?.state]);
  async function perform(value: Pending) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setPending(value); setWaitingReceipt(false); setError(''); setPollNotice('');
    try {
      const result = validateJob(await api.platform<PlatformImageJob>(value.path, 'POST', value.body));
      if (!alive.current) return;
      setJob(result); setJobs(old => [result, ...old.filter(item => item.id !== result.id)]); setPending(null); setPrompt('');
      if (result.state === 'archived') await read();
    } catch (e) {
      if (!alive.current) return;
      setError(errorText(e));
      if (e instanceof ApiError && !e.unknown) { setPending(null); if (e.status === 409) { await read(); callbacks.current.onImagesChanged(); } }
      else setWaitingReceipt(true);
    } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!images || !config?.image_modes[mode] || !prompt.trim() || pending || busy || loading || error || !!job && unresolved.has(job.state)) return;
    const slot = purpose === 'work_cover' ? 'cover' : 'illustration-main';
    void perform({ kind: 'create', path: '/image-jobs', body: { request_id: requestId(), mode, purpose, learner_id: work.learner_id, target_id: work.id, target_version: work.current_version.id, expected_binding_revision: images.items.find(item => item.slot === slot)?.binding_revision || 0, slot, prompt: prompt.trim() } });
  }
  const locked = loading || busy || !!pending || !!error || !!job && unresolved.has(job.state);
  const current = images?.items.filter(item => item.target_version === work.current_version.id) || [];
  const previous = images?.items.filter(item => item.target_version !== work.current_version.id) || [];
  function picture(item: ImageBinding) { return <figure key={item.asset_id}><PrivateImage url={assetUrl(item.asset_id)} label={`${item.purpose === 'work_cover' ? '作品封面' : '作品插图'} · ${item.mode === 'sample' ? '本地固定样例，不是真实AI生成' : 'AI生成配图，不是运行截图'}`} /><figcaption>{item.mode === 'sample' ? '本地固定样例 · 未调用图片模型' : item.source === 'test_fixture' ? '隔离测试图片' : 'AI生成配图'} · {item.purpose === 'work_cover' ? '封面' : '插图'} · 关联版本 {item.target_version === work.current_version.id ? `当前 v${work.current_version.number}` : '旧作品版本'}。配图不是作品已通过检查的证明。</figcaption></figure>; }
  return <section className="lp-image-panel" aria-labelledby="lp-image-title"><h2 id="lp-image-title">给这件作品配一张图</h2><p>明确点击后才处理图片。成功后自动保存到这件私人作品；不会代替你公开、交作业或通过检查。</p>
    {loading && <Notice>正在读取图片配置、已保存图片和原任务…</Notice>}{error && <Notice error>{error}</Notice>}
    {!loading && config && !config.images_available && <Notice>图片服务尚未配置或未开放。已保存的图片仍可查看；不会用文字回复冒充出图。</Notice>}
    {job && <div className="lp-image-state" role="status"><strong>{states[job.state]}</strong><p>{job.mode === 'sample' ? '本地固定样例，不是真实AI生成，也没有调用图片模型。' : job.source === 'test_fixture' ? '隔离测试结果。' : '真实图片请求，按服务端保存与用量回执显示。'}</p>{job.actual_model && <p>实际模型：{job.actual_model}</p>}<p>{job.usage.notice}</p>{job.state === 'archive_conflict' && <p>已有图片没有丢弃。请先读取作品当前版本；不要直接再生成一张。</p>}{job.can_recover && <button disabled={busy || !!pending} onClick={() => void perform({ kind: 'recover', path: `/image-jobs/${encodeURIComponent(job.id)}/recover-storage`, body: { request_id: requestId() } })}>恢复保存原图片</button>}</div>}
    {pollNotice && <Notice>{pollNotice}</Notice>}{waitingReceipt && pending && <><Notice>原请求结果尚未确认。保留原内容与编号；核对时不会建立新的图片请求。</Notice><button className="lp-primary" disabled={busy} onClick={() => void perform(pending)}>核对原图片请求</button></>}
    <form onSubmit={submit}><fieldset disabled={locked || !config?.images_available}><label htmlFor="lp-image-purpose">图片放在哪里？</label><select id="lp-image-purpose" value={purpose} onChange={e => setPurpose(e.target.value as typeof purpose)}><option value="work_cover">这件作品的封面</option><option value="illustration">这件作品的一张插图</option></select><label htmlFor="lp-image-prompt">希望图片表达什么？</label><textarea id="lp-image-prompt" value={prompt} maxLength={1000} required onChange={e => setPrompt(e.target.value)} placeholder="例如：几位伙伴一起节约校园用水，画面友善，不出现真实姓名。" />
      <label htmlFor="lp-image-mode">这次使用哪种图片？</label><select id="lp-image-mode" value={mode} onChange={e => setMode(e.target.value as typeof mode)}>{config?.image_modes.sample && <option value="sample">本地固定样例（不是AI生成）</option>}{config?.image_modes.live && <option value="live">使用已配置的真实图片模型</option>}{!config?.images_available && <option value="sample">尚未配置</option>}</select><div className="lp-actions"><button className="lp-primary" type="submit" disabled={locked || !config?.image_modes[mode] || !prompt.trim()}>{mode === 'sample' ? '保存本地样例配图' : '生成并自动保存图片'}</button></div></fieldset></form>
    <button disabled={loading || busy} onClick={() => void read()}>重新读取图片与原任务</button>
    {!!current.length && <div className="lp-image-gallery">{current.map(picture)}</div>}{!!previous.length && <details className="lp-image-history"><summary>查看旧作品版本的配图（{previous.length}）</summary><p>这些图片保留在旧版本下，没有自动作为当前版本封面。</p><div className="lp-image-gallery">{previous.map(picture)}</div></details>}
    {jobs.length > 1 && <details className="lp-image-history"><summary>查看这件作品最近的图片任务</summary><ul>{jobs.map(item => <li key={item.id}>{item.mode === 'sample' ? '本地样例' : '真实图片'} · {states[item.state]} · {item.target_version === work.current_version.id ? '当前作品版本' : '旧作品版本'}</li>)}</ul></details>}
  </section>;
}
