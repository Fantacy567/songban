import type { MountOptions } from './types';
// HTTP error parsing adapted from TeamAssistantPanel; lifecycle guard from ShareSuggestionPreview.
export class ApiError extends Error {
  constructor(message: string, readonly code: string, readonly status: number) { super(message); }
}
export function errorText(error: unknown) {
  return error instanceof Error ? error.message : '连接中断，请核对已保存状态。';
}
export function uncertain(error: unknown) {
  return !(error instanceof ApiError) || error.status >= 500 || error.code === 'invalid_response';
}
export function operationKey() {
  if (typeof globalThis.crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}
export function saved<T>(key: string, fallback: T): T {
  try { return JSON.parse(sessionStorage.getItem(key) || 'null') ?? fallback; } catch { return fallback; }
}
export function save(key: string, value: unknown) {
  try { value === null ? sessionStorage.removeItem(key) : sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* Private mode may disable draft storage. */ }
}
export function dateText(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间待确认' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date);
}
export class WorkbenchApi {
  private controller = new AbortController();
  private denied = false;
  onAccessLost: (() => void) | null = null;
  onContextStale: (() => void) | null = null;
  constructor(private options: MountOptions) {}
  dispose() { this.controller.abort(); }
  get active() { return !this.controller.signal.aborted && !this.denied; }
  async request<T>(path: string, options: { method?: 'GET' | 'POST'; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
    if (!this.active) throw new DOMException('请求已结束', 'AbortError');
    const signals = [this.controller.signal, AbortSignal.timeout(options.method === 'POST' ? 180000 : 20000)];
    if (options.signal) signals.push(options.signal);
    const signal = AbortSignal.any(signals);
    const response = await fetch(path, {
      method: options.method || 'GET', credentials: 'same-origin', cache: 'no-store', signal,
      headers: { Authorization: `Bearer ${this.options.token}`, ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const value = await response.json().catch(() => null);
    if (!this.active || signal.aborted) throw new DOMException('请求已结束', 'AbortError');
    if (!response.ok) {
      const code = value?.error?.code || 'http_error';
      const recoverable = new Set(['source_unavailable', 'share_scope', 'captain_required']);
      if (response.status === 401 || response.status === 403 && !recoverable.has(code)) {
        this.denied = true; this.onAccessLost?.(); this.controller.abort();
        if (response.status === 401) this.options.onUnauthorized();
      }
      if (code === 'source_unavailable') this.onContextStale?.();
      throw new ApiError(value?.error?.message || '暂时无法读取结果，请核对已保存状态。', code, response.status);
    }
    if (!value || typeof value !== 'object') throw new ApiError('未收到有效结果，请核对已保存状态。', 'invalid_response', 502);
    return value as T;
  }
}
