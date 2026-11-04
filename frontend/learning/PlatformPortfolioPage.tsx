import { useCallback, useEffect, useRef, useState } from 'react';
import { PortfolioPage } from '../platform/portfolio';
import type { PortfolioTransport, WorkDetail, WorkList, WorkSummary } from '../platform/portfolio';
import { PlatformImagePanel } from './PlatformImagePanel';
import { errorText } from './api';
import type { LearningApi } from './api';
import type { Consents, Family, Learner, Route, Session } from './types';
import type { Artifact } from './contracts';
import { Notice, useGuard, type SetGuard } from './ui';
import { readPages } from './workspace';
import { creativeRoute, runRoute } from './routes';
import { ExplorationRecords } from './workbench/ExplorationRecords';

interface Props {
  api: LearningApi; session: Session; identityKey: string; navigate: (route: Route) => Promise<boolean>;
  canLeave: () => Promise<boolean>; setGuard: SetGuard; onCurrentWork: (work: WorkDetail | null) => void;
  creativeEnabled?: boolean;
}
export function PlatformPortfolioPage(props: Props) {
  return <PortfolioIdentity key={props.identityKey} {...props} />;
}
function PortfolioIdentity(props: Props) {
  const { api, session, identityKey, navigate, canLeave, setGuard, onCurrentWork } = props;
  const [children, setChildren] = useState<Learner[]>([]), [selected, setSelected] = useState(''), [loading, setLoading] = useState(session.mode === 'manager'), [error, setError] = useState(''), [permitted, setPermitted] = useState(false), [retry, setRetry] = useState(0);
  const alive = useRef(true), generation = useRef(0);
  useEffect(() => {
    alive.current = true;
    if (session.mode !== 'manager') return () => { alive.current = false; };
    const captured = ++generation.current; setLoading(true); setError(''); setChildren([]); setSelected(''); setPermitted(false); onCurrentWork(null);
    void readPages<Family>(api, '/families').then(async families => {
      const result = await Promise.all(families.map(family => api.request<Family>(`/families/${encodeURIComponent(family.id)}`)));
      if (alive.current && captured === generation.current) setChildren(result.flatMap(family => family.learners));
    }).catch(e => { if (alive.current && captured === generation.current) setError(errorText(e)); }).finally(() => { if (alive.current && captured === generation.current) setLoading(false); });
    return () => { alive.current = false; ++generation.current; };
  }, [api, session.mode, session.id, retry, onCurrentWork]);
  useEffect(() => {
    if (session.mode !== 'manager' || !selected) return;
    let active = true; setPermitted(false); setError(''); setLoading(true);
    void api.request<Consents>(`/learners/${encodeURIComponent(selected)}/consents`).then(async first => {
      let all = first, cursor = first.next_cursor; const seen = new Set<string>();
      while (cursor) { if (seen.has(cursor)) throw new Error('Repeated consent cursor'); seen.add(cursor); const page = await api.request<Consents>(`/learners/${encodeURIComponent(selected)}/consents?cursor=${encodeURIComponent(cursor)}`); all = { ...page, items: [...all.items, ...page.items] }; cursor = page.next_cursor; }
      if (all.learner_id !== selected) throw new Error('Scope mismatch');
      const scopes = new Set(all.items.flatMap(consent => consent.effective_scopes));
      if (active) setPermitted(all.relationship_status === 'verified' && scopes.has('learning') && scopes.has('parent_summary'));
    }).catch(e => { if (active) setError(errorText(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, selected, session.mode]);
  if (session.mode === 'learner' && session.learner_id) return <AuthorizedPortfolio {...props} learnerId={session.learner_id} mode="learner" />;
  if (session.mode !== 'manager') return <Notice>请使用本人学习身份或已认证的家庭管理身份查看作品集。</Notice>;
  return <>
    <section className="lp-platform-selection"><p className="lp-eyebrow">家长查看 · 先明确选择孩子</p>{!selected && <h1>查看哪位孩子的私人作品？</h1>}<p>选好孩子后，只会展示已获授权的作品；收录比赛成果需要孩子确认。</p>
      <label htmlFor="lp-portfolio-child">选择当前已授权的孩子</label><select id="lp-portfolio-child" value={selected} disabled={loading} onChange={async e => { const value = e.target.value; if (await canLeave()) { onCurrentWork(null); setPermitted(false); setSelected(value); } }}><option value="">请选择孩子</option>{children.map(child => <option key={child.id} value={child.id} disabled={child.guardian_link.status !== 'verified'}>{child.display_name}{child.guardian_link.status !== 'verified' ? ' · 关系待核对' : ''}</option>)}</select>
      {loading && <Notice>正在核对本人家庭及对应授权…</Notice>}{error && <Notice error>{error}</Notice>}{!loading && !children.length && !error && <Notice>当前账号还没有可选择的家庭学习者。请先到家庭与授权准备，不会自动复制比赛成员。</Notice>}
      {selected && !loading && !permitted && !error && <Notice>这位孩子还缺有效的学习及家长摘要授权。请按已开放的家庭流程准备；不会自动同意。</Notice>}
      {(error || !children.length) && <button onClick={() => setRetry(value => value + 1)}>重新读取本人家庭</button>}
      <button className="lp-secondary" onClick={() => void navigate('#/family')}>查看家庭与授权</button>
    </section>
    {selected && permitted && !loading && !error && <AuthorizedPortfolio key={`${identityKey}:${selected}`} {...props} learnerId={selected} mode="manager" />}
  </>;
}
function AuthorizedPortfolio({ api, session, identityKey, learnerId, mode, navigate, canLeave, setGuard, onCurrentWork, creativeEnabled = false }: Props & { learnerId: string; mode: 'learner' | 'manager' }) {
  const [portfolioDirty, setPortfolioDirty] = useState(false), [imageDirty, setImageDirty] = useState(false), [urls, setUrls] = useState<Record<string, string>>({}), [refreshToken, setRefreshToken] = useState(0);
  const alive = useRef(true), cached = useRef(new Map<string, string>()), fetching = useRef(new Map<string, Promise<void>>());
  useGuard(setGuard, portfolioDirty || imageDirty);
  useEffect(() => { alive.current = true; return () => { alive.current = false; cached.current.forEach(url => URL.revokeObjectURL(url)); cached.current.clear(); fetching.current.clear(); }; }, []);
  const loadAsset = useCallback((id: string): Promise<void> => {
    if (cached.current.has(id)) return Promise.resolve();
    const existing = fetching.current.get(id); if (existing) return existing;
    const task = api.platformBinary(`/assets/${encodeURIComponent(id)}/content`).then(blob => {
      if (!alive.current) return;
      if (!['image/png', 'image/jpeg', 'image/webp'].includes(blob.type) || !blob.size || blob.size > 12582912) throw new Error('Unsupported private image');
      const url = URL.createObjectURL(blob); cached.current.set(id, url); setUrls(Object.fromEntries(cached.current));
    }).finally(() => fetching.current.delete(id));
    fetching.current.set(id, task); return task;
  }, [api]);
  const transport = useCallback<PortfolioTransport>(async <T,>(path: string, method = 'GET', body?: unknown): Promise<T> => {
    const value = await api.platform<T>(path, method, body);
    const possible = value as unknown as WorkList & Partial<WorkSummary>;
    const works = Array.isArray(possible.items) ? possible.items : possible.cover_asset_id !== undefined ? [possible as WorkSummary] : [];
    works.forEach(work => { if (work.cover_asset_id && work.learner_id === learnerId) void loadAsset(work.cover_asset_id).catch(() => {}); });
    return value;
  }, [api, learnerId, loadAsset]);
  const assetUrl = useCallback((id: string) => urls[id] || null, [urls]);
  const imagesChanged = useCallback(() => setRefreshToken(value => value + 1), []);
  async function openLearning(runId?: string, artifactId?: string) {
    if (mode !== 'learner') return navigate('#/family');
    if (runId) return navigate(runRoute(runId));
    if (artifactId) { const artifact = await api.request<Artifact>(`/artifacts/${encodeURIComponent(artifactId)}`); if (artifact.learner_id !== learnerId) throw new Error('Scope mismatch'); return navigate(runRoute(artifact.run_id)); }
    return navigate('#/learn/first');
  }
  async function openCompetition() {
    if (session.mode === 'learner') return navigate('#/hackathon');
    if (await canLeave()) location.assign('/#/work');
  }
  return <>{mode === 'learner' && <ExplorationRecords api={api} navigate={navigate}/>}<PortfolioPage transport={transport} learnerId={learnerId} mode={mode} identityKey={`${identityKey}:${learnerId}`} onOpenLearning={openLearning} onOpenCompetition={openCompetition} onOpenStudio={creativeEnabled && mode === 'learner' ? id => navigate(creativeRoute(id)) : undefined} onDirty={setPortfolioDirty} onCurrentWork={onCurrentWork} getAssetUrl={assetUrl} refreshToken={refreshToken} beforeTransition={imageDirty ? canLeave : undefined}
    renderImageTools={work => work.available_actions.includes('open_studio') ? null : <PlatformImagePanel api={api} work={work} identityKey={identityKey} onDirty={setImageDirty} onImagesChanged={imagesChanged} assetUrl={assetUrl} loadAsset={loadAsset} />} /></>;
}
