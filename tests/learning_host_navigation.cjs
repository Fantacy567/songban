/* Real host script in an isolated DOM shell: bookmarks, guards and identity exits. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../static/learning-host.js'), 'utf8');
function shell(hash) {
  const events = {}, docEvents = {}, calls = [], host = { focus() { calls.push('focus'); } };
  const exit = {}, header = {}, storage = () => ({ removeItem(k) { delete this[k]; }, setItem(k,v) { this[k] = v; } });
  const context = { URLSearchParams, Set, crypto: { randomUUID: () => 'new-boundary' },
    localStorage: storage(), sessionStorage: storage(), location: { hash, assign(url) { calls.push(['exit',url]); } },
    history: { replaceState(_s,_t,next) { context.location.hash = next; } },
    document: { querySelector(s) { return s === '#learning-prep-root' ? host : header; }, querySelectorAll() { return [exit]; }, addEventListener(n,f) { docEvents[n]=f; } },
    window: { addEventListener(n,f) { events[n]=f; }, SongbanLearning: { mount(h,opts) {
      context.options = opts; calls.push(['mount',opts.initialRoute]); return {
        async navigate(r) { calls.push(['navigate',r]); if (context.allow) opts.onRouteChange(r); return context.allow; },
        async canLeave() { return context.allow; }, unmount() { calls.push('unmount'); }
      };
    } } }, allow: true,
  };
  vm.runInNewContext(source, context);
  return { context, events, docEvents, calls, exit, header };
}
(async () => {
  let passed=0;
  for (const hash of ['#/learn', '#/family', '#/learn/start', '#/learning-admin', '#/learn/run?id=run-1', '#/learn/run?id=run-1&view=review', '#/learn/works', '#/learn/works?id=a1&version=v2']) {
    const s=shell(hash); assert.equal(s.calls[0][1],hash); ++passed;
  }
  for (const hash of ['#/learn/run', '#/learn/run?id=a&id=b', '#/learn/run?id=a&role=staff', '#/learn/run?id=a&view=admin', '#/learn/works?version=v1', '#/learn/works?id=%2F%2Fevil.invalid', '#/learn/start?token=secret', '#/learning-admin?role=staff']) {
    assert.equal(shell(hash).calls[0][1],'#/learn'); ++passed;
  }
  const s=shell('#/learn/run?id=first');
  s.context.allow=false; s.context.location.hash='#/learn/works'; await s.events.hashchange();
  assert.equal(s.context.location.hash,'#/learn/run?id=first'); ++passed;
  await s.events.hashchange(); // Browser's guard-restoration event.
  s.context.allow=true; s.context.location.hash='#/learn/run?id=second&view=review'; await s.events.hashchange();
  assert.equal(s.calls.at(-1)[1],'#/learn/run?id=second&view=review'); assert.equal(s.calls.filter(c=>c[0]==='mount').length,1); ++passed;
  s.context.options.onSessionChange({mode:'learner'}); assert.equal(s.exit.hidden,true); assert.equal(s.header.hidden,true); ++passed;
  s.context.options.onSessionChange({mode:'manager'}); assert.equal(s.header.hidden,false); ++passed;
  s.context.localStorage['studio-token']='old'; s.context.localStorage['songban:workbench:draft']='private'; s.context.localStorage['unrelated-setting']='keep';
  s.context.options.onIdentityBoundary(); assert.equal(s.context.localStorage['studio-token'],undefined); assert.equal(s.context.localStorage['songban:workbench:draft'],undefined); assert.equal(s.context.localStorage['unrelated-setting'],'keep'); ++passed;
  await s.docEvents.click({target:{closest(sel){return sel==='[data-learning-skip]'?{}:null;}},preventDefault(){}});
  assert.equal(s.calls.at(-1),'focus'); assert.equal(s.context.location.hash,'#/learn/run?id=second&view=review'); ++passed;
  s.events.pagehide({persisted:true}); assert.notEqual(s.calls.at(-1),'unmount');
  s.events.pagehide({persisted:false}); assert.equal(s.calls.at(-1),'unmount'); ++passed;
  console.log(JSON.stringify({passed,scope:'isolated static host, no child data or service'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
