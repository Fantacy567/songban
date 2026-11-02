/* ============================================================ 模拟数据 */

const TEAM = {
  name: "晨光队",
  contest: "2027 青少年 AI 创新挑战赛",
  code: "SONG-3F7Q",
  id: "tm_9f3c21",
  revision: 3,
  updated: "2027-03-02 20:14"
};

const DIRECTION = {
  goal: "四周内做出一个能演示的「校园午餐排队预测器」，并完成一次正式提交。\n判定标准：三条队列能显示真实来源的数据，路演时能讲清为什么这样设计。",
  rules: "提交要求（主办方原文摘录）：\n1. 可运行的作品链接\n2. 三分钟以内的演示视频\n3. 项目说明文档（含截图）\n4. 团队分工说明",
  rubric: "问题真实性 30% · 完成度 30% · 表达能力 25% · 技术 15%\n评委特别提示：反对把可选项做成必须项。",
  nonGoals: "现场答辩准备（等主办方另行通知）\n多语言支持\n后台管理系统\n任何登录与支付功能",
  deadline: "2027-03-15T18:00"
};

const MEMBERS = [
  { name: "林知远", role: "队长", initial: "林", strengths: "前端、路演、把想法画成图", willing: "想把路演讲顺，愿意上台", hours: 6 },
  { name: "周雨桐", role: "成员", initial: "周", strengths: "数据整理、写说明文档", willing: "愿意做数据和文档，不想碰接口", hours: 5 },
  { name: "陈子墨", role: "成员", initial: "陈", strengths: "接口、爬虫、调试", willing: "想练真实数据接入", hours: 4 }
];

const REPORTS = [
  {
    id: "r1", who: "林知远", initial: "林", tool: "Codex", model: "deepseek-v4-pro",
    status: "进行中", time: "03-02 19:40",
    now: "页面骨架已经搭好，三条队列能渲染。数据先用了模拟值，等真实来源。",
    view: "现在最该做的是把页面做完整，数据晚点再说。",
    target: "页面与演示",
    evidence: "页面可正常打开，三条队列渲染正常；截图在项目 /docs/shots 下。"
  },
  {
    id: "r2", who: "周雨桐", initial: "周", tool: "WorkBuddy", model: "claude-sonnet",
    status: "讨论", time: "03-02 19:52",
    now: "看了赛规和评分依据，担心「问题真实性」这 30 分拿不到。",
    view: "现在的瓶颈是数据来源。学校没有开放接口，建议先用问卷收集一周的排队时长，再手工录入。",
    target: "数据来源",
    evidence: "无实测依据，只是判断。"
  },
  {
    id: "r3", who: "陈子墨", initial: "陈", tool: "Cursor", model: "deepseek-v4-pro",
    status: "受阻", time: "03-02 20:05",
    now: "试着请求了食堂菜单页，返回 200，但没确认过有没有排队时长字段。",
    view: "数据来源不是瓶颈，我可以直接抓公开的食堂菜单页，今天就能跑通。",
    target: "数据来源",
    evidence: "仅有一次手动请求记录，未记录返回字段。"
  }
];

const CONFLICT = {
  question: "数据来源到底是不是瓶颈？",
  a: { who: "周雨桐", text: "建议先用问卷收集一周的排队时长，再手工录入。", tool: "WorkBuddy" },
  b: { who: "陈子墨", text: "可以直接抓公开的食堂菜单页，今天就能跑通。", tool: "Cursor" }
};

const PROPOSAL = {
  version: 3,
  reason: "两条观点对「数据来源」的判断相反，且都没有提供实测依据。按赛规「问题真实性 30%」，先验证数据可得性，再扩功能；不替任何一方站队。",
  pending: [
    "食堂菜单页是否真的含排队时长字段（陈子墨的返回记录里没有字段清单）",
    "问卷回收一周是否来得及（截止 03-15，剩 13 天）"
  ],
  tasks: [
    { key: "T-01", title: "验证数据可得性：菜单页到底有没有排队字段", owner: "陈子墨", dep: "无", check: "请求返回 200 且响应里含排队时长字段；若没有，明确记录“无该字段”并截图。" },
    { key: "T-02", title: "问卷设计与投放", owner: "周雨桐", dep: "T-01", check: "10 份有效回收，且每份含日期与等待时长。" },
    { key: "T-03", title: "页面接入真实数据", owner: "林知远", dep: "T-01", check: "三条队列的数据来自真实文件，页面上标注数据日期。" }
  ]
};

const LIBRARY = [
  { who: "林知远", tool: "Codex", model: "deepseek-v4-pro", time: "03-02 19:40",
    original: "页面骨架搭好了，三条队列能渲染，数据先用模拟值。", reply: "建议先补齐「数据日期」标注，再做视觉细节。" },
  { who: "周雨桐", tool: "WorkBuddy", model: "claude-sonnet", time: "03-02 19:52",
    original: "学校没有开放接口，是不是先用问卷收一周数据？", reply: "问卷可行，但要先确认回收周期是否赶上 03-15。" },
  { who: "陈子墨", tool: "Cursor", model: "deepseek-v4-pro", time: "03-02 20:05",
    original: "菜单页返回 200，我直接抓就行。", reply: "返回 200 不代表有排队字段，建议先打印字段清单。" }
];

const CONNECTIONS = [
  { label: "Codex · 晨光队项目", tool: "Codex", state: "可连接", last: "03-02 20:05", token: "sbconn_••••••••7f2a", exp: "2027-04-01" }
];

/* ============================================================ 状态 */

const PAGES = [
  { id: "scene", name: "团队现场" },
  { id: "direction", name: "统一方向" },
  { id: "connect", name: "连接个人工具" },
  { id: "library", name: "团队资料库" },
  { id: "settings", name: "成员与设置" }
];

const S = {
  page: "scene",
  step: 0,          // 0 = 未开始；1..7 = 演示进度
  playing: false
};

/* 每个演示步骤：切到哪一页 + 这一步揭示什么 */
const STEPS = [
  { page: "scene",     label: "队友的三条进展，从各自的 AI 工具同步进来" },
  { page: "library",   label: "资料库留下来源与两种说法，不合并成一句话" },
  { page: "scene",     label: "总智能体发现两条表述相反，没有替谁选边" },
  { page: "direction", label: "生成带引用、理由和待核实的草案，等队长确认" },
  { page: "scene",     label: "队长确认后，才成为正式安排" },
  { page: "connect",   label: "任务读回各自的工具，方向保持同一份" },
  { page: "settings",  label: "自动统筹由队长控制，随时可关" }
];

/* 揭示闸门 */
const gate = {
  reports:  () => S.step >= 1,
  library:  () => S.step >= 2,
  conflict: () => S.step >= 3,
  proposal: () => S.step >= 4,
  confirmed:() => S.step >= 5,
  readback: () => S.step >= 6
};

/* ============================================================ 小组件 */

const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const who = (m) => `<span class="who-line"><span class="avatar">${esc(m.initial)}</span><span>${esc(m.name)}</span></span>`;
const chip = (text, tone = "") => `<span class="chip ${tone}">${esc(text)}</span>`;

/* ============================================================ 页面：团队现场 */

function pageScene() {
  const showReports = gate.reports();
  const reports = showReports ? REPORTS : [];

  const nextAction = gate.confirmed() ? `
    <div class="next-action fade">
      <div>
        <div class="eyebrow">我的下一步</div>
        <h2>验证数据可得性：菜单页到底有没有排队字段</h2>
        <p class="muted">T-01 · 负责人 陈子墨 · 依赖：无 · 来自已确认安排 v${PROPOSAL.version}</p>
      </div>
      <button class="primary" onclick="toast('演示页不提交真实数据')">查看这项任务</button>
    </div>` : "";

  const conflict = gate.conflict() ? `
    <div class="card fade">
      <div class="row" style="margin-bottom:6px">
        <span class="eyebrow">存在不同观点的问题</span>
        ${chip("待核实", "warm")}
      </div>
      <h2>${esc(CONFLICT.question)}</h2>
      <p class="muted">检测到不同表述，是否矛盾需要核对依据。</p>
      <div class="quote a"><strong>${esc(CONFLICT.a.who)}</strong> · ${esc(CONFLICT.a.tool)}<br>${esc(CONFLICT.a.text)}</div>
      <div class="quote b"><strong>${esc(CONFLICT.b.who)}</strong> · ${esc(CONFLICT.b.tool)}<br>${esc(CONFLICT.b.text)}</div>
      <div class="note">不同AI说法一致，也不代表已经验证。这里保留两种说法，等实测之后再判断。</div>
    </div>` : "";

  const confirmed = gate.confirmed() ? `
    <div class="card fade">
      <div class="row" style="margin-bottom:10px">
        <span class="eyebrow">已确认安排</span>
        ${chip("v" + PROPOSAL.version, "green")}
        <span class="spacer"></span>
        <button class="ghost" onclick="toast('已导出当前交接清单')">导出当前交接清单</button>
      </div>
      ${PROPOSAL.tasks.map(t => `
        <div class="task">
          <div class="h">
            <div>
              <div class="k">${esc(t.key)} · 负责人 ${esc(t.owner)} · 依赖 ${esc(t.dep)}</div>
              <div style="font-weight:600;margin-top:3px">${esc(t.title)}</div>
              <div class="muted" style="margin-top:5px">检查方法：${esc(t.check)}</div>
            </div>
            ${chip("已确认", "green")}
          </div>
        </div>`).join("")}
    </div>` : "";

  const reportsHtml = showReports ? `
    <div class="card fade">
      <div class="row" style="margin-bottom:4px">
        <span class="eyebrow">最近同步记录</span>
        <span class="spacer"></span>
        <span class="muted">每 5 秒刷新 · ${esc(TEAM.updated)}</span>
      </div>
      <p class="muted" style="margin-bottom:14px">各自的进展，在这里对齐。个人自报 · 尚未独立核实。</p>
      ${reports.map(r => `
        <div class="task fade">
          <div class="h">
            <div>
              <div class="who-line" style="margin-bottom:6px">
                <span class="avatar">${esc(r.initial)}</span>
                <strong>${esc(r.who)}</strong>
                <span class="muted">${esc(r.tool)} · ${esc(r.model)} · ${esc(r.time)}</span>
              </div>
              <div>${esc(r.now)}</div>
              <div class="quote" style="margin:8px 0 6px">“${esc(r.view)}”</div>
              <div class="muted">对应：${esc(r.target)}　依据：${esc(r.evidence)}</div>
            </div>
            <div style="text-align:right;white-space:nowrap">
              ${chip(r.status, r.status === "受阻" ? "red" : r.status === "讨论" ? "warm" : "blue")}
            </div>
          </div>
        </div>`).join("")}
    </div>` : `
    <div class="card">
      <div class="note">等待第一条重要进展。连接个人工具后，工作记录会出现在这里。</div>
    </div>`;

  return `
    <div class="top">
      <div>
        <div class="eyebrow">团队现场 · ${esc(TEAM.contest)}</div>
        <h1>${esc(TEAM.name)}</h1>
        <p class="muted">资料 v${TEAM.revision} · 队伍码 ${esc(TEAM.code)} · 3 名成员</p>
      </div>
      <div class="row">
        ${chip("每 5 秒刷新", "green")}
        <button class="ghost" onclick="toast('演示页只有一个团队')">切换团队</button>
      </div>
    </div>
    ${nextAction}
    ${confirmed}
    ${conflict}
    <div class="grid2" style="align-items:start">
      <div>${reportsHtml}</div>
      <div>
        <div class="card">
          <div class="eyebrow" style="margin-bottom:10px">团队成员</div>
          ${MEMBERS.map(m => `
            <div style="padding:9px 0;border-bottom:1px solid #eef1f6">
              <div class="who-line">
                <span class="avatar">${esc(m.initial)}</span>
                <strong>${esc(m.name)}</strong>
                ${m.role === "队长" ? chip("队长", "blue") : ""}
                <span class="spacer"></span>
                <span class="muted">${m.hours} 小时</span>
              </div>
              <div class="muted" style="margin-top:3px">${esc(m.strengths)}</div>
            </div>`).join("")}
        </div>
        <div class="card">
          <div class="eyebrow" style="margin-bottom:10px">团队总智能体</div>
          ${gate.proposal()
            ? `<p>有一份待确认建议，基于资料 v${PROPOSAL.version}。</p>
               <button class="primary" onclick="go('direction')">查看待确认建议</button>`
            : `<p class="muted">尚无统筹建议。先连接工具并同步进展，或填写共同方向。</p>
               <button class="ghost" onclick="go('direction')">去看统一方向</button>`}
        </div>
      </div>
    </div>`;
}

/* ============================================================ 页面：统一方向 */

function pageDirection() {
  const hasProposal = gate.proposal();
  const isConfirmed = gate.confirmed();

  const proposalCard = hasProposal ? `
    <div class="card fade" style="border-color:#c9d6fd">
      <div class="row" style="margin-bottom:10px">
        <span class="eyebrow">待确认建议</span>
        ${chip("基于资料 v" + PROPOSAL.version, "blue")}
        <span class="spacer"></span>
        ${isConfirmed ? chip("已发布", "green") : chip("待队长确认", "warm")}
      </div>
      <p>综合团队方向、成员意愿、评分依据和个人工具提供的观点，先给建议，再由人确认。</p>
      <div class="divider"></div>
      <h3>理由</h3>
      <p>${esc(PROPOSAL.reason)}</p>
      <h3 style="margin-top:14px">待核实</h3>
      <ul style="margin:0 0 14px 18px;padding:0">
        ${PROPOSAL.pending.map(p => `<li style="margin-bottom:5px">${esc(p)}</li>`).join("")}
      </ul>
      <h3>建议任务（${PROPOSAL.tasks.length}）</h3>
      ${PROPOSAL.tasks.map(t => `
        <div class="task">
          <div class="h">
            <div>
              <div class="k">${esc(t.key)} · 负责人 ${esc(t.owner)} · 依赖 ${esc(t.dep)}</div>
              <div style="font-weight:600;margin-top:3px">${esc(t.title)}</div>
              <div class="muted" style="margin-top:5px">检查方法：${esc(t.check)}</div>
            </div>
          </div>
        </div>`).join("")}
      <div class="divider"></div>
      <div class="row">
        ${isConfirmed
          ? `<button class="ghost" onclick="toast('安排已发布，个人工具可以读取')">已发布 · 查看历史</button>`
          : `<button class="primary" onclick="confirmProposal()">确认并发布这 ${PROPOSAL.tasks.length} 项任务</button>`}
        <span class="muted">确认发布这份安排？新版本会替换当前正式任务，旧版本保留记录。</span>
      </div>
    </div>` : `
    <div class="card">
      <div class="note">尚未生成建议。填好共同方向后，由队长发起统筹。</div>
    </div>`;

  const readback = gate.readback() ? `
    <div class="card fade">
      <div class="eyebrow" style="margin-bottom:8px">个人工具已读回</div>
      <div class="mono">$ songban context --team tm_9f3c21

方向 v${PROPOSAL.version} · 与团队同一份
我的任务  T-01  验证数据可得性   依赖：无
截止      2027-03-15 18:00 (+08:00)
状态      已读取（note_id: n_7c41e9）</div>
    </div>` : "";

  return `
    <div class="top">
      <div>
        <div class="eyebrow">统一方向 · 全队共同依据</div>
        <h1>让每个智能体知道，我们要去哪。</h1>
        <p class="muted">这里是全队共同依据。个人讨论和 AI 建议都不会自动改写它。</p>
      </div>
      <div class="row">${chip("资料 v" + DIRECTION_VERSION(), "blue")}${chip("只有队长能修改", "warm")}</div>
    </div>

    <div class="card">
      <label>这次必须解决的问题与产出</label>
      <textarea rows="3">${esc(DIRECTION.goal)}</textarea>

      <label>赛事要求（手工粘贴主办方原文）</label>
      <textarea rows="5">${esc(DIRECTION.rules)}</textarea>

      <label>评委评分依据</label>
      <textarea rows="3">${esc(DIRECTION.rubric)}</textarea>

      <label>本次明确不做</label>
      <textarea rows="4">${esc(DIRECTION.nonGoals)}</textarea>

      <label>截止时间（带时区，可留空）</label>
      <input value="${esc(DIRECTION.deadline)}">

      <div class="divider"></div>
      <div class="row">
        <button class="primary" onclick="toast('共同方向已更新。已有草案需要根据新资料重新统筹。')">保存共同方向</button>
        <span class="muted">没有提供的信息会保留未知，不让 AI 补造赛规或评分比例。</span>
      </div>
    </div>

    <div class="row" style="margin:18px 0 10px">
      <span class="eyebrow">团队总智能体</span>
      <span class="spacer"></span>
      ${chip("已配置团队模型：deepseek-v4-pro", "green")}
    </div>
    ${proposalCard}
    ${readback}

    <div class="card">
      <div class="eyebrow" style="margin-bottom:10px">已确认的统筹记录</div>
      <table>
        <tr><th>版本</th><th>时间</th><th>任务</th><th>状态</th></tr>
        <tr><td>v3</td><td>2027-03-02 20:14</td><td>${PROPOSAL.tasks.length} 项</td><td>${gate.confirmed() ? chip("已发布", "green") : chip("待确认", "warm")}</td></tr>
        <tr><td>v2</td><td>2027-03-01 21:02</td><td>2 项</td><td>${chip("已被 v3 替换", "")}</td></tr>
      </table>
    </div>`;
}

function DIRECTION_VERSION() { return gate.confirmed() ? PROPOSAL.version : DIRECTION.rev || 3; }

/* ============================================================ 页面：连接个人工具 */

function pageConnect() {
  return `
    <div class="top">
      <div>
        <div class="eyebrow">连接个人工具</div>
        <h1>继续用你习惯的工具。</h1>
        <p class="muted">支持 MCP 的工具直接连接；其他能读写文件的工具可使用共享文件自动同步。无需上传所有私人聊天。</p>
      </div>
      ${chip("只共享获准的项目摘要", "green")}
    </div>

    <div class="card">
      <div class="row" style="margin-bottom:10px">
        <span class="eyebrow">本机原生插件</span>
        <span class="spacer"></span>
        ${chip("已安装", "green")}
      </div>
      <h3>松伴连接器 · Codex 原生插件</h3>
      <p class="muted">安装并注册原生插件，在输入框加号的插件入口选择。只共享获准的项目摘要。</p>
      <label>按项目连接）正在开发的项目文件夹</label>
      <input value="E:\\work\\lunch-queue">
      <div class="row" style="margin-top:12px">
        <button class="primary" onclick="toast('松伴原生插件已注册并启用，团队连接已验证。')">一键安装到所选工具</button>
        <span class="muted">已安装到：~/.codex/plugins/songban-local</span>
      </div>
      <div class="note" style="margin-top:12px">工具内是否加载成功，仍需回到该工具查看；这里没有把连接检查当作客户端已经启用。</div>
    </div>

    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="eyebrow" style="margin-bottom:10px">给自己的工具生成连接凭证</div>
        <label>工具名称</label>
        <select><option>Codex</option><option>WorkBuddy</option><option>Cursor</option><option>其他</option></select>
        <div class="row" style="margin-top:12px">
          <button class="primary" onclick="toast('凭证仅显示一次，请立即保存到工具配置。')">生成本人连接凭证</button>
        </div>
        <div class="divider"></div>
        <div class="mono">${CONNECTIONS[0].token}
有效期 ${CONNECTIONS[0].exp}</div>
        <p class="muted" style="margin-top:10px">不要将含凭证的配置发到群里或提交 Git。队友应生成自己的凭证。</p>
      </div>

      <div class="card">
        <div class="eyebrow" style="margin-bottom:10px">我的连接</div>
        <table>
          <tr><th>连接</th><th>状态</th><th>最近同步</th></tr>
          <tr>
            <td>Codex · 晨光队项目</td>
            <td>${chip("可连接", "green")}</td>
            <td>${CONNECTIONS[0].last}</td>
          </tr>
        </table>
        <div class="row" style="margin-top:10px">
          <button class="ghost" onclick="toast('连接状态已更新。')">暂停</button>
          <button class="ghost" onclick="toast('已撤销，下一次访问会被拒绝。')">撤销</button>
        </div>
        <div class="divider"></div>
        <p class="muted">连接凭证只能上传本人的进展、读取本队方向与任务，不能替队长发布安排。</p>
      </div>
    </div>

    <div class="card">
      <div class="eyebrow" style="margin-bottom:10px">同步和回传，都有边界</div>
      <div class="grid3">
        <div><h3>断网先留在本机</h3><p class="muted">内容先留在本机队列，恢复后补传。</p></div>
        <div><h3>撤销立即生效</h3><p class="muted">暂停或撤销连接会立即阻止下一次访问。</p></div>
        <div><h3>只显示最近 80 条</h3><p class="muted">完整历史保留在服务器；较早的信息不当成已了解的事实。</p></div>
      </div>
    </div>

    ${gate.readback() ? `
    <div class="card fade" style="border-color:#bfe0d6">
      <div class="row" style="margin-bottom:8px">
        <span class="eyebrow">读回同一个方向</span>
        ${chip("已读取", "green")}
      </div>
      <div class="mono">$ songban my-tasks --team tm_9f3c21

T-01  验证数据可得性：菜单页到底有没有排队字段   负责人 陈子墨
T-02  问卷设计与投放                            负责人 周雨桐   依赖 T-01
T-03  页面接入真实数据                          负责人 林知远   依赖 T-01

方向版本 v${PROPOSAL.version} · 与其他成员读取的是同一份</div>
    </div>` : ""}`;
}

/* ============================================================ 页面：团队资料库 */

function pageLibrary() {
  const show = gate.library();
  return `
    <div class="top">
      <div>
        <div class="eyebrow">团队资料库</div>
        <h1>被你选中的关键内容，留在团队里。</h1>
        <p class="muted">注册姓名：用户原话　模型名称：回复关键信息。当前对话上传只记录，不自动触发分析。</p>
      </div>
      <button class="ghost" onclick="toast('已刷新资料库')">刷新资料库</button>
    </div>

    ${show ? LIBRARY.map((it, i) => `
      <div class="card fade">
        <div class="row" style="margin-bottom:8px">
          ${chip(it.who + " · " + it.tool, "blue")}
          ${chip(it.model, "")}
          <span class="spacer"></span>
          <span class="muted">${esc(it.time)}</span>
        </div>
        <div class="quote a"><strong>用户原话</strong><br>${esc(it.original)}</div>
        <div class="quote"><strong>${esc(it.model)}：回复关键信息</strong><br>${esc(it.reply)}</div>
        ${i === 1 ? `<div class="warn">这条与下一条对「数据来源」的判断相反。${chip("存在不同观点", "warm")}</div>` : ""}
      </div>`).join("") : `
      <div class="card"><div class="note">还没有上传的对话记录。</div></div>`}

    <div class="card">
      <div class="eyebrow" style="margin-bottom:8px">这份资料库不做什么</div>
      <p class="muted" style="margin:0">没有宿主事件钩子，不承诺后台捕获所有聊天；只有用户显式选择的那一轮会被记录。来源保留、观点分开，不同 AI 说法一致也不代表已经验证。</p>
    </div>`;
}

/* ============================================================ 页面：成员与设置 */

function pageSettings() {
  return `
    <div class="top">
      <div>
        <div class="eyebrow">成员与设置</div>
        <h1>分工，也要尊重你的意愿。</h1>
        <p class="muted">优势不代表必须一直做同一种工作。把本次学习目标和可用时间告诉团队。</p>
      </div>
      ${chip("队长视角", "blue")}
    </div>

    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="eyebrow" style="margin-bottom:10px">我的工作情况</div>
        <label>本次愿意承担什么，想练习什么</label>
        <input value="想把路演讲顺，愿意上台；同时练一下用 AI 拆任务">
        <label>本次剩余可用小时</label>
        <input value="6">
        <div class="row" style="margin-top:14px">
          <button class="primary" onclick="toast('个人情况已保存。')">保存我的情况</button>
        </div>
        <div class="divider"></div>
        <label style="display:flex;gap:9px;align-items:flex-start;font-weight:400;margin:0">
          <input type="checkbox" checked style="width:auto;margin-top:4px">
          <span>启用自动生成待确认草案<br>
          <span class="muted">重要进展同步后自动生成建议，会调用服务端模型并产生费用。不会自动发布任务。</span></span>
        </label>
      </div>

      <div class="card">
        <div class="eyebrow" style="margin-bottom:10px">邀请队友</div>
        <p class="muted">队友用自己的手机号登录，再输入队伍码加入。</p>
        <div class="mono">队伍码：${esc(TEAM.code)}
队伍 ID：${esc(TEAM.id)}</div>
        <div class="divider"></div>
        <div class="eyebrow" style="margin-bottom:10px">安排历史</div>
        <table>
          <tr><th>版本</th><th>时间</th><th>状态</th></tr>
          <tr><td>v3</td><td>03-02 20:14</td><td>${gate.confirmed() ? chip("已发布", "green") : chip("待确认", "warm")}</td></tr>
          <tr><td>v2</td><td>03-01 21:02</td><td>${chip("已被替换", "")}</td></tr>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="eyebrow" style="margin-bottom:12px">成员</div>
      <table>
        <tr><th>成员</th><th>优势</th><th>意愿</th><th>剩余时间</th></tr>
        ${MEMBERS.map(m => `
          <tr>
            <td>${who(m)} ${m.role === "队长" ? chip("队长", "blue") : ""}</td>
            <td>${esc(m.strengths)}</td>
            <td>${esc(m.willing)}</td>
            <td>${m.hours} 小时</td>
          </tr>`).join("")}
      </table>
    </div>`;
}

/* ============================================================ 路由与渲染 */

const RENDER = { scene: pageScene, direction: pageDirection, connect: pageConnect, library: pageLibrary, settings: pageSettings };

function renderNav() {
  document.getElementById("nav").innerHTML = PAGES.map(p =>
    `<button class="${S.page === p.id ? "on" : ""}" onclick="go('${p.id}')">${p.name}</button>`
  ).join("");
}

function render() {
  renderNav();
  document.getElementById("main").innerHTML = RENDER[S.page]();
  renderBar();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function go(id) {
  S.page = id;
  render();
}

function toast(msg) {
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.cssText = "position:fixed;left:50%;bottom:82px;transform:translateX(-50%);background:#17243b;color:#fff;padding:10px 16px;border-radius:10px;font-size:13px;z-index:60;box-shadow:0 10px 30px #17243b44";
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 1800);
}

function confirmProposal() {
  if (!gate.proposal()) return;
  S.step = Math.max(S.step, 5);
  toast("安排已发布，个人工具可以读取。");
  render();
}

/* ============================================================ 演示条 */

function renderBar() {
  const started = S.step > 0;
  document.getElementById("stepNo").textContent = started ? `第 ${S.step} / ${STEPS.length} 步` : "演示模式";
  document.getElementById("stepLabel").textContent = started
    ? STEPS[S.step - 1].label
    : "点「开始演示」，全流程自动走一遍";
  document.getElementById("dots").innerHTML = STEPS.map((_, i) =>
    `<i class="${i < S.step ? "on" : ""}"></i>`).join("");
  document.getElementById("btnPlay").textContent = started ? (S.playing ? "暂停" : "继续") : "开始演示";
  document.getElementById("btnPrev").disabled = S.step <= 1;
}

function applyStep(n) {
  S.step = Math.max(0, Math.min(STEPS.length, n));
  if (S.step > 0) S.page = STEPS[S.step - 1].page;
  render();
}

let timer = null;
function play() {
  if (S.step >= STEPS.length) { S.step = 0; S.page = "scene"; }
  S.playing = true;
  render();
  const tick = () => {
    if (!S.playing) return;
    if (S.step >= STEPS.length) { S.playing = false; render(); return; }
    applyStep(S.step + 1);
    if (S.step >= STEPS.length) { S.playing = false; render(); return; }
    timer = setTimeout(tick, 2600);
  };
  timer = setTimeout(tick, 600);
}

function pause() {
  S.playing = false;
  clearTimeout(timer);
  render();
}

document.getElementById("btnPlay").onclick = () => (S.playing ? pause() : play());
document.getElementById("btnPrev").onclick = () => { pause(); applyStep(S.step - 1); };
window.addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") { pause(); applyStep(S.step + 1); }
  if (e.key === "ArrowLeft") { pause(); applyStep(S.step - 1); }
});

/* 支持 #s5 这样直接跳到某一步，路演时不用现场点 */
function readHash() {
  const m = /^#s(\d)$/.exec(location.hash || "");
  if (m) {
    const n = Math.max(0, Math.min(STEPS.length, parseInt(m[1], 10)));
    S.step = n;
    if (n > 0) S.page = STEPS[n - 1].page;
  }
}
window.addEventListener("hashchange", () => { pause(); readHash(); render(); });

readHash();
render();
