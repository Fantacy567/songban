'use strict';
(() => {
  if (!document.querySelector('meta[name="songban-learning-v2"]')) return;
  let checking = false;
  async function check(force = false) {
    if (checking) return;
    checking = true;
    document.documentElement.style.visibility = 'hidden';
    try {
      const response = await fetch('/api/learning/v2/session', { credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
      if (response.ok) {
        const session = await response.json();
        if (force || session.mode === 'learner') { location.replace('/learning-prep#/learn'); return; }
      } else if (response.status === 401) {
        if (force) { location.replace('/learning-prep#/family'); return; }
        const probe = await fetch('/api/core/me', { credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
        const result = await probe.json();
        if (result.error?.code === 'child_mode_restricted') { location.replace('/learning-prep#/learn'); return; }
        if (![200, 401].includes(probe.status)) throw Error('identity_unavailable');
      } else throw Error('identity_unavailable');
      document.documentElement.style.visibility = '';
      document.querySelector('#learning-identity-pending')?.remove();
    } catch { location.replace('/learning-prep#/family'); }
    finally { checking = false; }
  }
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel('songban-learning-identity');
    channel.onmessage = () => { void check(true); };
  }
  window.addEventListener('storage', event => { if (event.key === 'songban-learning-boundary') void check(true); });
  window.addEventListener('pageshow', () => { void check(); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) document.documentElement.style.visibility = 'hidden'; else void check();
  });
  void check();
})();
