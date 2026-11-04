// Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
/** A separately authenticated HTML response owns the preview CSP. srcdoc would
 * inherit the parent application's script-src self and disable project scripts.
 * Never put bearer credentials in this URL; the server checks its session cookie. */
export function previewDocumentUrl(projectId: string, versionId: string): string {
  if (![projectId, versionId].every(value => /^[A-Za-z0-9_.:@-]{1,150}$/.test(value))) throw new Error('Invalid preview identifier');
  return `/api/platform/v1/studio/projects/${encodeURIComponent(projectId)}/preview/${encodeURIComponent(versionId)}/document`;
}
