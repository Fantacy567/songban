import type { Bootstrap, Config, MountOptions, Session } from './types';

const BASE = '/api/learning/v2';
const key = (s: Session | null) => s ? `${s.id}:${s.mode_epoch}:${s.mode}:${s.actor_id}:${s.learner_id}` : '';
export const requestId = () => crypto.randomUUID();
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
  get unknown() { return this.status === 0 || this.status >= 500; }
}
export const errorText = (e: unknown) => e instanceof ApiError
  ? e.status === 409 && e.code === 'revision_conflict' ? '另一处保存了新内容，请先核对最新内容。你的输入仍在这里。'
    : e.code === 'idempotency_conflict' ? '这次操作的编号与原内容不一致。请先核对记录，不要直接覆盖。'
    : e.code === 'family_exists' ? '本人家庭已经存在，正在读取已有档案。'
    : e.status === 409 ? '当前状态不允许这次操作，请重新核对记录。'
    : e.unknown ? '还没确认这次操作的结果，请先核对。你的输入仍在这里。'
    : e.status === 403 ? '当前身份或授权不允许这个操作，请核对关系与授权状态。'
    : e.status === 423 ? '学习入口暂未开放，可以保留已保存记录。'
    : e.status === 429 ? '操作稍频繁，请稍后再试。'
    : e.status === 422 ? '这些内容还不能保存，请检查选择和填写内容。'
    : '暂时没读到最新记录，请重新读取。'
  : '暂时没读到最新记录，请重新读取。';

export interface IdentityState { phase: 'loading' | 'ready' | 'checking' | 'error'; session: Session | null; config: Config | null; boundary: number; notice: string }
/** No Bearer, storage identity, cookie refresh, or automatic mutation replay. */
export class LearningApi {
  private state: IdentityState = { phase: 'loading', session: null, config: null, boundary: 0, notice: '' };
  private listeners = new Set<() => void>();
  private controllers = new Set<AbortController>();
  private generation = 0;
  private disposed = false;
  private boot: Bootstrap | null = null;
  private channel: BroadcastChannel | null = null;
  private checking: Promise<void> | null = null;
  private transition = false;
  constructor(private options: MountOptions) {
    if (typeof BroadcastChannel !== 'undefined') {
      this.channel = new BroadcastChannel('songban-learning-identity');
      this.channel.onmessage = () => { void this.revalidate(); };
    }
    window.addEventListener('pageshow', this.onPageShow);
    document.addEventListener('visibilitychange', this.onVisibility);
  }
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  snapshot = () => this.state;
  private publish(patch: Partial<IdentityState>) { if (this.disposed) return; this.state = { ...this.state, ...patch }; this.listeners.forEach(fn => fn()); }
  private cancel() { ++this.generation; this.controllers.forEach(c => c.abort()); this.controllers.clear(); }
  private boundary(reason: string) {
    this.cancel(); this.boot = null;
    this.publish({ session: null, boundary: this.state.boundary + 1, notice: reason });
    this.options.onIdentityBoundary?.(reason); this.options.onSessionChange?.(null);
  }
  private onPageShow = () => { void this.revalidate(); };
  private onVisibility = () => { if (document.visibilityState === 'visible') void this.revalidate(); };
  private async raw<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const captured = this.generation;
    const c = new AbortController(); this.controllers.add(c);
    const timeout = window.setTimeout(() => c.abort(), 20000);
    try {
      const response = await fetch(BASE + path, { method, credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: c.signal,
        headers: { Accept: 'application/json', ...(method !== 'GET' ? { 'Content-Type': 'application/json', 'X-CSRF-Token': this.boot?.csrf_token || '' } : {}) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      const result = await response.json();
      if (this.disposed || captured !== this.generation) throw new ApiError(0, 'stale', '身份已变化');
      if (!response.ok) throw new ApiError(response.status, result?.error?.code || 'request_failed', '请求未成功');
      return result as T;
    } catch (e) {
      if (this.disposed || captured !== this.generation) throw new ApiError(0, 'stale', '身份已变化');
      throw e instanceof ApiError ? e : new ApiError(0, 'network_unknown', '结果未确认');
    } finally { window.clearTimeout(timeout); this.controllers.delete(c); }
  }
  private async readSession() {
    try { return await this.raw<Session>('/session'); }
    catch (e) { if (e instanceof ApiError && e.status === 401) return null; throw e; }
  }
  private adopt(session: Session | null) {
    if (key(session) !== key(this.state.session)) {
      this.boundary('身份已更新，正在恢复当前身份的记录。');
      this.publish({ session }); this.options.onSessionChange?.(session);
    } else this.publish({ session });
  }
  revalidate = (): Promise<void> => {
    if (this.disposed || this.transition) return Promise.resolve();
    if (this.checking) return this.checking;
    this.cancel(); this.publish({ phase: 'checking' });
    this.checking = (async () => {
      try {
        const session = await this.readSession(); this.adopt(session);
        // Bootstrap is fetched after each identity change, never reused across epochs.
        this.boot = await this.raw<Bootstrap>('/session-bootstrap');
        const config = await this.raw<Config>('/config');
        this.publish({ phase: 'ready', config });
      } catch (e) { if (!this.disposed) { this.boundary('身份暂时无法确认，未保存内容已清除。'); this.publish({ phase: 'error' }); } }
      finally { this.checking = null; }
    })();
    return this.checking;
  };
  async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    if (this.state.phase !== 'ready' || !this.state.session || !this.boot) throw new ApiError(401, 'session_unconfirmed', '请重新确认身份');
    const captured = this.generation, identity = key(this.state.session);
    try {
      const value = await this.raw<T>(path, method, body);
      // Server is authoritative even if another tab has no BroadcastChannel support.
      const current = await this.readSession();
      if (captured !== this.generation) throw new ApiError(0, 'stale', '身份已变化');
      if (identity !== key(current)) { this.adopt(current); void this.revalidate(); throw new ApiError(0, 'stale', '身份已变化'); }
      return value;
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.code === 'child_mode_restricted' || e.code === 'consent_required')) {
        this.boundary('学习身份需要重新确认，请家长帮忙。'); void this.revalidate();
      }
      throw e;
    }
  }
  async consentText(version: string) {
    const { verifyConsentText } = await import('./consent');
    const text = await this.request<import('./types').ConsentText>(`/consent-texts/${encodeURIComponent(version)}`);
    await verifyConsentText(text, version); return text;
  }
  async changeIdentity(kind: 'authenticate' | 'enter-learner' | 'logout', fields: Record<string, unknown>) {
    if (this.transition) return;
    // Capture the current revision before hiding and cancelling all private views.
    const session = this.state.session;
    this.transition = true; this.boundary('正在核对身份，管理与学习内容已收起。'); this.publish({ phase: 'checking' });
    let failure: unknown;
    try {
      this.boot = await this.raw<Bootstrap>('/session-bootstrap');
      const body = kind === 'authenticate'
        ? { request_id: requestId(), browser_revision: this.boot.browser_revision, method: 'password', ...fields }
        : { request_id: requestId(), expected_revision: session?.revision, ...fields };
      await this.raw(`/sessions/${kind}`, 'POST', body);
    } catch (e) { failure = e; }
    finally {
      this.transition = false; this.channel?.postMessage({ type: 'identity-changed' });
      await this.revalidate();
    }
    if (failure) throw failure;
  }
  dispose() {
    this.disposed = true; this.cancel(); this.boot = null;
    this.state = { ...this.state, session: null, config: null };
    this.channel?.close(); this.listeners.clear();
    window.removeEventListener('pageshow', this.onPageShow); document.removeEventListener('visibilitychange', this.onVisibility);
  }
}
