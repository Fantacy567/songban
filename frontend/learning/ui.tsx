import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { LearningApi } from './api';
import { ApiError, errorText, requestId } from './api';

export interface LeaveGuard { dirty: boolean; save?: () => Promise<boolean> }
export type SetGuard = (guard: LeaveGuard) => void;
export function useGuard(setGuard: SetGuard, dirty: boolean, save?: () => Promise<boolean>) {
  useEffect(() => { setGuard({ dirty, save }); return () => setGuard({ dirty: false }); }, [setGuard, dirty, save]);
}
export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className={`lp-notice${error ? ' lp-error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>;
}
export function Dialog({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => { ref.current?.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="lp-dialog" aria-labelledby="lp-dialog-title" onCancel={e => { e.preventDefault(); close(); }} onKeyDown={e => {
    if (e.key !== 'Tab') return;
    const nodes = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex="0"]') || []).filter(n => n.getClientRects().length);
    const first = nodes[0], last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }}>
    <h2 id="lp-dialog-title">{title}</h2>{children}
  </dialog>;
}
export function useMutation(api: LearningApi, reload: () => Promise<void>) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [pending, setPending] = useState<{ path: string; method: string; body: Record<string, unknown> } | null>(null);
  const alive = useRef(true), lock = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function perform(job: NonNullable<typeof pending>): Promise<boolean> {
    if (lock.current) return false;
    lock.current = true; setBusy(true); setError('');
    try {
      await api.request(job.path, job.method, job.body);
      if (!alive.current) return false;
      setPending(null); await reload(); return true;
    } catch (e) {
      if (alive.current) { setError(errorText(e)); if (e instanceof ApiError && e.unknown) setPending(job); }
      return false;
    } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  return { busy, error, pending,
    run: (path: string, body: Record<string, unknown>, method = 'POST') => perform({ path, method, body: { request_id: requestId(), ...body } }),
    retry: async () => { if (pending) { await reload(); return perform(pending); } return false; } };
}
