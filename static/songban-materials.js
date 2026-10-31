'use strict';
// One mount belongs to one identity and one space. Never reuse a late response after navigation.
const SongbanMaterials = (() => {
  let guest = {text:'', url:'', files:[], nature:'unverified', author:''};
  const pending = new Map();
  const fileDrafts = new Map();
  let leaveGuard=null;
  const statuses = {received:'已收到，等待读取',reading:'读取中（中断后可重试）',ready:'已读取',partial:'已读取部分 / 需核对',failed:'读取失败',withdrawn:'已撤回'};
  const verifications = {unverified:'未独立核实',human_confirmed:'人工确认',deferred:'暂不处理',needs_review:'新证据待复核',source_withdrawn:'来源已撤回'};
  const kinds = {statement:'材料中的表述',suggestion:'AI 建议',unknown:'待确认'};
  const natures = {unverified:'来源性质待核实',sample:'虚构样例',self_report:'个人自述 / 聊天',organizer_notice:'自标主办方通知，未核验'};
  const requestId = key => {if(!pending.has(key))pending.set(key,crypto.randomUUID());return pending.get(key);};
  function reset(){pending.clear();fileDrafts.clear();guest={text:'',url:'',files:[]};for(const key of Object.keys(sessionStorage))if(key.startsWith('songban:materials:'))sessionStorage.removeItem(key);if(leaveGuard)window.removeEventListener('beforeunload',leaveGuard);leaveGuard=null;}

  async function mount(host, {teamId='', event=null}={}) {
    const epoch=state.epoch, token=state.token;
    let data=null, busy=false, selected=new Set(), draft=null;
    const alive=()=>host.isConnected&&epoch===state.epoch&&token===state.token;
    const path=suffix=>'/api/materials/spaces/'+encodeURIComponent(data.id)+suffix;
    const q=selector=>host.querySelector(selector);
    const draftKey=token?`songban:materials:${encodeURIComponent(state.me.person.id)}:${encodeURIComponent(teamId||'personal')}:draft`:'';
    let stored=null,persisted=true;
    try{stored=draftKey?JSON.parse(sessionStorage.getItem(draftKey)||'null'):null;}catch{}
    const initial=stored||(!teamId?guest:{});
    const label=teamId?'团队共享材料':'我的个人草稿';
    host.classList.add('materials');
    host.innerHTML=`<section class="card material-intake"><div class="row spread"><span class="chip">${label}</span><a href="#/${teamId?'event':'materials'}" class="text-link">${teamId?'回到个人资料入口':'查看团队资料'}</a></div><h2>把手头的资料放进来，<br>松伴帮你理清楚。</h2><p class="muted">规则、聊天、截图和想法，可以一起放。整理只使用此空间中已读取的材料；不会读取其他私聊。</p><form id="material-input"><label for="material-text">文字或聊天记录</label><textarea id="material-text" rows="5" maxlength="40000" placeholder="直接粘贴，不必先分好类。也可以在这里粘贴截图。"></textarea><label for="material-url">公开网页链接</label><input id="material-url" type="url" placeholder="https://…"><div class="material-meta"><div><label for="material-author">原作者 / 发言者（选填）</label><input id="material-author" maxlength="200" placeholder="不知道就留空"></div><div><label for="material-nature">材料性质</label><select id="material-nature"><option value="unverified">待核实材料</option><option value="self_report">个人自述 / 聊天</option><option value="organizer_notice">主办方通知（需核实）</option><option value="sample">虚构样例</option></select></div></div><div class="material-drop" tabindex="0" aria-label="文件拖放区域，按回车选择文件"><label for="material-files">添加截图或文件，也可以拖到这里</label><input id="material-files" type="file" multiple accept=".png,.jpg,.jpeg,.pdf,.docx,.txt"><p id="material-queued" class="caption"></p></div><p class="caption">PNG/JPEG、PDF、DOCX、TXT；单文件 8 MB，PDF 最多 20 页，图片最多 2000 万像素。文字每份 4 万字；每个空间 40 份 / 50 MB（含撤回原件），每次 AI 整理最多 8 万字。DOCX 图片请另传。</p><div class="action-row"><button type="submit" class="secondary">${token?'保存并读取材料':'登录后保存材料'}</button>${event?'<button type="button" id="material-sample" class="ghost">加入本活动样例规则</button>':''}</div></form><p class="caption">${teamId?'本团队成员可以查看原件和结果。':'当前输入先留在本页；登录后保存至个人空间。选择共享范围后，团队才能看到材料。'}</p></section><p id="material-message" role="status" aria-live="polite"></p><div id="material-saved"></div><div id="material-results"></div><div id="material-share"></div>`;
    for(const [id,key] of [['material-text','text'],['material-url','url'],['material-author','author']])q('#'+id).value=typeof initial[key]==='string'?initial[key]:'';
    q('#material-nature').value=Object.hasOwn(natures,initial.nature)?initial.nature:'unverified';
    let files=(fileDrafts.get(draftKey)||(!teamId&&!stored?guest.files:[])||[]).slice();
    const caption=q('.material-intake > p.caption');
    if(token)caption.textContent=teamId?'点击保存后，本团队成员可以查看原件和结果。':'点击保存后存入个人空间；选择共享范围并确认后，团队才能看到材料。';
    const draftNotice=document.createElement('p');draftNotice.className='caption';draftNotice.setAttribute('role','status');q('#material-input').append(draftNotice);
    let missingFiles=Array.isArray(stored?.fileNames)&&stored.fileNames.length&&!files.length;
    const queue=()=>q('#material-queued').textContent=files.length?files.map(f=>f.name+' · '+Math.ceil(f.size/1024)+' KB').join('；'):'尚未选择附件';queue();
    const keep=()=>{
      if(!alive())return;
      const input={text:q('#material-text').value,url:q('#material-url').value,nature:q('#material-nature').value,author:q('#material-author').value};
      if(!token){guest={...input,files};return;}
      fileDrafts.set(draftKey,files.slice());
      try{if(input.text||input.url||input.author||files.length||missingFiles)sessionStorage.setItem(draftKey,JSON.stringify({...input,fileNames:missingFiles?stored.fileNames:files.map(f=>f.name)}));else sessionStorage.removeItem(draftKey);persisted=true;}catch{persisted=false;}
      draftNotice.textContent=!persisted?'当前输入未能暂存，请保存材料后再离开。':missingFiles?'文字草稿已恢复；附件需重新选择，浏览器刷新不会保留文件。':files.length?'文字已暂存在本标签页；附件请在刷新前保存，或回来后重新选择。':input.text||input.url||input.author?'未保存到服务器；文字草稿已暂存在本标签页，刷新可恢复。退出或切换账号时清除。':'尚未输入材料。填写后点击保存，才会上传到服务器。';
    };
    if(token){guest={text:'',url:'',files:[]};keep();}
    if(leaveGuard)window.removeEventListener('beforeunload',leaveGuard);
    leaveGuard=e=>{if(alive()&&(files.length||!persisted)){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',leaveGuard);
    q('#material-text').oninput=keep;q('#material-url').oninput=keep;q('#material-nature').onchange=keep;q('#material-author').oninput=keep;
    function queueFiles(list){missingFiles=false;files.push(...list);queue();keep();}
    q('#material-files').onchange=e=>{queueFiles(e.target.files);e.target.value='';};
    const drop=q('.material-drop');drop.ondragover=e=>{e.preventDefault();drop.classList.add('dragging');};drop.ondragleave=()=>drop.classList.remove('dragging');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('dragging');queueFiles(e.dataTransfer.files);};drop.onkeydown=e=>{if(e.target===drop&&e.key==='Enter'){e.preventDefault();q('#material-files').click();}};
    q('#material-input').addEventListener('paste',e=>{const images=[...e.clipboardData.items].filter(x=>x.kind==='file').map(x=>x.getAsFile());if(images.length){e.preventDefault();queueFiles(images);}});
    function message(text,error=false){if(alive()){q('#material-message').className=error?'error':'notice';q('#material-message').textContent=text;}}
    async function reload(){const fresh=await api('/api/materials/space'+(teamId?'?team_id='+encodeURIComponent(teamId):''));if(!alive())throw Error('页面已切换。');data=fresh;draw();}
    async function action(fn){if(busy)return;busy=true;host.setAttribute('aria-busy','true');host.querySelectorAll('button').forEach(b=>b.disabled=true);try{await fn();}catch(e){message(e.message,true);if(alive()&&data&&e.status===409){const b=document.createElement('button');b.type='button';b.textContent='读取最新版本并比较（保留输入）';b.onclick=()=>action(async()=>{const edits=[...host.querySelectorAll('[data-edit]')].map(f=>[f.dataset.edit,f.elements.text.value,f.elements.note.value,f.elements.verification.value]);await reload();for(const [id,text,note,v]of edits){const f=q(`[data-edit="${id}"]`);if(f){f.elements.text.value=text;f.elements.note.value=note;f.elements.verification.value=v;f.closest('details').open=true;}}message('已读取最新版本，请比较保留的输入后再保存。');});q('#material-message').append(b);}}finally{busy=false;if(alive()){host.removeAttribute('aria-busy');host.querySelectorAll('button').forEach(b=>b.disabled=false);}}}
    async function add(body){const key=data.id+':source:'+JSON.stringify(body);const response=await api(path('/sources'),{...body,request_id:requestId(key)});await reload();const source=response.source;if(['received','failed','reading'].includes(source.status)){message('已收到「'+body.name+'」，正在读取…');await api(path('/sources/'+source.id+'/parse'),{expected_revision:data.revision});await reload();}pending.delete(key);return source;}
    function encodeFile(f){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('无法读取本机文件。'));reader.readAsDataURL(f);});}
    q('#material-input').onsubmit=e=>{e.preventDefault();if(!token){keep();openAuth();return;}action(async()=>{
      const meta={author:q('#material-author').value,nature:q('#material-nature').value};const errors=[];
      const text=q('#material-text').value.trim(),url=q('#material-url').value.trim();
      if(!text&&!url&&!files.length)throw Error('先粘贴文字、添加链接或选择文件。');
      if(text){await add({...meta,kind:'text',name:'文字 / 聊天摘录',content:text});if(q('#material-text').value.trim()===text)q('#material-text').value='';keep();}
      if(url){await add({...meta,kind:'url',name:url.slice(0,200),content:url});if(q('#material-url').value.trim()===url)q('#material-url').value='';keep();}
      const remaining=[];
      for(const f of files){try{if(f.size>8000000)throw Error(f.name+' 超过 8 MB，未上传。');await add({...meta,kind:'file',name:f.name,content:await encodeFile(f)});}catch(e){remaining.push(f);errors.push(e.message);}}
      files=remaining;queue();guest={text:'',url:'',files:[]};keep();message(errors.length?errors.join('；'):'已保存。逐份读取状态见下方；失败材料可以补充文字或重试。',errors.length>0);
    });};
    if(event)q('#material-sample').onclick=()=>{if(!token){guest.text=event.rules||'';q('#material-text').value=guest.text;q('#material-nature').value='sample';keep();message('这是虚构活动样例。登录后确认性质再保存。');return;}action(()=>add({kind:'text',name:event.title+'（虚构样例）',content:event.rules||'',nature:'sample',author:''}));};

    async function download(id){const r=await fetch(path('/sources/'+id+'/original'),{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('原件下载失败，请重新登录或刷新。');if(!alive())return;const u=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=u;a.download=data.sources.find(s=>s.id===id).metadata.name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
    function citation(c){const source=data.sources.find(s=>s.id===c.source_id);const seg=source?.segments.find(s=>s.id===c.segment_id);return `<details class="material-citation"><summary>${esc(source?.metadata.name||'来源')} · ${esc(c.location)} · ${esc(natures[c.nature])}</summary><blockquote>${esc(c.quote)}</blockquote><p class="caption">材料 v${c.source_version} · 原文字符 ${c.start}–${c.end}。引用存在不代表已核实。</p><pre class="material-source">${esc(seg?.text||'该来源当前不可用，请核对修订记录。')}</pre></details>`;}
    function draw(){
      const active=data.sources.filter(s=>s.status!=='withdrawn');
      q('#material-saved').innerHTML=`<section class="card"><div class="row spread"><h2>已收下的材料 <span class="muted">${active.length}</span></h2><button id="material-refresh" class="ghost">刷新状态</button></div>${data.sources.length?data.sources.map(s=>`<details class="material-source-row"><summary><strong>${esc(s.metadata.name)}</strong><span class="status-pill">${esc(statuses[s.status])}</span></summary><p class="caption">${esc(natures[s.metadata.nature])} · 原作者：${esc(s.metadata.author||'未知')} · v${s.version} · ${esc(s.created_at)}</p>${s.error?`<p class="error">${esc(s.error)}</p>`:''}${s.warnings.map(w=>`<p class="notice">${esc(w)}</p>`).join('')}${s.segments.map(seg=>`<details><summary>${esc(seg.location)} · ${seg.method==='ocr'?'图片识别，待核对':'文本读取'}</summary><pre class="material-source">${esc(seg.text)}</pre></details>`).join('')}<div class="action-row"><button data-download="${s.id}">下载原件</button>${s.status!=='withdrawn'?`<button data-withdraw="${s.id}" class="ghost">撤回此材料</button>`:''}${['received','reading','failed'].includes(s.status)?`<button data-parse="${s.id}">重试读取</button>`:''}</div></details>`).join(''):'<p class="empty">还没有保存的材料。先把手头的信息放进来。</p>'}<p class="caption">${esc(data.model.notice)}。点击整理会将此空间已读取的正文发送给服务端配置的模型。</p>${!data.model.configured?'<p class="notice">真实模型尚未配置，材料仍可保存和读取。</p>':''}<button class="primary" id="material-generate">帮我整理${data.result.items?' / 补充更新':''}</button>${data.batches.length?`<details class="material-history"><summary>最近整理状态与范围</summary>${data.batches.map(b=>`<p>${esc(b.created_at)} · ${esc({completed:'已整理',failed:'失败',stale:'版本已变化，未采用',running:'运行中；中断后可发起新批次'}[b.status])} · 输入 v${b.input_revision} · ${esc(b.model_id)}<br>${esc(b.error)}<br>${esc(b.inputs.excluded.map(x=>x.name+'：'+x.reason).join('；'))}</p>`).join('')}</details>`:''}</section>`;
      q('#material-refresh').onclick=()=>action(reload);
      host.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>action(()=>download(b.dataset.download)));
      host.querySelectorAll('[data-parse]').forEach(b=>b.onclick=()=>action(async()=>{await api(path('/sources/'+b.dataset.parse+'/parse'),{expected_revision:data.revision});await reload();}));
      host.querySelectorAll('[data-withdraw]').forEach(b=>b.onclick=()=>action(async()=>{await api(path('/sources/'+b.dataset.withdraw+'/withdraw'),{expected_revision:data.revision});await reload();message('已撤回，相关结果待更新；原件与修订记录保留。');}));
      q('#material-generate').onclick=()=>action(async()=>{const key=data.id+':generate:'+data.revision;message('正在整理当前已读取的材料…');try{const r=await api(path('/generate'),{expected_revision:data.revision,request_id:requestId(key)});pending.delete(key);await reload();message(r.status==='completed'?'整理结果已保存，请核对引用和未知项。':r.error||'该批次尚未完成，可刷新状态查看。',r.status!=='completed');}catch(e){if(e.status)pending.delete(key);await reload();throw e;}});
      const result=data.result;
      const groups=new Map();(result.items||[]).forEach(i=>{if(!groups.has(i.category))groups.set(i.category,[]);groups.get(i.category).push(i);});
      q('#material-results').innerHTML=(result.items?`<section class="material-result-heading"><p class="eyebrow">理清楚，再向前一步</p><h2>${esc(result.summary)}</h2><p class="caption">${esc(result.provenance)} · 已保存 v${data.result_revision}</p>${data.stale?'<p class="notice">材料已变化，下面保留上一版结果。请重新整理并比较变化，再带入团队。</p>':''}${result.scope.excluded.length?`<p class="notice">未纳入：${result.scope.excluded.map(x=>esc(x.name+'（'+x.reason+'）')).join('；')}</p>`:''}${result.scope.partial.length?'<p class="notice">本次包含部分读取或 OCR 材料，请展开原件核对；未读内容没有被补写。</p>':''}</section><details class="card"><summary>本次变化：新增 ${result.changes.added.length} · 重复 ${result.changes.repeated.length} · 不再出现 ${result.changes.removed.length} · 保护 ${result.changes.protected.length}</summary>${[['added','新增'],['repeated','重复（保留全部引用）'],['removed','本次模型不再列出'],['protected','人工修正已保护']].map(([k,l])=>result.changes[k].length?`<p><strong>${l}</strong></p><ul>${result.changes[k].map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`:'').join('')}</details><div class="material-groups">${[...groups].map(([category,items])=>`<section class="card"><h2>${esc(category)}</h2>${items.map(i=>`<article class="material-item ${i.importance==='high'?'material-important':''}" data-item="${i.id}"><div class="row spread"><span class="chip">${esc(kinds[i.kind])}${i.importance==='high'?' · 重点':''}</span><span class="caption">${esc(verifications[i.verification])}${i.protected?' · 人工保护':''}</span></div><label class="material-select"><input type="checkbox" data-select="${i.id}" ${selected.has(i.id)?'checked':''}><span>${esc(i.text)}</span></label>${i.conflict?`<p class="notice">冲突组：${esc(i.conflict)} · 双方保留，请核对来源。</p>`:''}${i.citations.map(citation).join('')}${!i.citations.length?'<p class="caption">此项为建议或待确认问题，没有直接事实引用。</p>':''}<details class="material-edit"><summary>纠正 / 确认这条信息</summary><form data-edit="${i.id}"><label>内容<textarea name="text" maxlength="1500" required>${esc(i.text)}</textarea></label><label>核实状态<select name="verification"><option value="unverified">未独立核实</option><option value="human_confirmed" ${i.verification==='human_confirmed'?'selected':''}>人工确认</option><option value="deferred" ${i.verification==='deferred'?'selected':''}>暂不处理</option></select></label><label>修改或确认依据<input name="note" maxlength="1000" required value="${esc(i.human_note)}" placeholder="说明核对了什么；原引用会保留"></label><button type="submit">保存纠正</button></form></details></article>`).join('')}</section>`).join('')}</div><section class="card"><h2>把选中的信息带入实践</h2><p>先选择条目，再确认目标小队和共享来源。不会自动发布方向或任务。</p><button id="material-preview-share" class="secondary">查看所选内容与共享范围</button></section><details class="card"><summary>修订记录与历史结果</summary>${data.history.map(h=>`<details><summary>v${h.revision} · ${esc(h.kind)} · ${esc(h.created_at)}</summary><pre class="material-source">${esc(JSON.stringify(h.body,null,2))}</pre></details>`).join('')||'<p>尚无修订。</p>'}</details>`:'')+`${data.drafts.length?`<section class="card"><h2>已保存的团队草稿</h2>${data.drafts.map(d=>`<details><summary>${d.body.kind==='direction'?'方向':'行动建议'}草稿 · ${esc(d.created_at)}</summary><pre class="material-source">${esc(d.body.text)}</pre><p class="caption">${esc(d.body.notice)}</p><button data-open-draft="${d.id}">继续处理这份草稿</button></details>`).join('')}</section>`:''}`;
      host.querySelectorAll('[data-select]').forEach(c=>c.onchange=()=>{c.checked?selected.add(c.dataset.select):selected.delete(c.dataset.select);q('#material-share').innerHTML='';});
      host.querySelectorAll('[data-edit]').forEach(f=>f.onsubmit=e=>{e.preventDefault();action(async()=>{await api(path('/items/'+f.dataset.edit),{...Object.fromEntries(new FormData(f)),expected_revision:data.revision},'PATCH');await reload();message('纠正已保存，原文引用及修改记录保留。');});});
      if(q('#material-preview-share'))q('#material-preview-share').onclick=previewShare;
      host.querySelectorAll('[data-open-draft]').forEach(b=>b.onclick=()=>{const d=data.drafts.find(x=>x.id===b.dataset.openDraft);draft={...d.body,id:d.id,team_id:d.team_id};showDraft();});
    }
    function previewShare(){
      const items=data.result.items.filter(i=>selected.has(i.id));
      if(!items.length){message('请先勾选要带入实践的条目。',true);return;}
      if(data.stale){message('材料已变化，请先重新整理。',true);return;}
      const teams=state.me.teams.filter(t=>!teamId||t.id===teamId);
      const sourceIds=new Set(items.flatMap(i=>i.citations.map(c=>c.source_id)));
      q('#material-share').innerHTML=`<section class="card accent"><h2>核对共享范围</h2><ul>${items.map(i=>`<li>${esc(i.text)}</li>`).join('')}</ul><p>以下来源的<strong>完整原件和已读取正文</strong>会共享给目标团队的全体成员。不要选择包含未获准私人聊天的原件。</p><ul>${data.sources.filter(s=>sourceIds.has(s.id)).map(s=>`<li>${esc(s.metadata.name)}</li>`).join('')||'<li>这些建议没有直接引用原件。</li>'}</ul>${teams.length?`<label for="material-target">目标团队</label><select id="material-target">${teams.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('')}</select><div class="action-row"><button data-draft-kind="direction">确认共享并创建方向草稿</button><button data-draft-kind="tasks">确认共享并创建行动草稿</button></div>`:'<p>还没有团队。个人材料已经保留。</p><a class="primary" href="#/team">创建或加入小队</a>'}</section>`;
      host.querySelectorAll('[data-draft-kind]').forEach(b=>b.onclick=()=>action(async()=>{const team=q('#material-target').value,body={team_id:team,item_ids:[...selected],kind:b.dataset.draftKind,share_sources:true,expected_revision:data.revision};const key=data.id+':draft:'+JSON.stringify(body);const r=await api(path('/drafts'),{...body,request_id:requestId(key)});pending.delete(key);draft={...r.body,id:r.id,team_id:team};await reload();showDraft();message('团队草稿已保存，尚未改变正式安排。');}));
      q('#material-share').scrollIntoView({behavior:'smooth',block:'start'});
    }
    function showDraft(){q('#material-share').innerHTML=`<section class="card accent"><h2>${draft.kind==='direction'?'方向':'行动建议'}草稿已保存</h2><pre class="material-source">${esc(draft.text)}</pre><p>${esc(draft.notice)}</p><button id="material-use-draft" class="primary">${draft.kind==='direction'?'带入方向编辑页，核对后再保存':'作为讨论送入团队统筹，等待队长确认'}</button></section>`;q('#material-use-draft').onclick=()=>action(async()=>{
      const prepared=await api(path('/drafts/'+draft.id+'/prepare'),{expected_revision:data.revision});draft={...prepared.body,id:prepared.id,team_id:prepared.team_id};
      state.personal=false;sessionStorage.removeItem('songban-personal');state.team=draft.team_id;localStorage.setItem('studio-squad',state.team);await load();
      if(draft.kind==='direction'){go('direction');const f=$('#direction-form');if(f&&!f.elements.rules.disabled){f.elements.rules.value=[f.elements.rules.value,draft.text].filter(Boolean).join('\n\n');f.dataset.dirty='true';toast('草稿已带入，请核对来源和长度后保存共同方向。');}else toast('草稿已留在团队资料入口，由队长核对方向。');}
      else{await api(endpoint('/reports'),{event_id:'materials-draft:'+draft.canonical_id,summary:draft.text,evidence:['资料入口草稿：'+draft.canonical_id],tool:'资料入口行动草稿',origin:'human',status:'discussion'});await refresh(true);go('tasks');toast('已保存为讨论。仍需生成统筹草案并由队长确认。');}
    });}
    if(token){try{await reload();}catch(e){message(e.message,true);}}else{
      message('未登录内容暂留当前页面，刷新会丢失。登录后可保存原件、读取材料和调用模型。');
      api('/api/studio/sms-status').then(s=>{if(alive()&&!(s.registration_available??s.ready))message('短信注册暂不可用。可以浏览活动；已有账号可用密码登录后保存材料。当前未登录输入仅留本页，刷新会丢失。');}).catch(()=>{});
    }
  }
  return {mount,reset};
})();

function materialsPage(){const c=$('#content');c.innerHTML=head('实践 / 统一资料入口','一起收下，把事情理清楚。',state.team?'这里是团队共享材料；个人草稿仍保存在自己的空间。':'先整理自己的材料，选择共享后团队才能看到。')+'<div id="materials-host"></div>';SongbanMaterials.mount($('#materials-host'),{teamId:state.team});}
