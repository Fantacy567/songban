/* Native adapter boundary with explicit local fetch fixtures; no HTTP listener. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../../../static/platform-native.js'), 'utf8');
function fixture(initialWho) {
  const listeners = {}, nodes = [], requests = [];
  let who = initialWho, status = 200, mounted = 0, unmounted = 0, props;
  const document = { hidden: false, body: { append(node) { nodes.push(node); } }, createElement() { return { hidden: false, remove() { this.removed = true; } }; }, addEventListener(event, fn) { listeners[event] = fn; } };
  const window = { confirm: () => false, addEventListener(event, fn) { listeners['window:' + event] = fn; },
    SongbanCompanion: { mount(host, value) { mounted++; props = value; return { update(value) { props = value; }, unmount() { unmounted++; } }; } } };
  async function fetch(url, options = {}) {
    requests.push({ url, options });
    const code = url.endsWith('/session') ? (who ? 200 : 401) : status;
    return { status: code, ok: code >= 200 && code < 300, async json() { return url.endsWith('/session') ? who : url.endsWith('/session-bootstrap') ? { csrf_token: 'fixture-csrf' } : code >= 400 ? { error: { code: 'session_revoked' } } : { id: 'fixture-chat' }; } };
  }
  vm.runInNewContext(source, { window, document, fetch, AbortSignal, setTimeout, location: { assign() {} } });
  return { window, document, listeners, nodes, requests, setWho(value) { who = value; }, reject(value) { status = value; }, get props() { return props; }, get mounted() { return mounted; }, get unmounted() { return unmounted; } };
}
const base = { token: 'fixture-legacy-token', epoch: 1, page: 'work', team: 'fixture-team', restricted: false, onNavigate() {} };
(async () => {
  const manager = fixture({ id: 'manager-session', mode_epoch: 1, mode: 'manager', actor_id: 'manager-a', learner_id: null });
  await manager.window.SongbanPlatformNative.update(base);
  assert.deepEqual(JSON.parse(JSON.stringify(manager.props.context)), { domain: 'hall', resource_id: 'hackathon' });
  await manager.props.transport.open({ request_id: 'fixture-request', context: manager.props.context });
  const write = manager.requests.find(r => r.url.endsWith('/companion/sessions'));
  assert.equal(write.options.headers['X-CSRF-Token'], 'fixture-csrf');
  assert.equal(write.options.headers.Authorization, undefined, 'Cookie mode does not forward another bearer');
  manager.document.hidden = true; manager.listeners.visibilitychange();
  assert.equal(manager.nodes[0].hidden, true); assert.equal(manager.unmounted, 0);
  manager.document.hidden = false; manager.listeners.visibilitychange();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(manager.nodes[0].hidden, false); assert.equal(manager.unmounted, 0, 'A normal tab switch preserves local draft state');
  manager.props.onDirty(true);
  assert.equal(manager.window.SongbanPlatformNative.canLeave(), false);
  manager.reject(401);
  await assert.rejects(manager.props.transport.read('fixture-chat'), error => error.status === 401);
  assert.equal(manager.unmounted, 1, 'Rejected private reads remove the old private UI');
  assert.equal(manager.window.SongbanPlatformNative.canLeave(), true);

  const participant = fixture(null);
  await participant.window.SongbanPlatformNative.update(base);
  assert.equal(participant.props.context.domain, 'competition');
  await participant.props.transport.read('fixture-chat');
  const read = participant.requests.find(r => r.url.endsWith('/companion/sessions/fixture-chat'));
  assert.equal(read.options.headers.Authorization, 'Bearer fixture-legacy-token');
  participant.setWho({ id: 'child-session', mode_epoch: 2, mode: 'learner', actor_id: 'manager-a', learner_id: 'child-a' });
  await assert.rejects(participant.props.transport.read('fixture-chat'), error => error.status === 401);
  assert.equal(participant.unmounted, 1);
  console.log('PASS native adapter: cookie/Bearer isolation, tab draft preservation, leave guard, revoked UI clearing, child-mode boundary (local fetch fixtures only).');
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
