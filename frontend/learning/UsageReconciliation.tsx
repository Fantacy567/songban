import { useCallback, useEffect, useRef, useState } from 'react';
import type { LearningApi } from './api';
import type { Reconciliation, ResolveReconciliation } from './contracts';
import { Notice } from './ui';
import { encode, lessonError, MutationNotice, readPages, useLessonMutation } from './workspace';

export function UsageReconciliation({ api, onDirty }: { api: LearningApi; onDirty: (dirty: boolean) => void }) {
  const [cases, setCases] = useState<Reconciliation[]>([]), [selected, setSelected] = useState(''), [error, setError] = useState('');
  const [resolution, setResolution] = useState<ResolveReconciliation['resolution']>('confirmed_no_charge');
  const [evidence, setEvidence] = useState(''), [units, setUnits] = useState(''), [reason, setReason] = useState('');
  const alive = useRef(true), seq = useRef(0);
  const load = useCallback(async () => {
    const generation = ++seq.current;
    try { const rows = await readPages<Reconciliation>(api, '/reconciliation-cases'); if (alive.current && generation === seq.current) { setCases(rows); setError(''); } }
    catch (e) { if (alive.current && generation === seq.current) { setError(lessonError(e)); setCases([]); } throw e; }
  }, [api]);
  const m = useLessonMutation(api, load), current = cases.find(c => c.id === selected);
  const dirty = !!evidence || !!units || !!reason || m.busy || !!m.pending;
  useEffect(() => { alive.current = true; void load().catch(() => {}); return () => { alive.current = false; ++seq.current; onDirty(false); }; }, [load, onDirty]);
  useEffect(() => onDirty(dirty), [onDirty, dirty]);
  const ids = evidence.split(/[\s,，]+/).filter(Boolean);
  const validUnits = resolution === 'confirmed_no_charge' || /^\d+$/.test(units) && Number.isSafeInteger(Number(units));
  return <section className="lp-card" aria-label="模型用量核对"><h2>模型用量核对</h2><p>这里只显示分配给你的运行核对。结果未知时保留预占，不自动重试。</p>
    {error && <Notice error>{error}</Notice>}<MutationNotice mutation={m} /><button disabled={m.busy} onClick={() => void load().catch(() => {})}>重新读取用量核对</button>
    {!error && !cases.length && <p>当前没有分配给你的用量核对。</p>}
    <div className="lp-actions">{cases.map(c => <button key={c.id} disabled={dirty || m.locked} onClick={() => setSelected(c.id)}>{c.status === 'resolved' ? '已核对' : c.status === 'escalated' ? '已升级' : '待核对'} · {c.id.slice(-6)}</button>)}</div>
    {current && <><h3>本次核对记录</h3><p>负责人：{current.owner_display_name}；期限：{new Date(current.due_at).toLocaleString('zh-CN')}</p><p>核对编号：{current.id}</p><p>{current.usage.notice}</p><p>真实费用：{current.usage.cost_estimate === null ? '尚未核实金额' : current.usage.cost_estimate}</p>
      {current.status !== 'resolved' && <><p>先由受控核查流程录入供应商响应或账单依据。这里填写已有依据编号，不能靠任意文字确认未计费。</p>
        <label>核对结论<select aria-label="核对结论" value={resolution} onChange={e => setResolution(e.target.value as ResolveReconciliation['resolution'])}><option value="confirmed_no_charge">有依据确认未计费</option><option value="accepted_result">有依据确认结果和用量</option><option value="confirmed_charge_no_output">确认产生用量，但没有可用结果</option></select></label>
        <label>已录入的依据编号<textarea aria-label="已录入的依据编号" value={evidence} onChange={e => setEvidence(e.target.value)} maxLength={1000} /></label>
        {resolution !== 'confirmed_no_charge' && <label>核实的计量单位<input aria-label="核实的计量单位" inputMode="numeric" value={units} onChange={e => setUnits(e.target.value)} /></label>}
        <label>核对说明<textarea aria-label="核对说明" value={reason} onChange={e => setReason(e.target.value)} maxLength={8000} /></label>
        <button disabled={m.locked || !ids.length || !reason.trim() || !validUnits} onClick={() => void m.run(`/reconciliation-cases/${encode(current.id)}/resolve`, { expected_revision: current.revision, resolution, evidence_ids: ids, settled_units: resolution === 'confirmed_no_charge' ? 0 : Number(units), adjustment_units: null, reason }, () => { setEvidence(''); setUnits(''); setReason(''); })}>保存本次核对结论</button></>}
    </>}
  </section>;
}
