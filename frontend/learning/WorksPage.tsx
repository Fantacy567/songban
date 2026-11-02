import { useCallback, useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Artifact, VersionRead } from './contracts';
import type { Route } from './types';
import { Notice, useGuard, type SetGuard } from './ui';
import { encode, lessonError, MutationNotice, Preview, readPages, useLessonMutation } from './workspace';
import { runRoute } from './routes';
export function WorksPage({ api, learnerId, id, version, navigate, setGuard }: { api: LearningApi; learnerId: string; id: string | null; version: string | null; navigate: (r: Route) => Promise<boolean>; setGuard: SetGuard }) {
  const [items, setItems] = useState<Artifact[]>([]), [opened, setOpened] = useState<VersionRead | null>(null), [error, setError] = useState(''), [confirmed, setConfirmed] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<string | null>(null);
  const alive = useRef(true), generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current; setOpened(null); setConfirmed(false); setCurrentVersion(null);
    try {
      const records = await readPages<Artifact>(api, `/learners/${encode(learnerId)}/artifacts`);
      if (!alive.current || current !== generation.current) return;
      setItems(records); setError('');
      if (id) {
        const artifact = await api.request<Artifact>(`/artifacts/${encode(id)}`);
        if (artifact.learner_id !== learnerId) throw new Error('Scope mismatch');
        const result = await api.request<VersionRead>(`/artifacts/${encode(id)}/versions/${encode(version || artifact.current_version.id)}`);
        if (result.artifact_version.artifact_id !== id) throw new Error('Scope mismatch');
        if (alive.current && current === generation.current) { setOpened(result); setCurrentVersion(artifact.current_version.id); }
      }
    } catch (e) { if (alive.current && current === generation.current) setError(lessonError(e)); throw e; }
  }, [api, id, learnerId, version]);
  useEffect(() => { alive.current = true; void load().catch(() => {}); return () => { alive.current = false; ++generation.current; }; }, [load]);
  const m = useLessonMutation(api, async () => {});
  useGuard(setGuard, m.busy || !!m.pending);
  return <section className="lp-card"><h2>已保存的作品</h2><p>作品保存和关卡完成是两件事。这里只展示本人的固定文本版本。</p>{error && <><Notice error>{error}</Notice><button onClick={() => void load().catch(() => {})}>重新读取作品</button></>}<MutationNotice mutation={m} />
    {opened && <><Preview content={opened.artifact_version.content} label={`已打开 v${opened.artifact_version.version}`} /><p>来源：{opened.artifact_version.authorship === 'ai_candidate_unedited' ? '工具候选原样保存' : '已记录编辑与帮助'}。生成模式与检查状态请回到本课查看。</p>{currentVersion !== opened.artifact_version.id ? <Notice>这是历史版本，可以查看；回到这节课打开当前版本后再确认。</Notice> : confirmed ? <Notice>已记录你打开并确认了这一版本；这不表示理解已经通过检查。</Notice> : <button className="lp-primary" disabled={m.locked} onClick={() => void m.run(`/artifacts/${encode(opened.artifact_version.artifact_id)}/readbacks`, { expected_revision: opened.artifact_revision, read_receipt_id: opened.read_receipt_id }, () => setConfirmed(true))}>我已打开并看过这一版</button>}</>}
    {!items.length && !error && <p>还没有已保存作品，回到学习首页继续练习。</p>}{items.map(item => <article className="lp-record" key={item.id}><h3>{item.current_version.content.title}</h3><p>已保存 v{item.current_version.version} · {item.check_status === 'passed' ? '服务记录：已完成检查' : item.check_status === 'pending_review' ? '等待老师' : item.check_status === 'needs_practice' ? '需要补练' : '还需要检查'}</p><div className="lp-actions"><button onClick={() => void navigate(`#/learn/works?id=${encode(item.id)}&version=${encode(item.current_version.id)}`)}>打开已保存的作品</button><button onClick={() => void navigate(runRoute(item.run_id))}>返回这节课</button></div></article>)}
  </section>;
}
