'use strict';
// Server owns phases, votes and claims. This view never derives a winning direction.
const SongbanTopics = (() => {
  function operationBody(scope, action, fields) {
    const key='songban:topics:'+scope+':'+action;
    let body;try{body=JSON.parse(sessionStorage.getItem(key));}catch{}
    if(!body){body={request_id:crypto.randomUUID(),...fields};sessionStorage.setItem(key,JSON.stringify(body));}
    return {key,body};
  }
  async function perform(url, scope, action, fields) {
    const pending=operationBody(scope,action,fields);
    try {const result=await api(url,pending.body);sessionStorage.removeItem(pending.key);return result;}
    catch(error){if(error.status && error.status<500)sessionStorage.removeItem(pending.key);throw error;}
  }
  function reset(){for(const key of Object.keys(sessionStorage))if(key.startsWith('songban:topics:'))sessionStorage.removeItem(key);}
  function installMarkup(){return `<details class="card topic-install"><summary>① 连接自己的 Agent · 安装松伴连接器</summary><p>每位成员用自己的账号安装。选题期间，选择连接器或明确授权当前对话后，本回合的用户发言和 AI 可见回复会共享给全队。</p><form id="topic-install-form"><label for="topic-tool">我使用的工具</label><select id="topic-tool" name="tool"><option value="connector-plugin">Codex · 松伴连接器原生插件</option><option value="cursor">Cursor · 项目 MCP 连接</option><option value="workbuddy">WorkBuddy · 项目 MCP 连接</option></select><div id="topic-project-field" hidden><label for="topic-project">当前项目文件夹的完整路径</label><input id="topic-project" name="project_dir" disabled></div><p class="muted" id="topic-install-help">Codex 安装后在插件入口选择「松伴连接器」；当前对话可能需要重新打开才能加载。</p><label class="topic-consent"><input type="checkbox" name="consent" required>允许配置本人连接；仅共享我选择或授权的当前选题对话</label><button type="submit" class="primary" disabled>一键安装并绑定本人团队</button><p id="topic-install-capability" class="muted">正在检测本机安装能力…</p></form><div id="topic-install-result" role="status"></div><p><a href="#/tools">查看连接状态、撤销授权或下载通用插件</a></p></details>`;}
  async function mount(host,d){
    const epoch=state.epoch,team=state.team,scope=d.me.id+':'+team;
    const base='/api/core/teams/'+encodeURIComponent(team)+'/topic-selection';
    const alive=()=>host.isConnected&&epoch===state.epoch&&state.team===team&&state.page==='direction';
    const q=s=>host.querySelector(s);let round=null,busy=false,timer;
    function message(value){if(alive())q('#topic-message').textContent=value;}
    async function mutate(action,fields){
      if(busy)return;busy=true;state.busy=true;
      const buttons=[...host.querySelectorAll('[data-topic-action],#topic-start button')].map(b=>[b,b.disabled]);buttons.forEach(([b])=>b.disabled=true);
      try{
        await perform(base+'/'+action,scope,action+(fields.ballot?':'+fields.ballot:'')+(fields.candidate_id?':'+fields.candidate_id:''),
          {expected_revision:round?.revision??d.revision,...fields});
        if(!alive())return;
        if(action==='rounds'){q('#topic-start')?.setAttribute('data-dirty','false');state.drafts.delete(team+':topic-start');}
        await read(true);
        await refresh(true);
      }catch(error){message(error.message);if(alive())await read(false);}
      finally{busy=false;state.busy=false;if(alive())buttons.forEach(([b,disabled])=>b.disabled=disabled);}
    }
    function candidateName(id){return round.candidates.find(c=>c.id===id)?.title||'未知选题';}
    function draw(){
      const r=round,cap=d.me.captain;
      const phase=r?.phase||'start';
      const step={start:0,discussion:1,ranking:2,failed:2,unknown:2,voting:3,awaiting_selection:3,selected:4}[phase];
      host.innerHTML=`<div class="hero"><div><div class="eyebrow">TEAM DIRECTION</div><h1>先各自聊透，再一起选定。</h1><p>连接个人 Agent → 共享讨论 → 全员确认 → 排名与投票 → 领取任务</p></div><a href="#/team">邀请队友</a></div><ol class="topic-steps" aria-label="选题流程">${['开启讨论','个人讨论与确认','团队排名','全员投票','主方向已定'].map((s,i)=>`<li ${step===i?'aria-current="step"':''} class="${step>=i?'reached':''}"><span>${i+1}</span>${s}</li>`).join('')}</ol><p id="topic-message" role="status" aria-live="polite"></p>${!r?`<section class="card"><h2>先给每个人一点想清楚的时间</h2><p>队长开启讨论时段后，每个人连接自己的 Agent，分享选题回合。队长口头核对上传是否完成，再由每个人亲自确认。全员确认会触发一次团队模型排名，可能消耗模型额度。</p>${cap?`<form id="topic-start"><label for="topic-track">本次赛道 / 讨论范围</label><input id="topic-track" name="track" required maxlength="1000" placeholder="例如：让校园生活更方便的 AI 应用"><label for="topic-minutes">选题讨论时间（分钟）</label><input id="topic-minutes" name="minutes" type="number" min="5" max="180" value="20" required><label>赛事要求<textarea name="rules" maxlength="12000" placeholder="粘贴主办方原文；未知就留空">${esc(d.direction.rules)}</textarea></label><label>评分依据<textarea name="rubric" maxlength="4000" placeholder="真实评审维度；未知就留空">${esc(d.direction.rubric)}</textarea></label><button type="submit" class="primary">开启选题讨论</button></form>`:'<p class="notice">等待队长开启讨论。可以先到成员页补充自己的优势和可用时间。</p>'}</section>`:thisRound(r,cap)}${phase==='start'||phase==='discussion'?installMarkup():''}`;
      if(q('#topic-start')){
        const form=q('#topic-start');const saved=state.drafts.get(team+':topic-start');
        if(saved){for(const [k,v] of saved)if(form.elements[k])form.elements[k].value=v;form.dataset.dirty='true';}
        form.onsubmit=e=>{e.preventDefault();const f=Object.fromEntries(new FormData(form));f.minutes=Number(f.minutes);void mutate('rounds',f);};
      }
      host.querySelectorAll('[data-topic-action]').forEach(b=>b.onclick=()=>{
        const action=b.dataset.topicAction;
        if(action==='ready')void mutate('ready',{complete:b.dataset.complete==='true'});
        if(action==='votes')void mutate('votes',{candidate_id:b.dataset.candidate,ballot:r.ballot});
        if(action==='select')void mutate('select',{candidate_id:r.winner_id});
        if(action==='reopen'&&window.confirm('重新开放 20 分钟并清空全员确认和当前排名？已上传讨论会保留，所有成员需要重新确认。'))void mutate('reopen',{minutes:20});
        if(action==='retry'&&(r.phase!=='unknown'||window.confirm('上次请求结果未知，再试可能重复消耗模型额度。确认重新请求排名？')))void mutate('retry',{acknowledge_unknown:r.phase==='unknown'});
      });
      if(q('#topic-install-form'))bindInstall();
    }
    function thisRound(r,cap){
      const me=r.members.find(m=>m.id===d.me.id),ended=Date.parse(r.deadline)<=Date.now();
      const discussion=r.phase==='discussion',disabled=r.roster_changed;
      let result=`<section class="card topic-status"><div class="row spread"><div><h2>${esc(r.track)}</h2><p>讨论截止：${esc(new Date(r.deadline).toLocaleString('zh-CN',{hour12:false}))}${ended?' · 上传时段已结束':''}</p></div><div class="topic-count"><strong data-testid="topic-confirmed">${r.confirmed_count}/${r.member_count}</strong><span>已确认人数 / 总人数</span></div></div><div class="topic-members">${r.members.map(m=>`<article><strong>${esc(m.name)}</strong><span>已上传 ${m.shared_turns} 个回合</span><span class="tag ${m.confirmed?'green':''}">${m.confirmed?'已确认':'待本人确认'}</span></article>`).join('')}</div>${discussion?`<p>先核对下方上传记录。队长口头确认大家上传完毕后，每位成员点击确认；最后一人确认后会自动生成排名。补充上传会撤回本人的确认。</p><div class="action-row"><button class="primary" data-topic-action="ready" data-complete="${!me?.confirmed}" ${!me?.shared_turns?'disabled':''}>${me?.confirmed?'撤回本人的确认':'确认进入排名'}</button><a href="#/members">完善我的能力与时间</a></div>${!me?.shared_turns?'<p class="notice">还没有收到你的回合。请先连接 Agent 并共享至少一个选题回合。</p>':''}`:''}${r.roster_changed?'<p class="error">成员或能力资料已改变，旧排名不能继续使用。请队长重新开放讨论，让当前成员重新确认。</p>':''}${cap&&r.phase!=='selected'?'<button class="ghost" data-topic-action="reopen">重新开放讨论 · 重置确认</button>':''}</section>`;
      if(['ranking','failed','unknown'].includes(r.phase))result+=`<section class="card" role="status"><h2>${r.phase==='ranking'?'团队 Agent 正在评估全部选题…':'排名暂未完成'}</h2><p>${esc(r.error||'从团队能力、赛道、特殊优势、评分依据和实现可行性逐项评估。结果准备好后会在这里显示。')}</p>${cap&&r.phase!=='ranking'?`<button data-topic-action="retry" ${disabled?'disabled':''}>${r.phase==='unknown'?'确认结果未知并重试排名':'重试排名'}</button>`:''}</section>`;
      if(r.ranking){result+=`<section class="card"><h2>团队评估排名</h2><p>${esc(r.ranking.summary)}</p><p class="muted">${r.ranking.mode==='fixture'?'协议测试替身 · 非真实模型评估':'模型建议 · 最终方向由全员投票决定'} · 实际返回模型：${esc(r.ranking.actual_model||'未提供')}</p>${r.ranking.coverage.truncated_turns?`<p class="notice">共 ${r.ranking.coverage.turns} 个回合，其中 ${r.ranking.coverage.truncated_turns} 个仅用摘录评估；完整原文保留在下方。</p>`:''}</section><div class="topic-ranking">${r.ranking.items.map(item=>`<article class="card"><div class="row spread"><span class="tag">建议第 ${item.rank} 名</span><span>${esc(name(r.candidates.find(c=>c.id===item.candidate_id)?.user_id))}</span></div><h3>${esc(candidateName(item.candidate_id))}</h3><dl>${Object.entries(r.dimensions).map(([k,label])=>`<dt>${esc(label)}</dt><dd>${esc(item.dimensions[k])}</dd>`).join('')}</dl>${[['advantages','优势'],['risks','可能的问题'],['verification','待验证']].map(([key,title])=>`<h4>${title}</h4><ul>${item[key].map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`).join('')}<p class="caption">依据：${item.source_ids.map(id=>id.startsWith('member:')?esc(name(id.slice(7))):esc(id)).join('、')}</p>${r.phase==='voting'&&r.eligible.includes(item.candidate_id)?`<button class="primary" data-topic-action="votes" data-candidate="${esc(item.candidate_id)}" ${r.my_vote||disabled?'disabled':''}>${r.my_vote===item.candidate_id?'本轮已投此选题':'投这个方向一票'}</button>`:''}</article>`).join('')}</div>`;}
      if(['voting','awaiting_selection','selected'].includes(r.phase))result+=`<section class="card topic-vote"><h2>${r.phase==='selected'?'主方向已确认':r.phase==='awaiting_selection'?'全员已投票，等待队长确认':'每人一票，选出共同方向'}</h2><p data-testid="topic-voted">第 ${r.ballot} 轮 · 已投 ${r.votes_count}/${r.member_count} 人</p>${r.previous_tie?`<p class="notice">上一轮最高票并列，本轮仅对 ${r.eligible.map(candidateName).map(esc).join('、')} 重投。每人重新投一票。</p>`:''}${r.my_vote?`<p>你本轮选择：${esc(candidateName(r.my_vote))}。本轮不能重复投票。</p>`:''}${r.tallies?`<ul>${Object.entries(r.tallies).map(([id,count])=>`<li>${esc(candidateName(id))}：${count} 票</li>`).join('')}</ul>`:'<p class="muted">全员投完后公布票数，平票只对并列最高项重投。</p>'}${r.winner_id?`<h3>${esc(candidateName(r.winner_id))}</h3>`:''}${r.phase==='awaiting_selection'&&cap?`<button class="primary" data-topic-action="select" ${disabled?'disabled':''}>确认最高票方向，进入任务领取</button>`:''}${r.phase==='selected'?`<p>队长到任务页生成并发布任务，成员按能力与时间领取。AI 建议的负责人只作参考。</p><a class="primary" href="#/tasks">${d.plan_version?'去领取任务':'去生成任务清单'}</a>`:''}</section>`;
      result+=`<section class="card"><h2>每个人和 AI 的选题讨论</h2><p>以下为成员选中并共享的回合。模型名称未知会留空；事实与建议仍需核实。</p>${r.candidates.length?r.candidates.map(c=>`<details class="topic-source"><summary>${esc(name(c.user_id))} · ${esc(c.title)} · ${c.turns.length} 个回合</summary>${c.turns.map(t=>`<article><p class="caption">${esc(new Date(t.created_at).toLocaleString('zh-CN'))} · 模型 ${esc(t.model_name||'未知')}${t.redacted?' · 已隐藏疑似密钥':''}</p><h4>成员原话</h4><pre>${esc(t.user_message)}</pre><h4>AI 可见回复</h4><pre>${esc(t.assistant_message)}</pre><small>回合记录 ${esc(t.id)}</small></article>`).join('')}</details>`).join(''):'<p class="empty">还没有上传的讨论。安装连接器后，在个人 Agent 中选用它开始聊选题。</p>'}</section>`;
      return result;
    }
    async function bindInstall(){
      const form=q('#topic-install-form'),tool=q('#topic-tool'),folder=q('#topic-project');
      tool.onchange=()=>{const native=tool.value==='connector-plugin';q('#topic-project-field').hidden=native;folder.disabled=native;folder.required=!native;q('#topic-install-help').textContent=native?'安装后在 Codex 插件入口选择「松伴连接器」；当前对话可能需要重新打开才能加载。':'写入当前项目的 MCP 配置。请在所选工具打开该项目，启用 songban-team，并明确要求共享当前选题对话。MCP 配置成功不表示加号菜单里已有原生插件。';};
      form.onsubmit=async e=>{
        e.preventDefault();if(busy)return;busy=true;state.busy=true;
        const button=form.querySelector('button');button.disabled=true;
        try{
          const result=await api('/api/core/teams/'+encodeURIComponent(team)+'/install',{tool:tool.value,...(folder.disabled?{}:{project_dir:folder.value}),consent:true});
          if(!alive())return;
          q('#topic-install-result').innerHTML=`<div class="notice"><strong>配置已安装，团队绑定已验证。</strong><p>${esc(result.notice)}</p><p>下一步：在个人工具中启用连接器，共享一个回合，再回这里核对实际上传记录。</p></div>`;
          form.dataset.dirty='false';
        }catch(error){if(alive())q('#topic-install-result').textContent=error.message;}
        finally{busy=false;state.busy=false;button.disabled=false;}
      };
      try{const options=await api('/api/core/install-options');if(!alive()||!form.isConnected)return;folder.value=options.project_dir;q('#topic-install-capability').textContent=options.notice;form.querySelector('button').disabled=!options.available;}catch(error){if(alive())message(error.message);}
    }
    async function read(force){
      try{const data=await api(base);if(!alive())return;
        const changed=!round||data.round?.revision!==round.revision||data.round?.phase!==round.phase||data.round?.roster_changed!==round.roster_changed;
        if(force||changed&&!host.querySelector('form[data-dirty="true"]')){round=data.round;draw();}
      }catch(error){if(alive()){if(!q('#topic-message'))host.innerHTML='<p id="topic-message" role="alert"></p>';message(error.message);}}
    }
    await read(true);
    async function poll(){if(!alive())return;if(!busy&&!document.hidden)await read(false);timer=setTimeout(poll,5000);}
    timer=setTimeout(poll,5000);
  }
  function mountClaims(host,d){
    const list=(d.active_plan.tasks||[]).filter(t=>t.claim_required&&!t.owner_id);
    if(!list.length)return;
    const team=state.team,epoch=state.epoch,scope=d.me.id+':'+team;
    host.innerHTML=`<section class="card topic-claims"><h2>领取团队任务</h2><p>先核对检查方法与前置依赖，再选择适合自己的任务。建议负责人不等于已领取。</p>${list.map(t=>`<article><h3>${esc(t.key)} · ${esc(t.title)}</h3><p>检查方法：${esc(t.acceptance)}</p><p class="muted">建议成员：${esc(name(t.suggested_owner_id))} · 前置任务：${esc(t.depends_on.join('、')||'无')}</p><button class="primary" data-claim-task="${esc(t.key)}">领取这项任务</button></article>`).join('')}<p class="topic-claim-message" role="status"></p></section>`;
    host.querySelectorAll('[data-claim-task]').forEach(b=>b.onclick=async()=>{
      b.disabled=true;try{
        await perform('/api/core/teams/'+encodeURIComponent(team)+'/tasks/'+encodeURIComponent(b.dataset.claimTask)+'/claim',scope,'claim:'+d.plan_version+':'+b.dataset.claimTask,{expected_revision:d.revision});
        if(epoch===state.epoch&&team===state.team){toast('已领取，个人工具会读取到这项任务。');await refresh(true);}
      }catch(error){if(host.isConnected)host.querySelector('.topic-claim-message').textContent=error.message;b.disabled=false;}
    });
  }
  return {mount,mountClaims,reset};
})();
