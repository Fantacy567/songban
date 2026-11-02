'use strict';
(() => {
  const host = document.querySelector('#learning-prep-root');
  const validRoute = hash => {
    if (['#/learn', '#/learn/start', '#/family', '#/learning-admin'].includes(hash)) return true;
    const [path, query = '', ...extra] = hash.split('?');
    if (extra.length || !['#/learn/run', '#/learn/works'].includes(path)) return false;
    const params = new URLSearchParams(query);
    const keys = [...params.keys()];
    if (new Set(keys).size !== keys.length) return false;
    const identifier = value => value !== null && /^[A-Za-z0-9_.:-]{1,100}$/.test(value);
    if (path === '#/learn/run') return identifier(params.get('id')) && keys.every(key => ['id', 'view'].includes(key)) && (!params.has('view') || params.get('view') === 'review');
    return keys.every(key => ['id', 'version'].includes(key)) && (!params.has('id') || identifier(params.get('id'))) && (!params.has('version') || (identifier(params.get('version')) && params.has('id')));
  };
  let handle, current = validRoute(location.hash) ? location.hash : '#/learn', reverting = false;
  const clearLegacy = () => {
    for (const storage of [localStorage, sessionStorage]) {
      for (const key of Object.keys(storage)) {
        if (['studio-token', 'studio-squad', 'studio-contest', 'studio-accounts', 'hackathon-collab-session-v1', 'songban-personal', 'songban-event'].includes(key) || key.startsWith('songban:workbench:') || key.startsWith('songban:start:')) storage.removeItem(key);
      }
    }
    localStorage.setItem('songban-learning-boundary', crypto.randomUUID());
  };
  if (!window.SongbanLearning) {
    host.textContent = '学习页面暂时没有加载成功。请刷新重试，已有记录仍保存在服务端。';
    return;
  }
  handle = window.SongbanLearning.mount(host, {
    initialRoute: current,
    onIdentityBoundary: clearLegacy,
    onRouteChange(route) {
      current = route;
      if (location.hash !== route) history.replaceState(null, '', route);
    },
    onSessionChange(session) {
      document.querySelectorAll('[data-learning-exit]').forEach(link => { link.hidden = session?.mode === 'learner'; });
      document.querySelector('[data-learning-exit-shell]').hidden = session?.mode === 'learner';
    },
  });
  window.addEventListener('hashchange', async () => {
    if (reverting) { reverting = false; return; }
    const next = validRoute(location.hash) ? location.hash : current;
    if (next === current) return;
    if (!(await handle.navigate(next))) {
      reverting = true; location.hash = current;
    }
  });
  document.addEventListener('click', async event => {
    if (event.target.closest('[data-learning-skip]')) { event.preventDefault(); host.focus(); return; }
    const link = event.target.closest('[data-learning-exit]');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (await handle.canLeave()) location.assign(link.href);
  });
  window.addEventListener('pagehide', event => { if (!event.persisted) handle.unmount(); });
})();
