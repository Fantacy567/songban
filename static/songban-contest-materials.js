'use strict';
async function contestMaterialsPage(){
 const host=$('#content'),epoch=state.epoch;
 const alive=()=>host.isConnected&&epoch===state.epoch&&state.page==='contestMaterials';
 host.innerHTML=head('本场比赛 / 主办方资料','赛事资料，一起理清。','导入公告、补充链接和文件，再提取关键信息。未找到的内容保持未知。')+'<div id="contest-material-intake"></div><section class="card"><h2>提取关键信息</h2><p>关键时间、地点、赛道、奖金、办赛理念，以及评分和提交要求。每条结果都要能找到原文。</p><button class="primary" id="brief-extract" disabled>提取关键信息</button><button id="brief-refresh" type="button">刷新提取状态</button><p id="brief-message" role="status" aria-live="polite"></p><div id="contest-brief-results"></div></section>';
 let brief,space,busy=false;
 const q=s=>host.querySelector(s);
 async function update(data){
  if(!alive())return;space=data;brief=await api('/api/journey/contest-materials');if(!alive())return;
  const result=brief.result,fields=result.fields;if(brief.latest_run&&brief.latest_run.status!=='completed')q('#brief-message').textContent=brief.latest_run.error||'上次提取仍在处理中，请稍后刷新查看。';
  q('#brief-extract').disabled=busy||!space.sources.some(s=>['ready','partial'].includes(s.status));
  q('#contest-brief-results').innerHTML=!fields?'<p class="empty">尚未提取。已确认的公告会自动保留在资料中，也可以继续补充链接和文件。</p>':`${brief.stale?'<p class="notice">资料已变化，下面是上一版结果；请重新提取再确认。</p>':''}<p class="caption">${esc(result.notice)} · 本次读取 ${result.source_count} 份资料</p>${result.excluded.map(x=>`<p class="error">未读到：${esc(x.name)} · ${esc(x.reason)}。该来源未参与提取。</p>`).join('')}${(result.warnings||[]).map(x=>`<p class="notice">${esc(x.name)}：${x.warnings.map(esc).join('；')}</p>`).join('')}<div class="brief-facts">${Object.values(fields).map(field=>`<section class="brief-fact"><h3>${esc(field.label)}</h3>${field.status==='not_found'?'<p class="muted">未找到（仅指本次已读取资料中未找到，不代表主办方没有公布）</p>':field.citations.map(c=>`<blockquote>${esc(c.quote)}</blockquote><details><summary>查看出处：${esc(c.source_name)} · ${esc(c.location)}</summary><p class="pre">${esc(c.quote)}</p><p class="caption">${c.nature==='sample'?'虚构样例':'来源性质尚未独立核实'} · 原件与完整正文可在上方展开查看。</p></details>`).join('')}</section>`).join('')}</div><p class="caption">多份材料若有不同表述会并列保留，请对照主办方最新公告核对。未知项不需要用猜测补齐。</p><button class="primary" id="brief-confirm" ${brief.stale?'disabled':''}>已核对，继续组队</button>`;
  const confirm=q('#brief-confirm');if(confirm)confirm.onclick=async()=>{confirm.disabled=true;try{await api('/api/journey/contest-materials/confirm',{confirmed:true,expected_revision:brief.revision});await load();go('team');}catch(e){if(alive()){q('#brief-message').textContent=e.message;confirm.disabled=false;}}};
 }
 try{
  brief=await api('/api/journey/contest-materials');if(!alive())return;
  q('#brief-refresh').onclick=async()=>{try{await update(await api('/api/materials/spaces/'+encodeURIComponent(brief.space_id)));}catch(e){if(alive())q('#brief-message').textContent=e.message;}};
  await SongbanMaterials.mount(q('#contest-material-intake'),{spaceId:brief.space_id,intakeOnly:true,onChange:update});
  if(!alive())return;
  q('#brief-extract').onclick=async()=>{
   if(busy)return;if(q('#contest-material-intake').getAttribute('aria-busy')==='true'){q('#brief-message').textContent='资料仍在保存或读取，请等本批资料处理完再提取。';return;}busy=true;q('#brief-extract').disabled=true;q('#brief-message').textContent='Agent 正在读取本场已导入资料并逐项核对出处…';
   const key='contest-brief-request:'+brief.contest_id+':'+space.revision;let request=sessionStorage.getItem(key);if(!request){request=crypto.randomUUID();sessionStorage.setItem(key,request);}
   try{const r=await api('/api/journey/contest-materials/extract',{request_id:request,expected_revision:space.revision});if(r.status!=='running')sessionStorage.removeItem(key);if(alive()){await update(await api('/api/materials/spaces/'+encodeURIComponent(brief.space_id)));q('#brief-message').textContent=r.status==='completed'?'提取完成，请对照原文核对；未找到的项目已明确列出。':r.error||'仍在处理中，请稍后刷新查看，系统不会自动重复调用。';}}
   catch(e){if(e.status)sessionStorage.removeItem(key);if(alive())q('#brief-message').textContent=e.message+' 已保存的原件和上一版结果仍保留。';}
   finally{busy=false;if(alive())q('#brief-extract').disabled=false;}
  };
 }catch(e){if(alive())q('#brief-message').textContent=e.message;}
}
