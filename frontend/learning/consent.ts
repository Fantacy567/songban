import type { ConsentText } from './types';
import { ApiError } from './api';
export async function verifyConsentText(t: ConsentText, version: string) {
  // JSON object member order is not preserved by storage/transport. Reconstruct
  // every hashed object in the frozen contract's order, preserving array order.
  const canonical = JSON.stringify({ locale: t.locale, title: t.title, text: t.text,
    scope_purposes: t.scope_purposes.map(p => ({ scope: p.scope, purpose: p.purpose })) });
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical));
  const digest = Array.from(new Uint8Array(bytes), n => n.toString(16).padStart(2, '0')).join('');
  if (t.consent_version !== version || digest !== t.text_sha256 || !t.text.trim()) throw new ApiError(422, 'consent_text_mismatch', '授权内容无法核对');
}
