/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md. */
import { useEffect, useState } from 'react';
import { errorText, type LearningApi } from '../api';
import { courseRoute } from '../routes';
import type { Route } from '../types';
import { Notice } from '../ui';
import { workbenchPath, type ExplorationRecord } from './types';

export function ExplorationRecords({ api, navigate }: { api: LearningApi; navigate: (r: Route) => Promise<boolean> }) {
  const [records, setRecords] = useState<ExplorationRecord[]>([]), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true; setLoading(true); setError('');
    void api.platform<{ items: ExplorationRecord[] }>(`${workbenchPath}/records`).then(data => {
      if (active) setRecords(data.items.filter(r => r.status === 'confirmed'));
    }).catch(e => { if (active) setError(errorText(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, retry]);
  return <section className="wb-records" aria-label="我的探索记录"><h2>我的探索记录</h2><p>这里是你亲自确认的尝试和想法。确认只保存到自己的作品集。</p>
    {loading && <Notice>正在读取探索记录…</Notice>}{error && <><Notice error>{error}</Notice><button onClick={() => setRetry(n => n + 1)}>重新读取探索记录</button></>}
    {!loading && !error && !records.length && <p>和课程老师聊一聊，把想留下的经历编辑确认后，就会出现在这里。</p>}
    <div className="wb-record-grid">{records.map(record => <article className="lp-card" key={record.id}><span className="lp-eyebrow">已确认 · {record.method === 'evidence' ? '根据已有记录整理' : '模型协助整理'}</span><h3>{record.title}</h3><p className="wb-text">{record.summary}</p>{record.next_step && <p>下次想试：{record.next_step}</p>}<button onClick={() => void navigate(courseRoute(record.course_id))}>继续这次探索</button></article>)}</div>
  </section>;
}
