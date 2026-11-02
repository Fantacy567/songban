/* P5-A local storyboard. Never import this into the production application. */
(() => {
  'use strict';
  const key = 'songban-p5-storyboard-v1';
  const main = document.querySelector('main'), role = document.querySelector('#role'), scenario = document.querySelector('#scenario');
  const blank = (name = 'normal') => ({ v:1, role:'parent', scenario:name, order:'none', claimed:false, refund:'none', expired:false, grants:0, ledger:0, refundEntries:0, report:false, message:'' });
  function fixture(name) {
    const s = blank(name);
    if (['paused','expired','refund_unknown'].includes(name)) Object.assign(s,{order:'verified',grants:1,ledger:1,report:true});
    if (name === 'expired') s.expired = true;
    if (name === 'refund_unknown') s.refund = 'unknown';
    return s;
  }
  let state = blank();
  try {
    const s = JSON.parse(sessionStorage.getItem(key));
    if (s?.v === 1 && ['parent','staff','child'].includes(s.role) && ['none','pending','verified','closed','refunded'].includes(s.order) && [...scenario.options].some(o=>o.value===s.scenario)) state = s;
  } catch { /* Unsupported local storage starts a fresh fictional walkthrough. */ }
  function save() { try { sessionStorage.setItem(key,JSON.stringify(state)); } catch { document.querySelector('#notice').textContent = '本地暂存不可用，关闭页面后会重置；没有真实数据受到影响。'; } }
  function message(text) { state.message = text; render(); }
  function hasOrder() { return state.order !== 'none'; }
  function historyVisible() { return state.ledger > 0; }
  const summary = () => `<aside class="stack"><section class="card"><span class="tag">服务范围已确认 · 暂不开售</span><h2>做出第一张活动邀请卡</h2><p>孩子做选择、修改和检查，留下自己的作品与解释。</p><dl class="facts"><div><dt>主题与关卡</dt><dd>1个主题 · 3关</dd></div><div><dt>练习安排</dt><dd>2次 × 约30分钟</dd></div><div><dt>人工答疑</dt><dd>2次 × 至多10分钟</dd></div><div><dt>家长报告</dt><dd>1份 · 审核后提供</dd></div></dl><p class="price">¥99 <small>虚构金额，非报价</small></p><p class="muted">正式价格、日期、人员、退款和保留规则尚未确定，不能据此报名付款。</p><details><summary>看已确认的准备范围</summary><p>服务期7天，送审后3个工作日反馈，已确认用于准备。实际日期、起算规则、工作日历、负责人和名额仍待配置。</p><p>到期后如何保留历史、部分交付如何退款，需在正式报价版本中说明。</p></details></section><section class="card"><h3>已有流程保持原样</h3><p class="muted">孩子依旧从当前任务进入三关；比赛、组队和连接器仍在黑客松里。</p></section></aside>`;
  function history() {
    if (!historyVisible()) return '';
    return `<section class="card history"><span class="pill">虚构历史样本</span><h2>已经留下的作品</h2><p>小禾 · 班级读书分享会邀请卡 · 第2版</p><p>“我补上了活动结束时间，把地点写成了图书角，并核对同学需要带一本喜欢的书。”</p><details><summary>查看虚构作品内容</summary><p>周六14:00—15:00，我们在图书角举办读书分享会。请带一本喜欢的书，一起分享你最喜欢的一页。</p></details><p class="muted">${state.report ? '示例报告：已发布，按有效授权只读。' : '报告：尚未发布，家长不能查看草稿。'} 到期或退款不会在原型中删除这些虚构记录；正式保留时限待确认。</p></section>`;
  }
  function orderCard() {
    const labels = {pending:'等待到账核验',verified:state.expired?'课程服务已到期':'课程服务已开通',closed:'本次订单已关闭',refunded:'已登记核实退款结果'};
    let body = `<section class="card"><span class="tag">示例订单 DEMO-001</span><h2>${labels[state.order]}</h2><p class="muted">小禾 · 示例报价版本 DEMO-OFFER-1 · ¥99（虚构）</p>`;
    if (state.order === 'pending') body += `<div class="status"><strong>${state.claimed?'已记录付款声明，仍未确认到账':'还没有已核实的到账记录'}</strong>只有工作人员核对实际渠道记录后，才能开通课程权益。</div><p>此原型没有真实付款方式，不要转账或上传银行卡信息。</p><div class="actions"><button class="primary" id="claim" ${state.claimed?'disabled':''}>模拟提交付款声明</button><button id="close">关闭未核验的示例订单</button></div>`;
    if (state.order === 'verified') {
      const refundLabel={requested:'退款申请已记录',approved:'退款申请已批准，尚未办理完成',processing:'已登记办理，等待渠道结果',unknown:'退款结果待核对'};
      body += `<div class="status"><strong>${refundLabel[state.refund]||(state.expired?'新的练习已暂停':'下一步：约定练习时间')}</strong>${state.refund!=='none'?'尚无确认结果，不重复办理、不声称已退款。':state.expired?'已有作品和报告按有效授权与保留规则读取。':'此处将展示本人约定时段和真实负责人员。当前均未配置。'}</div>`;
      body += `<ol class="timeline"><li>课程权益：${state.expired?'已到期':'示例已开通'}，人工支持示例剩余2次。</li><li>孩子进入现有三关练习，保存并修改作品。</li><li>明确送审后老师复核，再单独发布家长报告。</li></ol><div class="actions">${state.refund==='none'?'<button id="request-refund">模拟申请退款</button>':''}</div>`;
    }
    if (state.order === 'refunded') body += `<p>本状态只演示“已有渠道确认结果”的登记；本页面没有执行退款。对应示例权益已撤销，原学习记录保留。</p>`;
    if (state.order === 'closed') body += `<p>关闭订单没有退款，也没有发放权益。如果已付款但尚未核验，需要人工异常核对。</p>`;
    return body + '</section>';
  }
  function parent() {
    let primary = '';
    if (hasOrder()) primary = orderCard();
    else if (state.scenario === 'unverified') primary = `<section class="card accent"><h2>先为孩子做好准备</h2><p>监护关系和学习用途尚未确认。完成获准的关系核验与同意后再报名，付款不能代替授权。</p><button disabled>请先完成监护准备</button></section>`;
    else if (state.scenario === 'full') primary = `<section class="card accent"><h2>本期名额已满</h2><p>新订单暂不创建，避免报名后无法得到承诺的支持。</p><button disabled>本期暂不可报名</button></section>`;
    else primary = `<section class="card accent"><span class="tag">小禾的课程与服务</span><h2>从一个小作品开始</h2><p>把想法说清楚，自己操作，再检查哪里可以更好。</p><ol class="steps"><li><b>01 说清要求</b>读懂材料，作出选择</li><li><b>02 操作与保存</b>留下自己的作品</li><li><b>03 检查与解释</b>修改并说出理由</li></ol><label class="choice"><input id="terms" type="checkbox"><span>我已阅读示例服务说明，知道这是没有真实付款的演示。</span></label><button class="primary" id="create" disabled>模拟创建待核验订单</button><p class="muted">生成订单不等于付款，也不自动确认监护关系。</p></section>`;
    return `<div class="intro"><p class="eyebrow">家长视角 · 课程与服务</p><h1>看清服务，再安排孩子的练习。</h1><p class="muted">${state.scenario==='paused'?'新报名暂时关闭，已有服务、退款核对和历史入口继续保留。':'只展示本人孩子的课程与服务；报告草稿不会出现在这里。'}</p></div><div class="layout"><div class="stack">${primary}${history()}</div>${summary()}</div>`;
  }
  function staff() {
    let actions = '<p>当前没有待处理的示例订单。可先切换家长视角创建。</p>';
    if (state.order === 'pending') actions = `<div class="status"><strong>${state.claimed?'家长已声明付款':'家长尚未声明付款'}</strong>声明不是到款证据；这里的凭据是预置的虚构案例。</div><details open><summary>核对虚构渠道记录</summary><p>引用 DEMO-RECEIPT-01 · 到账 ¥99 CNY · 订单 DEMO-001。正式系统须受控导入、校验金额币种并防止跨订单复用。</p></details><label class="choice"><input id="receipt" type="checkbox"><span>我已核对本页虚构记录与订单一致，仅演示核验动作。</span></label><button class="primary" id="verify" disabled>模拟确认到账并发权益</button>`;
    if (state.order === 'verified') {
      actions = '<div class="status"><strong>示例订单已核验</strong>核验记录与权益应在同一事务中生成，刷新或重复提交不得重复发放。</div><button id="repeat">模拟重复提交原核验</button>';
      if(state.refund==='none') actions+='<p>尚无退款申请。</p>';
      else {
        actions+='<h3>退款处理</h3><p>只有已核实的渠道结果才能登记完成。此处不执行渠道退款；以下均是不同岗位的虚构动作。</p>';
        if(state.refund==='requested') actions+='<p>申请已记录，当前还没有批准或渠道办理记录。</p><button id="refund-approve">模拟批准全额退款申请</button>';
        if(state.refund==='approved') actions+='<p>已模拟批准。实际办理须使用稳定的案件与办理引用；点击此处不转账。</p><button id="refund-start">模拟登记已开始办理</button>';
        if(['processing','unknown'].includes(state.refund)) actions+=`<div class="status"><strong>${state.refund==='unknown'?'退款结果未知':'等待渠道结果'}</strong>固定示例办理号 DEMO-REFUND-01；未知时不重新办理。</div><label class="choice"><input id="refund-evidence" type="checkbox"><span>已核对虚构的全额退款结果，与此订单和办理号一致。</span></label><div class="actions"><button id="refund-unknown">模拟核对：结果未知</button><button id="refund-confirm" disabled>模拟核对：确认退款完成</button></div>`;
      }
    }
    if (state.order === 'refunded') actions = '<p>示例退款确认已留痕，权益已撤销，历史作品仍在。没有调用真实支付渠道。</p><button id="repeat-refund">模拟重复登记原退款结果</button>';
    if (state.order === 'closed') actions = '<p>订单已关闭，不能直接核验发权益。疑似迟到付款须另走异常核对。</p>';
    return `<div class="intro"><p class="eyebrow">工作人员视角 · 受理示意</p><h1>先核对事实，再改变服务状态。</h1><p class="muted">正式后台按岗位与分配限制；本原型视角切换不构成身份验证。</p></div><div class="layout"><section class="card"><h2>报名与核验</h2>${actions}</section><aside class="card"><h2>虚构记录核对</h2><dl class="facts ledger"><div><dt>到账核验记录</dt><dd id="ledger">${state.ledger}</dd></div><div><dt>权益发放记录</dt><dd id="grants">${state.grants}</dd></div><div><dt>退款确认记录</dt><dd id="refund-count">${state.refundEntries}</dd></div></dl><p class="muted">只展示原型计数，不是生产账本，不证明数据库原子性。</p></aside></div>`;
  }
  function child() {
    const active = state.order === 'verified' && !state.expired;
    return `<div class="intro"><p class="eyebrow">孩子视角 · 当前学习</p><h1>${active?'准备做一张邀请卡。':'你的作品，从一个想法开始。'}</h1></div><section class="card accent"><h2>${active?'先想想，你想邀请谁？':'请家长帮你准备好课程。'}</h2><p>${active?'读一读活动材料，说出这张邀请卡要告诉大家的三件事。真实产品会进入已有三关，这里只展示入口文案。':'你可以先告诉松伴自己想做什么。课程安排由家长处理，这里没有购买或付款操作。'}</p><button id="child-next" class="primary">${active?'看看这一关要做什么':'看看我可以从哪里开始'}</button></section>${history()}`;
  }
  function on(id, action) { const el=document.querySelector('#'+id); if(el) el.addEventListener('click',action); }
  function render() {
    role.value=state.role; scenario.value=state.scenario;
    main.innerHTML = state.role==='parent'?parent():state.role==='staff'?staff():child();
    document.querySelector('#notice').textContent=state.message;
    save();
    const terms=document.querySelector('#terms'); if(terms) terms.addEventListener('change',()=>{ document.querySelector('#create').disabled=!terms.checked; });
    const receipt=document.querySelector('#receipt'); if(receipt) receipt.addEventListener('change',()=>{ document.querySelector('#verify').disabled=!receipt.checked; });
    const refundEvidence=document.querySelector('#refund-evidence'); if(refundEvidence) refundEvidence.addEventListener('change',()=>{document.querySelector('#refund-confirm').disabled=!refundEvidence.checked;});
    on('create',()=>{if(state.role!=='parent'||state.scenario!=='normal'||hasOrder()||!terms?.checked)return;state.order='pending';message('示例订单已创建，尚未核实到款，未发放权益。');});
    on('claim',()=>{state.claimed=true;message('只记录了虚构付款声明。请切换工作人员视角查看核验流程。');});
    on('close',()=>{state.order='closed';message('示例订单已关闭，没有执行退款。');});
    on('verify',()=>{if(state.role!=='staff'||state.order!=='pending'||!receipt?.checked)return;state.order='verified';state.ledger=1;state.grants=1;message('已模拟核验与发放各一条记录；真实产品仍需服务端事务验收。');});
    on('repeat',()=>message('已读取原示例核验结果，到账核验和权益发放记录仍各1条。'));
    on('request-refund',()=>{state.refund='requested';message('示例退款申请已记录，没有退款完成结果。');});
    on('refund-approve',()=>{state.refund='approved';message('已模拟批准申请，尚无退款完成记录。');});
    on('refund-start',()=>{state.refund='processing';message('已模拟登记办理号 DEMO-REFUND-01，没有执行真实退款。');});
    on('refund-unknown',()=>{state.refund='unknown';message('结果待核对，未重试退款、未删除已发生用量或历史。');});
    on('refund-confirm',()=>{if(!refundEvidence?.checked||!['processing','unknown'].includes(state.refund))return;state.order='refunded';state.refund='confirmed';state.refundEntries=1;message('已模拟登记一条核实退款结果，示例权益撤销；没有实际转账。');});
    on('repeat-refund',()=>message('读取原示例退款结果，退款确认记录仍为1条。'));
    on('child-next',()=>message('这是学习入口示意。原有起点和三关流程没有被此原型修改。'));
  }
  role.addEventListener('change',()=>{state.role=role.value;state.message='';render();});
  scenario.addEventListener('change',()=>{state=fixture(scenario.value);render();});
  document.querySelector('#reset').addEventListener('click',()=>{state=fixture(state.scenario);state.message='当前情境已重置，只清除本原型的虚构状态。';render();});
  render();
})();
