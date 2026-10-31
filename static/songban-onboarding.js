'use strict';

const startingChoices = {
  interests: ['宠物', '运动', '音乐', '校园生活', '画画设计', '编程', '还在探索'],
  skills: ['画画或设计', '写代码或搭网页', '整理资料', '介绍作品', '都没做过，想试试'],
  time: ['3小时以内', '半天', '一天', '一个周末'],
};
const startingDrafts = new Map();
let guestOpening = null;

function startingDraftKey() { return 'songban:start:' + (state.me?.person.id || 'visitor'); }
function emptyStartingPreferences() { return {interests: [], skills: [], time: '', city: '', experience: ''}; }
function readStartingDraft() {
  const key = startingDraftKey();
  let draft = startingDrafts.get(key);
  try { draft ||= JSON.parse(sessionStorage.getItem(key)); } catch {}
  return {...emptyStartingPreferences(), ...(state.me?.preferences || {}), ...(draft || {})};
}
function startingFormValue(form) {
  const data = new FormData(form);
  return {interests: data.getAll('interests'), skills: data.getAll('skills'), time: data.get('time') || '', city: (data.get('city') || '').trim(), experience: data.get('experience').trim()};
}
function rememberStartingDraft(form) {
  const draft = startingFormValue(form), key = startingDraftKey();
  startingDrafts.set(key, draft);
  try { sessionStorage.setItem(key, JSON.stringify(draft)); } catch {}
}
function forgetStartingDraft(key) {
  startingDrafts.delete(key);
  try { sessionStorage.removeItem(key); } catch {}
}
async function ensureGuest() {
  if (state.me) return;
  if (guestOpening) return guestOpening;
  const epoch = state.epoch;
  const pending = (async () => {
    // Retry an existing identity before making another visitor. A temporary
    // network failure must not replace a real account or its selected team.
    if (state.token) { await load(); return; }
    const guest = await api('/api/core/guest-session', {});
    if (epoch !== state.epoch) return;
    localStorage.setItem('studio-token', guest.token);
    state.token = guest.token;
    await load();
  })();
  guestOpening = pending;
  try { await pending; }
  finally { if (guestOpening === pending) guestOpening = null; }
}
function guestEntryPage() {
  const container = $('#content');
  container.innerHTML = head('直接开始', '正在打开你的访客空间。', '无需手机号和验证码。') + '<p class="muted" role="status">正在连接…</p>';
  const epoch = state.epoch;
  ensureGuest().then(() => { if (container.isConnected && state.me) render(); }).catch(error => {
    if (!container.isConnected || epoch !== state.epoch) return;
    container.innerHTML = head('暂时没有连接上', '你的空间还没有打开。', '请重试，已有账号也可以选择登录。') + `<p class="error" role="alert">${esc(error.message)}</p><div class="action-row"><button id="retry-guest" class="primary">重新连接</button><button id="optional-login" class="text-link">登录已有账号</button></div>`;
    $('#retry-guest').onclick = guestEntryPage;
    $('#optional-login').onclick = () => openAuth();
  });
}
function startingPreferencesSummary() {
  const p = state.me?.preferences;
  return `<div class="starting-summary"><p>${p ? `${p.city ? `城市：${esc(p.city)} · ` : ''}兴趣：${esc(p.interests.join('、'))} · 可投入：${esc(p.time)}` : '从你的兴趣、城市、经历和时间开始，找到适合的起点。'}</p><a class="text-link" href="#/onboarding">${p ? '修改兴趣和经历' : '选择兴趣和经历'} ${icon('arrow')}</a></div>`;
}
function onboardingPage() {
  const draft = readStartingDraft(), revision = state.me?.preferences?.revision || 0;
  const group = (name, title, index, type) => `<fieldset class="starting-question"><legend><span>${index}</span>${title}</legend><div class="starting-options">${startingChoices[name].map((label, i) => {
    const checked = name === 'time' ? draft.time === label : Array.isArray(draft[name]) && draft[name].includes(label);
    return `<label class="starting-option"><input type="${type}" name="${name}" value="${esc(label)}" ${checked ? 'checked' : ''}><span>${esc(label)}</span></label>`;
  }).join('')}</div></fieldset>`;
  $('#content').innerHTML = `<section class="starting-page">${head('你的起点 / 约一分钟', '先认识一下你。', '没做过也没关系，我们从你的起点出发。')}<form id="starting-form" data-revision="${revision}" novalidate>
    ${group('interests', '你平时对什么感兴趣？', '01', 'checkbox')}
    ${group('skills', '这些事情，你做过哪些？', '02', 'checkbox')}
    ${group('time', '这次，你能投入多少时间？', '03', 'radio')}
    <fieldset class="starting-question starting-city"><legend><span>04</span><label for="starting-city">你在哪座城市？</label><small>选填</small></legend><div class="starting-city-field"><input id="starting-city" name="city" type="text" list="starting-cities" autocomplete="address-level2" maxlength="60" value="${esc(draft.city)}" placeholder="输入或选择城市，如上海、杭州"><datalist id="starting-cities">${['上海', '北京', '杭州', '深圳', '广州', '成都', '南京', '武汉', '苏州', '西安', '重庆', '天津'].map(city => `<option value="${city}"></option>`).join('')}</datalist></div></fieldset>
    <details class="starting-experience" ${draft.experience ? 'open' : ''}><summary>补充你的经历 <span class="muted">选填</span><span aria-hidden="true">＋</span></summary><label for="starting-experience" class="muted">做过的项目、擅长的事情，或者这次想尝试什么。</label><textarea id="starting-experience" name="experience" maxlength="1500" rows="4" placeholder="比如：给班级做过活动海报，想和同伴试着做一个小作品。">${esc(draft.experience)}</textarea></details>
    <p id="starting-error" class="error" role="alert" hidden></p>
    <div class="action-row"><p class="muted">这些内容之后都可以修改。<br>${state.me && !state.me.guest ? '仅保存到你的账号，不会自动分享给团队。' : '无需登录，保存后可继续。请保留当前浏览器的访客入口。'}</p><button class="primary" type="submit">看看适合的活动 ${icon('arrow')}</button></div>
  </form></section>`;
  const form = $('#starting-form'), errorBox = $('#starting-error');
  const showError = text => { errorBox.textContent = text; errorBox.hidden = false; };
  form.addEventListener('change', event => {
    const input = event.target;
    if (input.name === 'skills' && input.checked) {
      for (const other of form.querySelectorAll('[name="skills"]')) {
        if (other !== input && (input.value === '都没做过，想试试' || other.value === '都没做过，想试试')) other.checked = false;
      }
    }
    errorBox.hidden = true;
    rememberStartingDraft(form);
  });
  form.addEventListener('input', () => rememberStartingDraft(form));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (form.dataset.submitting) return;
    const value = startingFormValue(form);
    for (const key of ['interests', 'skills', 'time']) {
      if (!value[key].length) {
        showError('请选一个兴趣、做过的事情和可用时间，再继续。');
        form.querySelector(`[name="${key}"]`).focus();
        return;
      }
    }
    rememberStartingDraft(form);
    const originalKey = startingDraftKey(), epoch = state.epoch;
    form.dataset.submitting = 'true'; form.setAttribute('aria-busy', 'true');
    const controls = [...form.querySelectorAll('input, textarea, button')];
    controls.forEach(control => control.disabled = true);
    const button = form.querySelector('[type="submit"]'); button.textContent = '正在保存…';
    errorBox.hidden = true;
    try {
      await ensureGuest();
      if (epoch !== state.epoch || !state.me) return;
      // Associate an anonymous draft with the newly created visitor before
      // saving, so a failed request can be retried without losing the form.
      startingDrafts.set(startingDraftKey(), value);
      try { sessionStorage.setItem(startingDraftKey(), JSON.stringify(value)); } catch {}
      const saved = await api('/api/core/me/preferences', {...value, expected_revision: Number(form.dataset.revision)}, 'PUT');
      state.me.preferences = saved.preferences;
      forgetStartingDraft(originalKey); forgetStartingDraft(startingDraftKey());
      if (form.isConnected) go('events');
      toast('兴趣和经历已保存，可以继续选择活动。');
    } catch (error) {
      if (!form.isConnected) return;
      showError(error.message);
      if (error.status === 409) {
        const reload = document.createElement('button'); reload.type = 'button'; reload.textContent = '读取最新选择';
        reload.onclick = async () => {
          try { await load(); forgetStartingDraft(startingDraftKey()); if (form.isConnected) onboardingPage(); }
          catch (failure) { showError(failure.message); }
        };
        errorBox.append(reload);
      }
    } finally {
      delete form.dataset.submitting; form.removeAttribute('aria-busy');
      controls.forEach(control => control.disabled = false);
      button.innerHTML = `看看适合的活动 ${icon('arrow')}`;
    }
  });
}
