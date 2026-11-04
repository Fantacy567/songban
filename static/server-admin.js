/* Server administration: credentials stay in memory, provider keys are write-only. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const base = '/api/server-admin/v1';
  const jobDomains = [
    {kind:'studio', path:'/studio-jobs', label:'创作编程', hint:'核对容器执行记录和供应商记录。'},
    {kind:'workbench', path:'/workbench-jobs', label:'课程老师', hint:'核对消息派发和供应商记录；文字教学无需 Docker。'},
  ];
  let bearer = '', generation = 0, current = null, busy = false, identity = '';
  try { bearer = localStorage.getItem('studio-token') || ''; } catch (_) {}
  const status = message => { $('#status').textContent = message; };
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const field = (label, name, value, min, max) => `<label>${label}<input name="${name}" type="number" value="${value}" min="${min}" max="${max}" step="1" required></label>`;
  function lock(message) {
    generation++; current = null; identity = ''; busy = false;
    $('#workspace').hidden = true; $('#provider-forms').replaceChildren(); $('#audit-list').replaceChildren();
    $('#runtime').replaceChildren(); $('#unknown-jobs').replaceChildren(); $('#administrator').textContent = ''; $('#login').hidden = false;
    if (message) status(message);
  }
  async function request(path, body, method='POST') {
    const headers = { ...(bearer ? {Authorization:'Bearer '+bearer} : {}) };
    if (body) {
      const response = await fetch('/api/learning/v2/session-bootstrap', {credentials:'same-origin', cache:'no-store'});
      const bootstrap = await response.json();
      if (response.ok) headers['X-CSRF-Token'] = bootstrap.csrf_token;
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, {method:body ? method : 'GET', credentials:'same-origin', cache:'no-store',
      headers, ...(body ? {body:JSON.stringify(body)} : {})});
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(result.error?.message || result.detail || '请求未完成，请重新读取后核对。');
      error.status = response.status;
      throw error;
    }
    return result;
  }
  function form(kind, config) {
    return `<form class="provider" data-kind="${kind}"><div class="provider-header"><h3>${kind === 'text' ? 'DeepSeek · 课程老师与创作编程' : '豆包 · 图片生成'}</h3><p>${escape(config.base_url)}<br>配置版本 ${config.revision} · ${config.key_configured ? '密钥已配置' : '尚未配置密钥'}<br>${config.configuration_ready ? '配置齐全；尚未验证真实调用' : '尚未具备完整启用条件'}</p></div>
      ${kind === 'image' ? `<p>${config.integration_status === 'private_images' ? '已接入私密图片服务；仍需独立的图片授权和用户额度。修改配置后，旧配置的未发出任务取消，用户额度需要重新核准，总消耗不会清零。' : '尚未配置私密图片运行目录，当前仅能准备配置。'}</p>` : ''}
      <label class="check"><input name="enabled" type="checkbox" ${kind === 'image' && config.integration_status !== 'private_images' ? 'disabled' : ''} ${config.enabled ? 'checked' : ''}>启用此模型服务</label>
      <label>模型或推理接入点<input name="model" value="${escape(config.model)}" maxlength="150" autocomplete="off" ${kind === 'text' ? 'required' : ''}></label>
      <label>替换 API 密钥（留空保留现有配置）<input name="api_key" type="password" value="" maxlength="4096" autocomplete="new-password"></label>
      <label class="check"><input name="clear_key" type="checkbox">移除已保存的密钥</label>
      <div class="fields">${field(kind === 'text' ? '累计调用上限（0 为暂停）' : '累计图片调用上限（0 为暂停）','max_calls',config.max_calls,0,kind === 'image' ? 10000 : 100000)}${kind === 'text' ? field('每次最大输出 tokens','max_output_tokens',config.max_output_tokens,128,4096) : '<input name="max_output_tokens" type="hidden" value="800">'}${field('超时时间（秒）','timeout_seconds',config.timeout_seconds,10,120)}${field('并发上限','max_concurrency',config.max_concurrency,1,8)}</div>
      ${kind === 'image' ? `<label>图片尺寸<select name="size"><option ${config.size !== '4K' ? 'selected' : ''}>2K</option><option ${config.size === '4K' ? 'selected' : ''}>4K</option></select></label><label class="check"><input name="supports_sequential_generation" type="checkbox" ${config.supports_sequential_generation !== false ? 'checked' : ''}>模型支持 sequential_image_generation 参数（不支持的模型请取消）</label><label>允许返回的模型名（可选，多个以逗号分隔）<input name="allowed_response_models" value="${escape((config.allowed_response_models || []).join(','))}" autocomplete="off"></label>` : ''}
      <p class="muted">保存只修改配置，不发送测试请求。${kind === 'text' ? '课程老师与创作编程共用文字额度。每条课程消息发起 1 次模型请求；每个编程小步骤最多发起 4 次，逐次计入累计额度。未知请求仍占用额度和并发位，须人工核对。' : ''}未知结果不会自动重发。</p><button type="submit">保存${kind === 'text' ? '模型' : '图片'}配置</button></form>`;
  }
  async function refresh() {
    const ticket = ++generation;
    $('#workspace').hidden = true; $('#provider-forms').replaceChildren(); current = null;
    status('正在核对管理员身份和服务端配置…');
    try {
      const data = await request(base+'/session');
      if (ticket !== generation) return;
      current = data; identity = data.administrator.email;
      $('#administrator').textContent = '管理员：'+identity;
      $('#provider-forms').innerHTML = Object.entries(data.providers).map(([kind, config]) => form(kind, config)).join('');
      $('#runtime').textContent = `${data.runtime.learning_workbench_registered ? '课程工作台已注册；文字老师无需 Docker。' : '课程工作台尚未注册。'} ${data.runtime.creative_studio_registered ? '创作编程服务已注册；执行生成代码仍需隔离环境。' : '创作编程服务尚未注册。'} ${data.runtime.image_runtime_registered ? '私密图片运行层已接入。' : '图片运行层尚未接入。'} ${data.runtime.image_consent_policy_configured ? '' : '图片用途授权文本尚未配置，孩子不能发起真实图片请求。'} ${data.runtime.notice}`;
      $('#unknown-jobs').replaceChildren();
      $('#login').hidden = true; $('#workspace').hidden = false; status('配置已读取。真实模型联调状态：尚未验证。');
    } catch (error) {
      if (ticket !== generation) return;
      lock(error.message);
    }
  }
  $('#provider-forms').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !current) return;
    const form = event.target, kind = form.dataset.kind, data = new FormData(form), ticket = generation;
    const payload = {request_id:crypto.randomUUID(), expected_revision:current.providers[kind].revision,
      enabled:data.get('enabled') === 'on', model:String(data.get('model')).trim(), api_key:String(data.get('api_key')),
      clear_key:data.get('clear_key') === 'on', ...Object.fromEntries(['max_calls','max_output_tokens','timeout_seconds','max_concurrency'].map(k=>[k,Number(data.get(k))]))};
    if (kind === 'image') Object.assign(payload, {size:data.get('size'), supports_sequential_generation:data.get('supports_sequential_generation') === 'on', allowed_response_models:String(data.get('allowed_response_models') || '').split(',').map(x=>x.trim()).filter(Boolean)});
    busy = true; form.querySelectorAll('button').forEach(button => { button.disabled = true; }); status('正在保存服务端配置…');
    try {
      await request(base+'/providers/'+kind, payload, 'PUT');
      if (ticket !== generation) return;
      form.elements.api_key.value = ''; await refresh(); status('配置已保存。密钥不会回显；没有发起模型调用。');
    } catch (error) {
      if (ticket !== generation) return;
      if ([401,403].includes(error.status)) lock(error.message);
      else status(error.message+' 请先重新读取以确认结果，不要反复提交。');
    } finally {
      payload.api_key = ''; busy = false;
      form.querySelectorAll('button').forEach(button => { button.disabled = false; });
    }
  });
  $('#send-code').addEventListener('click', async () => {
    const input = $('#login-form').elements.email;
    if (!input.reportValidity()) return;
    const button = $('#send-code'); button.disabled = true;
    try { await request('/api/studio/email-codes', {email:input.value, purpose:'login'}); status('验证码已发送，请查看邮箱。'); }
    catch (error) { status(error.message); }
    finally { button.disabled = false; }
  });
  $('#login-form').addEventListener('submit', async event => {
    event.preventDefault(); const form = event.target, button = form.querySelector('[type=submit]'); button.disabled = true;
    try {
      const result = await request('/api/studio/login-email', {email:form.elements.email.value, code:form.elements.code.value});
      bearer = result.token; form.elements.code.value = ''; await refresh();
    } catch (error) { status(error.message); }
    finally { button.disabled = false; }
  });
  $('#refresh').addEventListener('click', () => { if (!busy) refresh(); });
  $('#read-unknown').addEventListener('click', async () => {
    if (!current || busy) return;
    const ticket = generation; $('#unknown-jobs').replaceChildren();
    busy=true; $('#read-unknown').disabled=true;
    try {
      const results = await Promise.allSettled(jobDomains.map(domain=>request(base+domain.path)));
      if (ticket !== generation) return;
      const denied=results.find(result=>result.status==='rejected' && [401,403].includes(result.reason.status));
      if (denied) { lock(denied.reason.message); return; }
      $('#unknown-jobs').innerHTML = results.map((result,index)=>{
        const domain=jobDomains[index];
        const content=result.status==='rejected' ? `<p>${escape(result.reason.message)}</p>` :
          result.value.items.map(job=>`<form class="provider" data-domain="${domain.kind}" data-job="${escape(job.id)}"><h4>待核对任务 ${escape(job.id)}</h4><p>${escape(job.created_at)} · ${escape(job.failure_code || '结果未知')}</p><label>核对证据（至少 10 字；请勿填写孩子聊天原文）<textarea name="evidence" minlength="10" maxlength="3000" required></textarea></label><label class="check"><input name="acknowledged" type="checkbox" required>我已核对执行记录，确认关闭本任务；保留已占用额度，不重试、不标为成功。</label><button type="submit">记录证据并关闭任务</button></form>`).join('') || '<p>没有待核对的未知任务。</p>';
        return `<section class="unknown-group" data-domain="${domain.kind}"><h3>${domain.label}</h3><p>${domain.hint}</p>${content}</section>`;
      }).join('');
    } catch (error) { if (ticket === generation) { if ([401,403].includes(error.status)) lock(error.message); else status(error.message); } }
    finally { if(ticket === generation)busy=false; $('#read-unknown').disabled=false; }
  });
  $('#unknown-jobs').addEventListener('submit', async event => {
    event.preventDefault(); if (!current || busy) return;
    const form=event.target, ticket=generation, button=form.querySelector('button');
    const domain=jobDomains.find(item=>item.kind===form.dataset.domain);
    if (!domain || !form.reportValidity()) return;
    busy=true; button.disabled=true;
    try {
      const result=await request(base+domain.path+'/'+encodeURIComponent(form.dataset.job)+'/close-unknown',{evidence:form.elements.evidence.value});
      if (ticket !== generation) return;
      form.remove(); status(result.notice);
    } catch(error) { if(ticket === generation) { if([401,403].includes(error.status))lock(error.message); else status(error.message+' 请重新读取任务状态，勿重复核对。'); } }
    finally { busy=false; button.disabled=false; }
  });
  $('#leave').addEventListener('click', () => { bearer = ''; lock('已离开管理页面。平台账号可在账号入口退出。'); });
  document.querySelector('nav').addEventListener('click', async event => {
    const button = event.target.closest('[data-section]'); if (!button || !current) return;
    const section = button.dataset.section;
    for (const name of ['providers','operations','audit']) $('#'+name).hidden = name !== section;
    document.querySelectorAll('[data-section]').forEach(item=>item.setAttribute('aria-pressed', String(item === button)));
    if (section !== 'audit') return;
    const ticket = generation; $('#audit-list').replaceChildren();
    try {
      const result = await request(base+'/audit'); if (ticket !== generation) return;
      for (const row of result.items) {
        const li = document.createElement('li'); li.textContent = `${row.created_at} · ${row.actor_id} · ${row.kind} 版本 ${row.revision} · ${row.changed_fields.join('、') || '无字段变化'}`; $('#audit-list').append(li);
      }
      if (!result.items.length) $('#audit-list').textContent = '还没有配置变更。';
    } catch (error) { if (ticket === generation) lock(error.message); }
  });
  window.addEventListener('storage', event=>{ if (event.key === 'studio-token') { bearer=''; lock('账号已变化，请重新确认管理员身份。'); } });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { lock('返回页面后将重新核对管理员身份。'); }
    else refresh();
  });
  refresh();
})();
