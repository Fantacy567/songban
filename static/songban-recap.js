'use strict';
let recapRequest=null;
function recapReportBody(report){const body=report.body;return `<p>${esc(body.summary||'')}</p><h3>比赛结果 · 本人填写</h3><p>${esc(body.result_note||'尚未提供')}</p><p class="caption">尚未经主办方核实，名次不代表个人能力。</p>${(body.observations||[]).map(item=>`<article class="recap-observation"><h3>${esc(item.title)}</h3><p>${esc(item.text)}</p><p class="caption">依据 ${item.source_ids.length} 条本人记录；这是待结合实际交流核对的解读。</p></article>`).join('')}<h3>下一次可以尝试</h3><ul>${(body.next_steps||[]).map(text=>`<li>${esc(text)}</li>`).join('')}</ul><h3>还不了解的部分</h3><ul>${(body.limitations||[]).map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`;}
async function recapPage(){
 const host=$('#content'),team=state.team,epoch=state.epoch;
 host.innerHTML=head('赛后复盘','这次比赛，你想留下什么？','先写下自己的感悟，再结合真实记录整理一份给家长看的报告。')+'<p class="notice" role="status">正在读取你的复盘…</p>';
 const alive=()=>epoch===state.epoch&&state.team===team&&host.isConnected;
 try{
  const data=await api(endpoint('/recap'));if(!alive())return;
  const reflection=data.reflection,latest=data.reports[0],ready=data.reports.find(report=>report.status==='ready');
  host.innerHTML=head('赛后复盘','这次比赛，你想留下什么？','你的感悟、比赛结果和本人的工作记录，会成为报告的依据。')+`<form class="card" id="personal-recap"><h2>先由你自己说</h2><input type="hidden" name="expected_version" value="${data.version}"><label for="recap-feelings">这次比赛有什么感悟？</label><textarea id="recap-feelings" name="feelings" maxlength="3000" required rows="4" placeholder="哪一刻最难忘？遇到了什么困难？你怎么处理的？">${esc(reflection.feelings||'')}</textarea><label for="recap-ideas">还有什么想法，或者下次想尝试的事？</label><textarea id="recap-ideas" name="ideas" maxlength="3000" rows="3" placeholder="也可以写对队伍合作、AI使用或作品的想法。">${esc(reflection.ideas||'')}</textarea><label for="recap-result">这次比赛的结果</label><textarea id="recap-result" name="result" maxlength="1500" required rows="2" placeholder="例如：完成展示，获得优秀作品奖；还没公布结果也可以如实写。">${esc(reflection.result||'')}</textarea><p class="caption">这是你自己的复盘，不会自动发到团队或家长端。比赛结果会标注为本人填写、尚未核实。</p><button type="submit" class="primary">保存我的复盘</button></form><section class="card"><h2>让 AI 结合真实经历整理</h2><p>${esc(data.notice)}</p><p class="caption">生成会调用平台配置的模型。模型不可用时，复盘仍然保留。报告只描述本场表现，不给孩子下性格或天赋结论。</p><button class="primary" id="generate-recap" ${!data.version?'disabled':''}>${latest?'根据当前记录生成新报告':'生成报告草稿'}</button><div id="recap-message" role="status"></div>${latest&&latest.status!=='ready'?`<p class="notice">${latest.status==='running'?'上次生成尚无最终结果，请刷新查看；不会自动重复调用。':esc(latest.error||'报告尚未完成，复盘已保存。')}</p>`:''}</section>${ready?`<section class="card" id="recap-preview"><div class="row spread"><h2>先看看这份报告</h2><span class="tag">${ready.share?'已分享':'仅本人预览'}</span></div><p class="caption">${esc(ready.created_at)} · ${esc(ready.model_id)} · 本次依据 ${ready.source_count} 条记录${ready.reflection_version!==data.version?' · 复盘已更新，请重新生成再分享':''}</p>${recapReportBody(ready)}<div class="divider"></div><label class="recap-consent"><input type="checkbox" id="confirm-parent-share"><span>我已预览，同意将这份 AI 整理报告分享给家长。持有二维码的人均可查看，30天有效；不包含完整聊天与队友原文。</span></label><div class="action-row"><button id="share-recap" class="primary">${ready.share?'重新生成二维码（旧码失效）':'确认并生成家长二维码'}</button>${ready.share?'<button id="revoke-recap">撤销这份分享</button>':''}</div><div id="parent-qr">${ready.share?shareMarkup(ready.share):''}</div><div id="share-message" role="status"></div></section>`:''}`;
  restoreDrafts();
  bindForm('#personal-recap',async(form,fd)=>{
   const fields=values(fd);await api(endpoint('/recap'),{...fields,expected_version:Number(fields.expected_version)},'PUT');
   form.dataset.dirty='false';state.drafts.delete(team+':personal-recap');recapRequest=null;await recapPage();toast('你的感悟和比赛结果已保存。');
  });
  $('#generate-recap').onclick=async event=>{
   const message=$('#recap-message');if($('#personal-recap').dataset.dirty==='true'){message.textContent='请先保存刚写的感悟，再生成报告。';return;}
   event.target.disabled=true;message.textContent='正在对照本人的感悟和工作记录生成报告，请稍候…';
   const key=team+':'+data.version+':'+epoch;
   if(recapRequest?.key!==key)recapRequest={key,id:crypto.randomUUID()};
   try{
    const report=await api(endpoint('/recap/reports'),{request_id:recapRequest.id,expected_version:data.version});if(!alive())return;
    recapRequest=null;await recapPage();toast(report.status==='ready'?'报告草稿已保存，请预览后决定是否分享。':report.error||'上次生成还在处理，请稍后刷新。');
   }catch(error){if(alive()){message.textContent=error.message;event.target.disabled=false;}}
  };
  if(ready){
   $('#share-recap').onclick=async event=>{
    const message=$('#share-message');if(!$('#confirm-parent-share').checked){message.textContent='请先预览报告并勾选分享确认。';return;}
    event.target.disabled=true;
    try{await api(endpoint('/recap/reports/'+ready.id+'/share'),{confirmed:true});if(alive()){await recapPage();toast('家长二维码已生成，请只发给希望查看的家长。');}}catch(error){if(alive()){message.textContent=error.message;event.target.disabled=false;}}
   };
   if($('#revoke-recap'))$('#revoke-recap').onclick=async()=>{try{await api(endpoint('/recap/reports/'+ready.id+'/share'),null,'DELETE');if(alive()){await recapPage();toast('分享已撤销，原二维码无法再打开。');}}catch(error){toast(error.message);}};
  }
 }catch(error){if(alive())host.innerHTML=head('赛后复盘','复盘暂时未能读取。','已保存的内容会保留，稍后可重新打开。')+`<p class="error">${esc(error.message)}</p><button id="retry-recap">重新读取</button>`;if($('#retry-recap'))$('#retry-recap').onclick=recapPage;}
}
function shareMarkup(share){return `<div class="parent-qr-card"><img src="${esc(share.qr_url)}" width="240" height="240" alt="家长扫描此二维码查看已确认的AI报告"><div><h3>把这次经历，分享给家长</h3><p>家长扫码可直接阅读，不需要你的账号。</p><p class="caption">到期时间：${esc(share.expires_at)}。若当前为局域网地址，手机需连接同一 Wi-Fi。</p><a href="${esc(share.url)}" target="_blank" rel="noreferrer">打开家长报告</a><p class="caption wrap">${esc(share.url)}</p><a href="${esc(share.qr_url)}" download="松伴-家长报告二维码.svg">下载二维码</a></div></div>`;}
