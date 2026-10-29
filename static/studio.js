const SAMPLE = "主办方要求：可演示作品、宣传片、PPT、分工说明，以及 GitHub 仓库链接。";
const NAV = [
  ["signup", "首次注册"],
  ["contest", "赛事信息"],
  ["team", "组队"],
  ["success", "组队成功"],
  ["home", "首页"],
  ["mine", "我的空间"],
  ["teamspace", "团队空间"],
  ["topics", "选题空间"],
  ["skill", "安装同一技能"],
  ["talk", "讨论"],
  ["docs", "需求与流程图"],
  ["vote", "团队表决"],
  ["captain", "队长规划"],
  ["log", "更改记录"],
  ["growth", "赛后成长"],
];
const SIDE = [
  ["home", "首页"],
  ["hubMine", "我的系统"],
  ["hubContest", "比赛系统"],
  ["friends", "好友"],
  ["past", "参加过的比赛"],
  ["growth", "成长系统"],
  ["stack", "我的技术栈"],
  ["contest", "赛事信息"],
  ["team", "组队"],
  ["teamspace", "团队空间"],
  ["mine", "我的空间"],
  ["talk", "讨论"],
  ["topics", "选题空间"],
  ["skill", "安装同一技能"],
  ["vote", "团队表决"],
  ["docs", "需求与流程图"],
  ["log", "更改记录"],
  ["captain", "队长规划"],
];
const CHAT = new Set(["team", "mine", "teamspace", "topics", "skill", "talk", "docs", "vote", "captain", "growth", "profile", "memory", "stack", "board", "progress", "space"]);
const COACH = new Set(["mine", "docs", "growth", "profile", "memory", "stack", "progress", "space"]);
const NEED_SQUAD = new Set(["success", "mine", "topics", "skill", "talk", "docs", "vote", "captain", "log", "board", "progress"]);
const NEED_CONFIRMED = new Set(["success", "mine", "topics", "skill", "talk", "docs", "vote", "captain"]);
const ROLES = ["产品", "设计", "后端开发", "用户调研", "前端开发", "路演", "UI/视觉设计"];
const COUNTDOWN_SCREENS = new Set(["messages", "home", "contest", "team", "board", "teamspace", "past", "space"]);
const HUB_FREE = new Set(["home", "hubMine", "hubContest", "friends", "past", "growth", "stack", "contest", "team", "profile", "memory", "settings", "messages", "space"]);
const BRIEFS = {
  需求文档: "目标：做出截止前能演示的一条路径。\n谁用：本队。\n主路径：选比赛、组队、选题、安装同一技能、发布任务。\n这场不做：主办方系统和给其他队伍排名。",
  业务流程图: "注册 → 选比赛 → 组队 → 选题 → 安装同一技能 → 发布任务 → 提交清单上的成果",
  页面原型: "首页放比赛名、倒计时和提交清单。我的空间只放我的截止时间。团队空间放任务树、成果架和仓库记录。",
};

const state = {
  screen: "login",
  token: localStorage.getItem("studio-token") || "",
  squadId: localStorage.getItem("studio-squad") || "",
  contestId: localStorage.getItem("studio-contest") || "",
  me: null,
  squad: null,
  error: "",
  note: "",
  needProfile: false,
  issuedCode: "",
  wechatNote: "",
  wechatTicket: "",
  wechatInvite: "",
  smsNote: "",
  smsReady: false,
  teamModelName: "",
  menuOpen: false,
  chats: {},
  contestDraft: null,
  contestPreview: null,
  threadKind: "",
  threadId: "",
  threadMessages: [],
  friendCard: null,
  contestAskReply: "",
  showContestFacts: true,
  confirmingContest: false,
  flow: "",
  tick: null,
  agentLines: [],
  showRoster: false,
  threadRoster: [],
  boardEdit: false,
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function val(form, name) {
  const node = form.elements.namedItem(name);
  return node && "value" in node ? String(node.value) : "";
}

function when(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso || "";
  return date.toLocaleString("zh-CN", { hour12: false });
}

function toIso(value) {
  if (!value) throw new Error("先选择结束时间。");
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!match) throw new Error("结束时间格式不对。");
  const local = new Date(`${match[1]}T${match[2]}:${match[3]}:00`);
  if (Number.isNaN(local.getTime())) throw new Error("结束时间不对。");
  const off = -local.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  const pad = (n) => String(Math.floor(n)).padStart(2, "0");
  return `${match[1]}T${match[2]}:${match[3]}:00${sign}${pad(abs / 60)}:${pad(abs % 60)}`;
}

function toDatetimeLocal(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

async function apiUpload(path, formData) {
  const response = await fetch(path, {
    method: "POST",
    headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},
    body: formData,
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try { data = JSON.parse(text); } catch { data = {}; }
  }
  if (!response.ok) {
    const error = new Error(data.error?.message || "没有完成。");
    error.code = data.error?.code || "";
    error.status = response.status;
    throw error;
  }
  return data;
}

function level(score) {
  return ["做不到", "一般", "做得到"][score] || String(score);
}

function nameOf(id) {
  const member = (state.squad?.members || []).find((item) => item.user_id === id);
  return member ? member.name : "队员";
}

function checkedValues(form, name) {
  return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map((node) => node.value);
}

function saveSession() {
  localStorage.setItem("studio-token", state.token);
  localStorage.setItem("studio-squad", state.squadId);
  localStorage.setItem("studio-contest", state.contestId);
  localStorage.removeItem("studio-accounts");
}

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try { data = JSON.parse(text); } catch { data = {}; }
  }
  if (!response.ok) {
    const error = new Error(data.error?.message || "没有完成。");
    error.code = data.error?.code || "";
    error.status = response.status;
    throw error;
  }
  return data;
}

async function reload() {
  if (!state.token) return;
  state.me = await api("GET", "/api/studio/me");
  if (state.squadId) state.squad = await api("GET", `/api/studio/squads/${state.squadId}`);
}

function rememberSquad(id) {
  state.squadId = id;
  saveSession();
}

let threadLoad = 0;
async function loadThread() {
  if (!state.threadId || (state.threadKind !== "dm" && state.threadKind !== "squad")) {
    state.threadMessages = [];
    return;
  }
  const ticket = ++threadLoad;
  const kind = state.threadKind;
  const id = state.threadId;
  const query = kind === "dm"
    ? `kind=dm&peer_id=${encodeURIComponent(id)}`
    : `kind=squad&squad_id=${encodeURIComponent(id)}`;
  if (kind === "squad") {
    try {
      const snap = await api("GET", `/api/studio/squads/${id}`);
      if (ticket === threadLoad && state.threadKind === kind && state.threadId === id) state.threadRoster = snap.members || [];
    } catch {
      if (ticket === threadLoad) state.threadRoster = [];
    }
  } else if (ticket === threadLoad) {
    state.threadRoster = [];
  }
  const data = await api("GET", `/api/studio/messages?${query}`);
  if (ticket !== threadLoad || state.threadKind !== kind || state.threadId !== id) return;
  state.threadMessages = data.messages || [];
}

function clearPrivateView() {
  state.threadKind = "";
  state.threadId = "";
  state.threadMessages = [];
  state.friendCard = null;
  state.chats = {};
  threadLoad += 1;
}

function canOpen(id) {
  if (id === "signup" || id === "login") return true;
  if (!state.token) return "先用手机号和密码登录。没有注册就用手机号注册。";
  if (HUB_FREE.has(id)) return true;
  if (NEED_SQUAD.has(id) && !state.squad) return "还没有队伍。先点左侧「团队」创建或加入。";
  if (NEED_CONFIRMED.has(id) && state.squad && !state.squad.squad.confirmed) return "先让每人贴介绍并选角色，再由队长确认。";
  if ((id === "skill" || id === "docs") && !state.squad.squad.topic) return "先在选题空间确认题目。";
  if (id === "captain" && !state.squad.me.captain) return "队长规划只有队长能打开。你的任务在我的空间，全队任务在团队空间。";
  return true;
}

function nextStep() {
  if (!state.token) return "用手机号和密码登录。还没有注册就走手机号注册。";
  if (!state.squad && !(state.me?.contests || []).length) return "下一步：填写比赛名称，上传资料或公众号网址，点确认比赛。";
  if (!state.squad) return "下一步：创建队伍，或让队友用自己的手机号进入后填写队伍码。";
  if (!state.squad.squad.confirmed) return "下一步：每人贴一段介绍并选角色。人齐了，队长再确认。确认后才会出现对勾。";
  if (!state.squad.squad.topic) return "下一步：到选题空间送入想法。队长确认一条，全队看见同一题。";
  if (state.squad.members.some((member) => !member.skill_installed)) return "下一步：每人下载并安装同一份技能。文件内容全队相同。";
  if (!state.squad.tasks.length) return state.squad.me.captain ? "下一步：在队长规划里发布任务。发布不用等表决。" : "下一步：等队长发布任务。会改题目、主干或提交清单的想法，先到团队表决。";
  if (!state.squad.squad.finished) return "任务已经发布。做完后由队长在赛后成长里记下这场。";
  return "这场已记入成长。下次用手机号和密码进入，不必重填画像。";
}

function page(inner) {
  const hint = state.screen === "signup" || state.screen === "login" || state.screen === "success" ? "" : `<p class="hint">${esc(nextStep())}</p>`;
  const main = `<div>${hint}${inner}</div>`;
  if (!CHAT.has(state.screen)) return main;
  return `<div class="work">${main}${chatBox()}</div>`;
}

function chatBox() {
  const coach = COACH.has(state.screen);
  const lines = state.chats[state.screen] || [];
  const bubbles = lines.map((line) => `<div class="bubble me">${esc(line.me)}</div><div class="bubble">${esc(line.reply)}</div>`).join("");
  const idle = coach
    ? "问你自己的模型：怎么做、先学什么、今天排哪几步。答完可以交给团队。"
    : "问团队模型下一步做什么。它按已确认的题目和提交清单回答，不会改题目或任务。";
  const share = coach && lines.length ? `<button class="btn ghost" type="button" data-act="shareChat">把这次讨论交给团队</button>` : "";
  const caption = coach
    ? (state.me?.model_ready ? `个人模型 · ${esc(state.me.model_name || "已填写")}。费用算在你自己的账户上。` : "还没填写密钥。到设置里写上你的 API，费用算在你自己的账户上。")
    : (state.teamModelName ? `团队模型 · ${esc(state.teamModelName)}。费用记在配置这台服务的账户上。` : "团队模型还没在服务器上配好。");
  return `<aside class="chat">
    <h3>${coach ? "私人教练" : "团队方向"}</h3>
    <p class="muted">${caption}</p>
    ${bubbles || `<div class="bubble">${esc(idle)}</div>`}
    <form data-act="chat" class="composer">
      <input name="message" aria-label="${coach ? "问私人教练" : "问团队方向"}" ${state.squad ? "" : "disabled"}>
      <button class="btn" type="submit" ${state.squad ? "" : "disabled"}>发送</button>
    </form>
    ${share}
  </aside>`;
}

function banners() {
  return `${state.error ? `<p class="error" role="alert">${esc(state.error)}</p>` : ""}${state.note ? `<p class="ok" role="status">${esc(state.note)}</p>` : ""}`;
}

function submissionsOf(list) {
  if (!list.length) return "<p class=\"muted\">正文里没有抽出提交项。换一段写明要交什么的材料。</p>";
  return `<ul>${list.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
}

function memberOptions(selected) {
  return (state.squad?.members || []).map((member) => `<option value="${esc(member.user_id)}" ${member.user_id === selected ? "selected" : ""}>${esc(member.name)} · ${esc(member.role || "未选角色")}</option>`).join("");
}

function editorBoxes() {
  return (state.squad?.members || []).filter((member) => member.user_id !== state.squad.me.id).map((member) => `<label class="check"><input type="checkbox" name="editors" value="${esc(member.user_id)}"> ${esc(member.name)} 可以改</label>`).join("");
}

function avatarHtml(url, name, cls = "avatar") {
  const label = (name || "我").slice(0, 1);
  if (url) return `<span class="${cls}"><img src="${esc(url)}" alt="" referrerpolicy="no-referrer"></span>`;
  return `<span class="${cls}">${esc(label)}</span>`;
}

function viewLogin() {
  return `<div class="reg-wrap"><h2>进入松伴</h2>
    <p class="muted">用手机号和密码登录。</p>
    <form id="login-form" data-act="login" class="card">
      <label for="login-phone">手机号</label>
      <input id="login-phone" name="phone" type="tel" autocomplete="tel" inputmode="numeric" required placeholder="注册时用的手机号">
      <label for="login-password">密码</label>
      <input id="login-password" name="password" type="password" autocomplete="current-password" required>
      <button class="btn" type="submit">登录</button>
    </form>
    <p id="entry-status" hidden></p>
    <p class="muted"><button class="linkish" type="button" data-go="signup">还没有注册？用手机号注册</button></p></div>`;
}

function viewSignup() {
  return `<div class="reg-wrap"><h2>用手机号注册</h2>
    <p class="muted">验证手机号后设置密码。手机号就是登录账号。已经注册过的手机号只会补上密码，不覆盖原来的名字和技能。</p>
    <form id="reg-form" data-act="enter" class="card">
      <label for="reg-phone">手机号</label>
      <input id="reg-phone" name="phone" type="tel" autocomplete="tel" inputmode="numeric" placeholder="11 位手机号" required>
      <button class="btn ghost" type="button" data-act="requestCode">获取验证码</button>
      <p id="reg-code-note" class="muted" hidden></p>
      <p id="reg-issued" class="code" hidden></p>
      <label for="reg-code">验证码</label>
      <input id="reg-code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6 位数字" required>
      <label for="reg-password">密码</label>
      <input id="reg-password" name="password" type="password" autocomplete="new-password" minlength="8" maxlength="64" required>
      <label for="reg-password2">再输入一次密码</label>
      <input id="reg-password2" name="password2" type="password" autocomplete="new-password" minlength="8" maxlength="64" required>
      <div id="reg-profile" hidden>
        <label for="reg-name">名字</label>
        <input id="reg-name" name="name" maxlength="40" autocomplete="name">
        <label for="reg-about">我是谁、做过什么</label>
        <textarea id="reg-about" name="profile" placeholder="例如：高二，产品设计。会整理讨论和演示。"></textarea>
        <label for="reg-skills">目前做得到的事</label>
        <input id="reg-skills" name="skills" placeholder="例如：需求、流程图、路演">
        <p class="muted">只在第一次问。验证码还没通过时，填了也不会进入。</p>
      </div>
      <button class="btn" type="submit">注册</button>
    </form>
    <p id="entry-status" hidden></p>
    <p class="muted"><button class="linkish" type="button" data-go="login">已经注册？去登录</button></p></div>`;
}

function viewProfile() {
  const me = state.me || {};
  return page(`<h2>编辑资料</h2>
    <p class="muted">改的是你自己的名字、画像和目前做得到的事。不会编头像，也不会读取旧对话。</p>
    <form data-act="saveProfile" class="card">
      <label for="profile-name">名字</label>
      <input id="profile-name" name="name" maxlength="40" value="${esc(me.name || "")}" required>
      <label for="profile-about">我是谁、做过什么</label>
      <textarea id="profile-about" name="profile" required>${esc(me.profile || "")}</textarea>
      <label for="profile-skills">目前做得到的事</label>
      <input id="profile-skills" name="skills" value="${esc(me.skills || "")}" required>
      <button class="btn" type="submit">保存资料</button>
    </form>
    <div class="row">
      <button class="btn ghost" type="button" data-go="settings">模型设置</button>
      <button class="btn ghost" type="button" data-act="logout">退出登录</button>
    </div>`);
}

function viewMemory() {
  const growth = state.me?.growth || "";
  return page(`<h2>个人记忆与能力记录</h2>
    <p class="muted">这里只记你写下来的，和每场比赛结束后教练按真实任务补上的。没有读取整段旧对话。</p>
    <div class="card"><pre>${esc(growth || "还没有记录。")}</pre></div>
    <form data-act="addMemory" class="card">
      <label for="memory-text">记一句以后还用得上的</label>
      <textarea id="memory-text" name="text" required placeholder="例如：路演可以独立完成，接口实现需要队友。"></textarea>
      <button class="btn" type="submit">记入个人记忆</button>
    </form>`);
}

function viewSettings() {
  const me = state.me || {};
  return `<h2>设置</h2>
    <div class="card">
      <p class="kicker">我的资料</p>
      <p>${esc(me.name || "")}</p>
      <p class="muted">手机号 ${esc(me.phone || "")}</p>
      <p class="muted">用手机号和密码登录。还没有注册时，用手机号收验证码并设置密码。</p>
      <div class="row">
        <button class="btn" type="button" data-go="profile">编辑资料</button>
        <button class="btn ghost" type="button" data-go="memory">个人记忆与能力记录</button>
      </div>
    </div>
    <div class="card">
      <p class="kicker">我的模型</p>
      <p class="muted">${me.model_ready ? `已保存 ${esc(me.model_name || "")}。密钥不再显示。留空密钥再保存，就是只改地址或模型名。` : "填写你自己的 API。问私人教练时花你的额度。"}</p>
      <form data-act="saveModel">
        <label for="model-base">接口地址</label>
        <input id="model-base" name="base_url" type="url" placeholder="https://api.deepseek.com" value="${esc(me.model_base || "")}" required>
        <label for="model-key">API 密钥</label>
        <input id="model-key" name="api_key" type="password" autocomplete="off" placeholder="${me.model_ready ? "已填写，要换再输入" : "只保存在服务器上"}">
        <label for="model-name">模型名</label>
        <input id="model-name" name="model_id" placeholder="deepseek-flash" value="${esc(me.model_name || "")}" required>
        <button class="btn" type="submit">保存我的模型</button>
      </form>
    </div>
    <div class="card">
      <p class="kicker">本机标记</p>
      <p>GitHub：${me.github_linked ? "已标记" : "未标记"} · 飞书：${me.feishu_linked ? "已标记" : "未标记"}</p>
      <p class="muted">只记在这台电脑上，不会打开 GitHub 或飞书。</p>
      <div class="row">
        <button class="btn ghost" type="button" data-act="markGithub" ${me.github_linked ? "disabled" : ""}>${me.github_linked ? "GitHub 已标记" : "标记已绑定 GitHub"}</button>
        <button class="btn ghost" type="button" data-act="markFeishu">${me.feishu_linked ? "取消飞书标记" : "标记已绑定飞书"}</button>
      </div>
    </div>
    <button class="btn ghost" type="button" data-act="logout">退出登录</button>`;
}

function savedContests() {
  return (state.me?.contests || []).filter((contest) => contest.card_saved);
}

function briefFact(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || text === "待补充") return "";
  const first = text.split(/[。；;]/)[0].trim();
  return first.length > 42 ? `${first.slice(0, 42)}…` : first;
}

function contestChips(contest) {
  const facts = contest.facts || {};
  const chips = [
    ["时间", briefFact(facts.time) || when(contest.deadline)],
    ["地点", briefFact(facts.location)],
    ["赛道", briefFact(facts.tracks)],
  ].filter((pair) => pair[1]);
  if (!chips.length) return "";
  return `<div class="contest-chips">${chips.map(([label, value]) => `<span>${esc(label)} ${esc(value)}</span>`).join("")}</div>`;
}

function safeIcon(value) {
  const text = String(value || "");
  return text.startsWith("data:image/") ? text : "";
}

function themeLabel(contest) {
  return contest?.theme_status === "pending" ? "现场公布 · 具体主题待揭晓" : "自由命题";
}

function contestCard(contest, actionsHtml) {
  const facts = contest.facts || {};
  const icon = safeIcon(contest.icon_data);
  const requirement = briefFact(facts.selection) || briefFact(facts.submissions_text);
  return `<article class="contest-card">
      ${icon ? `<img class="contest-icon" alt="" src="${esc(icon)}">` : `<p class="kicker">赛事卡</p>`}
      <h3>${esc(contest.name)}</h3>
      ${contestChips(contest)}
      ${requirement ? `<p>要求 ${esc(requirement)}</p>` : ""}
      <p>${esc(contest.core_summary || "核心内容会在搜索时由模型提炼。")}</p>
      <p class="muted">${esc(themeLabel(contest))} · 作品截止 ${esc(when(contest.deadline) || "未写入")}</p>
      ${actionsHtml || ""}
    </article>`;
}

function viewContest() {
  const found = state.contestPreview;
  if (found) {
    return `<h2>赛事信息</h2>
      <p class="muted"><button class="linkish" type="button" data-go="hubContest">← 比赛系统</button></p>
      ${contestCard(found, `<div class="card" style="margin-top:12px">
        <label for="theme-status">命题状态</label>
        <select id="theme-status">
          <option value="open" ${found.theme_status === "pending" ? "" : "selected"}>自由命题，队长填写开发内容</option>
          <option value="pending" ${found.theme_status === "pending" ? "selected" : ""}>官方现场公布，先显示具体主题待揭晓</option>
        </select>
        <p class="muted">确认前可以改这一项。保存后写入你的比赛卡。</p>
        <div class="row" style="margin-top:16px">
          <button class="btn" type="button" data-act="saveContestCard" data-id="${esc(found.id)}">保存为赛事卡</button>
          <button class="btn ghost" type="button" data-act="clearContestPreview">再搜一场</button>
        </div>
      </div>`)}`;
  }
  const draft = state.contestDraft || {};
  const attach = draft.fileName
    ? `已附上文件：${esc(draft.fileName)}`
    : (draft.fileText ? "已附上拖入的文字资料" : "把文件或链接拖到这里，也可点选文件");
  return `<h2>搜索比赛</h2>
    <p class="muted"><button class="linkish" type="button" data-go="hubContest">← 比赛系统</button></p>
    <form data-act="confirmContest" class="card">
      <label for="cname">比赛名称</label>
      <input id="cname" name="name" value="${esc(draft.name || "")}" placeholder="例如：ClawHunt 72小时黑客松上海站" required>
      <label>上传资料</label>
      <div class="dropzone" id="contest-drop" tabindex="0">
        <strong>拖文件或链接到这里</strong>
        <p class="muted">${attach}</p>
        <label class="filepick" for="cfile">选择文件</label>
        <input id="cfile" type="file" accept=".txt,.md,.markdown,.html,.htm,.csv,.json,.log,.rst,.webloc,.url,text/plain">
      </div>
      <label for="curl">微信公众号网址</label>
      <input id="curl" name="url" value="${esc(draft.url || "")}" placeholder="https://mp.weixin.qq.com/s/……">
      <div class="row" style="margin-top:14px">
        <button class="btn" type="submit" ${state.confirmingContest ? "disabled" : ""}>${state.confirmingContest ? "正在读取公众号/长图并整理…" : "搜索比赛"}</button>
        <button class="btn ghost" type="button" data-go="team">去组队</button>
      </div>
      <p class="muted">搜到后这里只显示概要。细则写入赛事记忆，保存后才出现在「参加过的比赛」。</p>
    </form>`;
}

function planRows() {
  if (state.squad.squad.confirmed && state.squad.squad.draft.length) return state.squad.squad.draft;
  return state.squad.members.map((member) => {
    const extract = member.extract || "";
    const optional = extract === "海报" || (extract.includes("海报") && !["前端", "后端", "产品", "接口", "页面", "文档"].some((word) => extract.includes(word)));
    return { name: member.name, work: extract || "还没贴介绍", priority: member.role ? (optional ? "should" : "must") : "should" };
  });
}

function viewTeam() {
  if (!state.squad) {
    const contests = savedContests();
    const selected = contests.find((contest) => contest.id === state.contestId) || null;
    const pool = contests.map((contest) => contestCard(contest, `<div class="row" style="margin-top:14px"><button class="btn ${contest.id === selected?.id ? "" : "ghost"}" type="button" data-act="useContest" data-id="${esc(contest.id)}">${contest.id === selected?.id ? "已选这张比赛卡" : "用这张比赛卡组队"}</button></div>`)).join("");
    const pending = selected?.theme_status === "pending";
    const create = selected ? `<form data-act="createSquad" class="card">
          <p class="kicker">比赛组队 · ${esc(selected.name)}</p>
          <input type="hidden" name="contest_id" value="${esc(selected.id)}">
          <label for="squad-name">队伍名称</label>
          <input id="squad-name" name="name" maxlength="40" placeholder="例如：回响小队" required>
          ${pending
            ? `<p>具体主题待揭晓</p><p class="muted">官方公告写明现场公布，建队时不填写开发内容。</p>`
            : `<label for="project-brief">本次项目准备开发什么</label><textarea id="project-brief" name="project_brief" required placeholder="自由命题：写下这次要做的内容"></textarea>`}
          <button class="btn" type="submit">创建队伍</button>
        </form>` : `<div class="card"><p>先从比赛卡池里点一张，再填写队名。</p></div>`;
    return page(`<h2>比赛组队</h2>
      <p class="muted">从你保存的比赛卡里选一场。还没有卡，先到赛事里搜索并确认。</p>
      <div class="contest-grid">${pool || `<p class="muted">比赛卡池是空的。<button class="linkish" type="button" data-go="contest">去搜索比赛</button></p>`}</div>
      <div class="split">
        ${create}
        <form data-act="joinSquad" class="card">
          <p class="kicker">用邀请码入队</p>
          <label for="join-code">队伍码</label>
          <input id="join-code" name="code" autocomplete="off" required>
          <button class="btn" type="submit">加入</button>
          <p class="muted">不必先成为好友。加人之后的名额在团队空间里管。</p>
        </form>
      </div>`);
  }
  const squad = state.squad.squad;
  const contest = state.squad.contest || {};
  const pending = contest.theme_status === "pending";
  const ready = state.squad.members.length >= 2 && state.squad.members.every((member) => member.role && (member.responsibility || member.extract));
  const roleOptions = ROLES.map((role) => `<option>${esc(role)}</option>`).join("");
  const people = state.squad.members.map((member) => `<div class="person"><strong>${esc(member.name)}</strong> ${member.captain ? "<span class=\"tag\">队长</span>" : ""} <span class="tag">${esc(member.role || "还没选职位")}</span><p>${esc(member.responsibility || member.extract || "还没写本次负责的内容")}</p></div>`).join("");
  return page(`<h2>组队</h2>
    <div class="card">
      <p class="kicker">${esc(contest.name || "比赛")} · ${esc(themeLabel(contest))}</p>
      <form data-act="renameSquad" class="row">
        <label for="rename" class="muted">队伍名称</label>
        <input id="rename" name="name" value="${esc(squad.name)}" ${state.squad.me.captain ? "" : "readonly"}>
        ${state.squad.me.captain ? `<button class="btn ghost" type="submit">改名称</button>` : ""}
      </form>
      ${pending
        ? `<p>具体主题待揭晓</p>`
        : (state.squad.me.captain ? `<form data-act="saveBrief"><label for="brief">项目开发内容</label><textarea id="brief" name="project_brief">${esc(squad.project_brief || "")}</textarea><button class="btn ghost" type="submit">保存开发内容</button></form>` : `<p>${esc(squad.project_brief || "待队长补充项目开发内容")}</p>`)}
      <p class="kicker">邀请码</p>
      <p class="code">${esc(squad.code)}</p>
      <button class="btn ghost" type="button" data-act="copyCode">复制邀请码</button>
      <p class="muted">建队后，消息栏会出现同名团队群。新成员请到团队空间加入。</p>
    </div>
    <div class="card">
      <p class="kicker">每个人一个名字框</p>
      ${people}
      <form data-act="saveIntro">
        <label for="role">我本次负责的职位</label>
        <select id="role" name="role">${roleOptions}<option value="其他">其他，自己填写</option></select>
        <label for="role-custom">其他职位</label>
        <input id="role-custom" name="role_custom" placeholder="选了「其他」再填">
        <label for="responsibility">本次具体负责哪一块</label>
        <input id="responsibility" name="responsibility" required placeholder="例如：报名页、路演稿、用户访谈">
        <button class="btn" type="submit">保存我的职位</button>
      </form>
      ${squad.confirmed ? `<p class="muted">分工已确认。任务在看板的思维导图里改，这里不再整份重排。</p>` : `<button class="btn" type="button" data-act="confirmTeam" ${state.squad.me.captain && ready ? "" : "disabled"}>${state.squad.me.captain ? "确认这版分工" : "等队长确认"}</button>
        <p class="muted">${ready ? "至少两人，且每人都选了职位并写了负责内容。" : "至少两人，且每人都选了职位并写了负责内容。"}</p>`}
    </div>`);
}

function viewSuccess() {
  return `<div class="card pay"><div>
    <div class="tick" aria-hidden="true">✓</div>
    <h2>组队成功</h2>
    <p class="muted">对勾先出现，然后是阶段条。第一阶段是选题确认。</p>
    <ol class="stages"><li class="now">选题确认</li><li>之后的阶段还没定名</li></ol>
    <button class="btn" type="button" data-go="home">回到首页</button>
  </div></div>`;
}

function hubCard(go, title, desc) {
  return `<button class="hub-card" type="button" data-go="${go}"><strong>${esc(title)}</strong><span>${esc(desc)}</span></button>`;
}

function viewHome() {
  const squadLine = state.squad?.squad?.name ? `当前队伍：${state.squad.squad.name}` : "还没有加入队伍";
  const contestLine = state.squad?.contest?.name || (state.me?.contests || [])[0]?.name || "还没有确认比赛";
  return `<h2>首页</h2>
    <p class="muted">先选一块系统。左侧只保留头像；功能从这里展开。</p>
    <p class="hint">${esc(nextStep())}</p>
    <div class="hub-grid">
      <button class="hub-tile" type="button" data-go="hubContest">
        <strong>比赛系统</strong>
        <span>赛事信息、团队空间、我的空间</span>
        <em>${esc(contestLine)} · ${esc(squadLine)}</em>
      </button>
      <button class="hub-tile" type="button" data-go="hubMine">
        <strong>我的系统</strong>
        <span>好友、参加过的比赛、成长、技术栈</span>
        <em>${esc(state.me?.name || "")}</em>
      </button>
    </div>`;
}

function viewHubContest() {
  const ready = !!(state.squad?.squad?.confirmed);
  const contest = state.squad?.contest;
  const clock = contest ? `<div class="card">
      <p class="kicker">${esc(contest.name)} · ${esc(stageName())}</p>
      <p class="count" style="font-size:36px">${esc(when(contest.deadline))}</p>
      <p class="muted">实时倒计时收在屏幕最上沿，鼠标移上去展开。这里是同一截止时间。</p>
    </div>` : "";
  return `<h2>比赛系统</h2>
    <p class="muted"><button class="linkish" type="button" data-go="home">← 首页</button></p>
    ${clock}
    <div class="hub-modules">
      ${hubCard("contest", "搜索比赛", "搜一场，保存成赛事卡")}
      ${hubCard("team", "比赛组队", "从比赛卡池选一场，再创建队伍")}
      ${hubCard("teamspace", "团队空间", ready ? "任务树、成果架、仓库、讨论入口" : "组队并确认分工后可用")}
      ${hubCard("mine", "我的空间", ready ? "我这场的任务与截止" : "组队并确认分工后可用")}
    </div>
    ${ready ? `<div class="card"><p class="kicker">比赛中常用</p><div class="row">
      <button class="btn ghost" type="button" data-go="topics">选题</button>
      <button class="btn ghost" type="button" data-go="talk">讨论</button>
      <button class="btn ghost" type="button" data-go="vote">表决</button>
      <button class="btn ghost" type="button" data-go="skill">同一技能</button>
      <button class="btn ghost" type="button" data-go="docs">需求与流程</button>
      ${state.squad?.me?.captain ? `<button class="btn ghost" type="button" data-go="captain">队长规划</button>` : ""}
      <button class="btn ghost" type="button" data-go="log">更改记录</button>
    </div></div>` : ""}`;
}

function viewHubMine() {
  return `<h2>我的系统</h2>
    <p class="muted"><button class="linkish" type="button" data-go="home">← 首页</button></p>
    <div class="hub-modules">
      ${hubCard("friends", "好友", "用手机号添加好友（不是加入队伍的门槛）")}
      ${hubCard("past", "参加过的比赛", "已确认过的赛讯与关键信息")}
      ${hubCard("growth", "成长系统", "赛后记下的能力与完成记录")}
      ${hubCard("stack", "我的技术栈", "画像、技能，以及个人记忆")}
    </div>`;
}

function viewFriends() {
  const card = state.friendCard;
  const tags = (card?.skills || []).map((skill) => `<span>${esc(skill)}</span>`).join("");
  const squads = (card?.squads || []).map((squad) => `<p>${esc(squad.name)} · ${esc(squad.contest)}</p>`).join("");
  const contests = (card?.contests || []).map((name) => `<p>${esc(name)}</p>`).join("");
  const detail = card ? `<article class="contest-card">
      <h3>${esc(card.name)}</h3>
      <p class="muted">${esc(card.phone || "未显示手机号")}</p>
      <p>${esc(card.profile || "还没写简介。")}</p>
      <div class="contest-chips">${tags || "<span>还没写主要工作</span>"}</div>
      <p class="kicker">参加过的比赛</p>${contests || "<p class=\"muted\">还没有赛事卡。</p>"}
      <p class="kicker">所在团队</p>${squads || "<p class=\"muted\">还没有队伍。</p>"}
    </article>` : "<p class=\"muted\">左边点一个好友。</p>";
  return `<h2>好友</h2>
    <form data-act="addFriend" class="card">
      <label for="friend-phone">对方注册用的手机号</label>
      <input id="friend-phone" name="phone" inputmode="numeric">
      <button class="btn" type="submit">加为好友</button>
      <p class="muted">好友不是加入队伍的门槛。有队伍码即可加入。社区报名这版先不做。</p>
    </form>
    ${detail}`;
}

function viewPast() {
  const cards = savedContests().map((contest) => contestCard(contest, `<div class="row" style="margin-top:14px"><button class="btn" type="button" data-act="useContest" data-id="${esc(contest.id)}">用这场组队</button></div>`)).join("");
  return `<h2>参加过的比赛</h2>
    <p class="muted"><button class="linkish" type="button" data-go="hubMine">← 我的系统</button></p>
    <div class="contest-grid">${cards || "<p class=\"muted\">还没有赛事卡。去比赛系统 → 搜索比赛。</p>"}</div>`;
}

function viewStack() {
  const me = state.me || {};
  return page(`<h2>我的技术栈</h2>
    <p class="muted"><button class="linkish" type="button" data-go="hubMine">← 我的系统</button></p>
    <div class="card">
      <p class="kicker">目前登记</p>
      <p><strong>${esc(me.name || "")}</strong></p>
      <p>技能：${esc(me.skills || "还没填")}</p>
      <p class="muted">${esc(me.profile || "")}</p>
      <div class="row">
        <button class="btn ghost" type="button" data-go="profile">编辑资料</button>
        <button class="btn ghost" type="button" data-go="memory">个人记忆与能力记录</button>
      </div>
    </div>`);
}

function stageName() {
  const squad = state.squad.squad;
  if (squad.finished) return "这场已结束";
  if (!squad.topic) return "选题确认";
  return "选题已确认";
}

function viewMine() {
  const mine = state.squad.tasks.filter((task) => task.owner_id === state.squad.me.id);
  const cards = mine.map((task) => `<form data-act="saveProgress" class="card">
      <input type="hidden" name="id" value="${esc(task.id)}">
      <p><span class="tag ${task.priority === "must" ? "must" : ""}">${task.priority === "must" ? "必须" : "可选"}</span> ${esc(task.title)}</p>
      <p>截止：${esc(when(task.due_at))}</p>
      <p>${task.alone ? "<span class=\"tag\">可以自己做</span>" : `<span class="tag">要找 ${esc(task.talk_to || "队友")} 商量</span>`}</p>
      <div class="bar"><span style="width:${task.progress}%"></span></div>
      <label for="progress-${esc(task.id)}">进度 0 到 100</label>
      <input id="progress-${esc(task.id)}" name="progress" type="number" min="0" max="100" step="1" value="${task.progress}" required>
      <label for="doing-${esc(task.id)}">我正在做</label>
      <input id="doing-${esc(task.id)}" name="doing" maxlength="40" value="${esc(state.squad.me.doing)}" placeholder="例如：正在收规则">
      <button class="btn" type="submit">更新我的进度</button>
    </form>`).join("");
  return page(`<h2>我的空间</h2>
    <p class="muted">只看我这场的任务和截止时间。别人的任务在团队空间。</p>
    ${cards || `<div class="card"><p>队长还没把任务发到你名下。</p></div>`}
    <p class="muted">私人教练的重要回答，可以贴进讨论。会改题目、主干或提交清单的，先表决。</p>`);
}

function viewTeamspace() {
  if (!state.squad) return viewTeam();
  const squad = state.squad;
  const must = squad.tasks.filter((task) => task.priority === "must");
  const optional = squad.tasks.filter((task) => task.priority !== "must");
  const taskLine = (task) => `<li>${esc(nameOf(task.owner_id))} · ${esc(task.title)} <div class="bar"><span style="width:${task.progress}%"></span></div></li>`;
  const people = squad.members.map((member) => `<div class="who">${avatarHtml(member.avatar_url, member.name || member.avatar)}<div>${esc(member.name)} · ${esc(member.role || "未选角色")}<br><span class="muted">${esc(member.doing || "还没说正在做什么")}</span></div></div>`).join("");
  const shelf = squad.shelf.map((item) => {
    const editable = item.author_id === squad.me.id || item.editors.includes(squad.me.id);
    return `<div class="item"><strong>${esc(item.title)}</strong><br><span class="muted">${esc(item.kind)} · ${esc(nameOf(item.author_id))}</span><pre>${esc(item.body)}</pre>${editable ? `<form data-act="editShelf"><input type="hidden" name="id" value="${esc(item.id)}"><textarea name="body">${esc(item.body)}</textarea><button class="btn ghost" type="submit">保存修改</button></form>` : `<p class="muted">全队可见。${item.editors.length ? `可编辑：${item.editors.map((id) => esc(nameOf(id))).join("、")}` : "还没有额外授权。"}</p>`}</div>`;
  }).join("");
  const invitees = (state.me?.friends || []).filter((friend) => !squad.members.some((member) => member.user_id === friend.user_id));
  const invite = squad.me.captain ? `<form data-act="inviteFriend" class="card">
      <p class="kicker">在团队空间加入成员</p>
      <label for="invite-friend">邀请已互加的好友</label>
      <select id="invite-friend" name="friend_id" ${invitees.length ? "" : "disabled"}>${invitees.map((friend) => `<option value="${esc(friend.user_id)}">${esc(friend.name)}</option>`).join("") || "<option value=\"\">还没有可邀请的好友</option>"}</select>
      <button class="btn" type="submit" ${invitees.length ? "" : "disabled"}>邀请入队</button>
      <p class="muted">群聊里只能看成员。加人只在这里。</p>
    </form>` : `<p class="muted">新成员由队长在团队空间邀请，或使用邀请码。</p>`;
  return page(`<h2>团队空间</h2>
    <div class="card">
      <p class="kicker">团队模型的综合判断</p>
      <p>${esc(squad.team_overview || "还没有综述。它只读取职位、职责，以及成员明确上传的资料。")}</p>
      <button class="btn ghost" type="button" data-act="refreshOverview">根据资料库重新看一遍</button>
    </div>
    ${invite}
    <div class="card"><p class="kicker">本场必须完成</p>${submissionsOf(squad.contest.submissions)}</div>
    <div class="card"><p class="kicker">现在谁在做什么</p>${people}</div>
    <div class="card">
      <p class="kicker">任务树</p>
      <ul class="tree"><li><span class="tag must">主干</span> ${esc(squad.squad.trunk || "题目确认后才会写下主干")}
        <ul>${must.map(taskLine).join("") || "<li class=\"muted\">还没有必须任务</li>"}
          ${optional.length ? `<li><span class="tag">分支 · 可选</span><ul>${optional.map(taskLine).join("")}</ul></li>` : ""}
        </ul>
      </li></ul>
      <div class="row">
        <button class="btn ghost" type="button" data-go="captain">队长规划</button>
        <button class="btn ghost" type="button" data-go="vote">看团队表决</button>
      </div>
    </div>
    <div class="card">
      <p class="kicker">成果架</p>
      <div class="shelf">${shelf || `<div class="item">还没有成果</div>`}</div>
      <form data-act="uploadShelf">
        <label for="shelf-kind">放上什么</label>
        <select id="shelf-kind" name="kind"><option value="link">演示链接</option><option value="ppt">PPT 要点</option><option value="flow">流程图</option><option value="note">笔记</option></select>
        <label for="shelf-title">名称</label><input id="shelf-title" name="title" required>
        <label for="shelf-body">内容</label><textarea id="shelf-body" name="body" placeholder="PPT 粘贴要点。本机不接收文件。"></textarea>
        ${editorBoxes()}
        <button class="btn" type="submit">放到成果架</button>
      </form>
      <div class="row">
        ${squad.me.github_linked ? "" : `<button class="btn ghost" type="button" data-act="markGithub">标成本机已绑定 GitHub</button>`}
        <button class="btn" type="button" data-act="makeRepo" ${squad.me.captain ? "" : "disabled"}>建立本机团队仓库记录</button>
      </div>
      <p class="muted">不会调用 GitHub。记录只留在成果架，地址以 local:// 开头。</p>
    </div>`);
}

function ideaCard(idea, index) {
  const locked = state.squad.squad.topic;
  return `<div class="card"><strong>${index}. ${esc(idea.core)}</strong>
    <p class="muted">${esc(nameOf(idea.author_id))} · 贴题 ${level(idea.fit)} · 队内 ${level(idea.ability)} · 截止前 ${level(idea.finishable)}</p>
    <p>可能卡住：${esc(idea.problems)}</p>
    <p>做得到：${esc(idea.realistic)}</p>
    ${!locked && state.squad.me.captain ? `<button class="btn" type="button" data-act="confirmTopic" data-id="${esc(idea.id)}">确认这条为本队题目</button>` : ""}
  </div>`;
}

function viewTopics() {
  const ideas = state.squad.ideas;
  const topic = state.squad.squad.topic;
  return page(`<h2>选题空间</h2>
    <p class="muted">只排本队候选。公开赛讯已经从选择比赛导入。要引用旧对话，把那段贴在这里，不会自动读取。</p>
    ${topic ? `<div class="card"><p class="kicker">已确认的题目</p><p>${esc(topic)}</p><p class="muted">主干：${esc(state.squad.squad.trunk)}</p><button class="btn" type="button" data-go="skill">去安装同一技能</button></div>` : ""}
    ${topic ? "" : `<form data-act="sendIdea" class="card">
      <label for="idea">送入一条想法评估</label>
      <textarea id="idea" name="body" required placeholder="写下想法。若要引用某段旧对话，把那段贴在这里。"></textarea>
      <button class="btn" type="submit">送入</button>
    </form>`}
    <p class="kicker">前三名 · 与后面的候选分开</p>
    <div class="top3">${ideas.top.map((idea, index) => ideaCard(idea, index + 1)).join("") || `<div class="card">还没有想法。</div>`}</div>
    <div class="card"><p class="kicker">其余本队候选</p>${ideas.rest.length ? ideas.rest.map((idea) => `<p>${esc(idea.core)}</p>`).join("") : "<p class=\"muted\">没有更多候选。</p>"}</div>`);
}

function viewSkill() {
  const rows = state.squad.members.map((member) => `<div class="person">${esc(member.name)} · ${esc(member.tool || "还没选工具")} · ${member.skill_installed ? "已标记安装这一份" : "待安装这一份"}</div>`).join("");
  return page(`<h2>安装同一技能</h2>
    <p class="muted">全队装同一份，不按人改写。本机只标记，不会装进真正的 Codex 或 Workbuddy。</p>
    <div class="card">
      <pre>${esc(state.squad.squad.skill_body)}</pre>
      <div class="row">
        <button class="btn" type="button" data-act="downloadSkill">下载这一份</button>
        <button class="btn ghost" type="button" data-act="installSkill" data-tool="codex">标记装进 Codex</button>
        <button class="btn ghost" type="button" data-act="installSkill" data-tool="workbuddy">标记装进 Workbuddy</button>
      </div>
      ${rows}
      <p class="muted">两个人下载到的文字相同。技术做法不在这份文件里。</p>
    </div>`);
}

function viewTalk() {
  const notes = state.squad.library.map((note) => `<div class="bubble"><strong>${esc(nameOf(note.author_id))}</strong><br>${esc(note.body)}<p class="tag">已写入团队资料库</p><p class="muted">${esc(note.suggestion)}</p></div>`).join("");
  return page(`<h2>讨论</h2>
    <div class="card">
      ${notes || `<p class="muted">发出的话会进资料库。普通内容不改主干。</p>`}
      <form data-act="sendLibrary" class="composer">
        <input name="body" aria-label="队内讨论" placeholder="发到队内讨论" required>
        <button class="btn" type="submit">发送</button>
      </form>
      <p class="muted">若这句话要改题目、主干或提交清单，会转到团队表决，任务板先不动。</p>
      <button class="btn ghost" type="button" data-go="vote">查看表决</button>
    </div>`);
}

function viewDocs() {
  const linked = state.squad.me.feishu_linked;
  return page(`<h2>需求与流程图</h2>
    <p class="muted">题目定了之后。飞书仍用来写正式稿。这里留下黑客松简版，不打开飞书。</p>
    <div class="card">
      <p class="kicker">${linked ? "已标成本机绑定飞书" : "还没标记飞书"}</p>
      <div class="row">
        <button class="btn ghost" type="button" data-act="markFeishu">${linked ? "取消飞书标记" : "标成本机已绑定飞书"}</button>
        <button class="btn ghost" type="button" data-act="leaveBrief" data-title="需求文档">需求文档简版</button>
        <button class="btn ghost" type="button" data-act="leaveBrief" data-title="业务流程图">业务流程图简版</button>
        <button class="btn ghost" type="button" data-act="leaveBrief" data-title="页面原型">页面原型简版</button>
      </div>
      <p class="muted">三个简版会直接放上成果架。正式稿请到飞书写。</p>
    </div>
    <form data-act="makeFlow" class="card">
      <label for="flow-request">用一句话画流程图</label>
      <input id="flow-request" name="request" placeholder="例如：讨论，确认题目，安装技能，发布任务" required>
      <button class="btn" type="submit">排成方框</button>
      ${state.flow ? `<pre>${esc(state.flow)}</pre><button class="btn ghost" type="button" data-act="uploadFlow">上传到成果架</button><p class="muted">这张图不改题目和主干，直接上架。</p>` : ""}
    </form>`);
}

function viewVote() {
  const votes = state.squad.votes;
  if (!votes.length) {
    return page(`<h2>团队表决</h2><div class="card"><p>还没有会改题目、主干或提交清单的建议。</p><p class="muted">普通讨论只进资料库。队长发布任务不用走这里。</p></div>`);
  }
  const cards = votes.map((vote) => {
    const mine = vote.ballots.find((ballot) => ballot.user_id === state.squad.me.id);
    const kind = { topic: "题目", trunk: "主干", submissions: "提交清单" }[vote.kind] || vote.kind;
    return `<div class="card">
      <p class="kicker">${esc(nameOf(vote.author_id))} 想改${esc(kind)} · ${vote.status === "recorded" ? "全队已表态" : "还没收齐"} · 未改任务</p>
      <p class="kicker">澄清</p><p>${esc(vote.clarify)}</p>
      <p class="kicker">框架</p><p>${esc(vote.frame)}</p>
      <p class="kicker">截止前，按各自现在的水平</p>
      <ul>${vote.parts.map((part) => `<li>${esc(part.name)}：${esc(part.part)}</li>`).join("")}</ul>
      <p class="muted">${mine ? `你目前选的是${mine.choice === "yes" ? "同意" : "先不改"}。改选会覆盖你的票。` : "你还没表态。"}要通过多少票没定。表态之后也不改题目、主干和提交清单。</p>
      <div class="row">
        <button class="btn ghost" type="button" data-act="cast" data-id="${esc(vote.id)}" data-choice="no">先不改</button>
        <button class="btn" type="button" data-act="cast" data-id="${esc(vote.id)}" data-choice="yes">同意这条建议</button>
      </div>
    </div>`;
  }).join("");
  return page(`<h2>团队表决</h2>${cards}`);
}

function viewCaptain() {
  const pending = state.squad.votes.map((vote) => `<p>${esc(nameOf(vote.author_id))} 的建议会改${esc({ topic: "题目", trunk: "主干", submissions: "提交清单" }[vote.kind] || "")}。先不要把它发布成已定方案。表决在团队表决。</p>`).join("");
  const tasks = state.squad.tasks.map((task) => `<div class="person">
      <strong>${esc(task.title)}</strong>
      <p class="muted">${task.priority === "must" ? "必须" : "可选"} · ${esc(nameOf(task.owner_id))} · ${esc(when(task.due_at))}</p>
      <div class="row">
        <button class="btn ghost" type="button" data-act="flipTask" data-id="${esc(task.id)}" data-next="${task.priority === "must" ? "should" : "must"}">改为${task.priority === "must" ? "可选" : "必须"}</button>
        <form data-act="reassign" class="row">
          <input type="hidden" name="id" value="${esc(task.id)}">
          <select name="owner_id">${memberOptions(task.owner_id)}</select>
          <button class="btn ghost" type="submit">改负责人</button>
        </form>
      </div>
    </div>`).join("");
  return page(`<h2>队长规划</h2>
    <p class="muted">只有队长能打开。和方向商量之后，一次发布一项。发布不等表决，也不推倒整份方案。</p>
    <div class="card"><p class="kicker">队员送来、还没变成任务的建议</p>${pending || "<p>目前没有待表决的战略性建议。</p>"}</div>
    <form data-act="publishTask" class="card">
      <label for="task-title">准备发布的一项任务</label>
      <input id="task-title" name="title" required placeholder="例如：可演示页面">
      <label for="task-owner">负责人</label>
      <select id="task-owner" name="owner_id">${memberOptions("")}</select>
      <label for="task-priority">必须或可选</label>
      <select id="task-priority" name="priority"><option value="must">必须</option><option value="should">可选</option></select>
      <label for="task-due">截止 · 空着就用比赛结束时间</label>
      <input id="task-due" name="due_at" type="datetime-local">
      <label for="task-talk">需要找谁商量 · 空着表示可以自己做</label>
      <input id="task-talk" name="talk_to" placeholder="例如：杨涵">
      <button class="btn" type="submit">发布这一项</button>
    </form>
    <div class="card"><p class="kicker">已发布 · 一次只改一项</p>${tasks || "<p>还没有发布。</p>"}</div>`);
}

function viewLog() {
  const names = Object.fromEntries((state.squad?.members || []).map((member) => [member.user_id, member.name]));
  const rows = (state.squad?.log || []).slice().reverse().map((item) => `<tr><td>${esc(when(item.created_at))}</td><td>${esc(item.actor || names[item.actor_id] || "有人")}</td><td>${esc(item.detail)}</td></tr>`).join("");
  return `<h2>更改记录</h2><div class="card"><table><thead><tr><th>时间</th><th>谁</th><th>做了什么</th></tr></thead><tbody>${rows || "<tr><td colspan=\"3\">还没有记录。</td></tr>"}</tbody></table><p class="muted">只记录。表决不会改任务板。队长发布和调整会留在这里。</p></div>`;
}

function viewGrowth() {
  const growth = state.me?.growth || state.squad?.me?.growth || "";
  const canFinish = !!(state.squad?.me?.captain);
  return page(`<h2>成长系统</h2>
    <p class="muted"><button class="linkish" type="button" data-go="hubMine">← 我的系统</button></p>
    <div class="card">
      <p class="kicker">已经记住的</p>
      <pre>${esc(growth || "还没有成长记录。结束一场比赛后会按角色和完成的任务写下一句。")}</pre>
      ${canFinish ? `<button class="btn" type="button" data-act="finishContest" ${state.squad.squad.finished ? "disabled" : ""}>${state.squad.squad.finished ? "这场已经记过" : "结束这场并写入成长"}</button>` : `<p class="muted">${state.squad ? "由队长结束这场。你的画像不会重问。" : "加入并完成一场比赛后，这里会留下记录。"}</p>`}
    </div>`);
}

const views = {
  login: viewLogin,
  signup: viewSignup,
  contest: viewContest,
  team: viewTeam,
  success: viewSuccess,
  home: viewMessages,
  messages: viewMessages,
  board: viewBoard,
  progress: viewProgress,
  space: viewSpace,
  hubMine: viewHubMine,
  hubContest: viewHubContest,
  friends: viewFriends,
  past: viewPast,
  stack: viewStack,
  mine: viewMine,
  teamspace: viewTeamspace,
  topics: viewTopics,
  skill: viewSkill,
  talk: viewTalk,
  docs: viewDocs,
  vote: viewVote,
  captain: viewCaptain,
  log: viewLog,
  growth: viewGrowth,
  profile: viewProfile,
  memory: viewMemory,
  settings: viewSettings,
};

function isTypingTarget(target) {
  const node = target instanceof Element ? target : target?.parentElement;
  return !!node?.closest("input, textarea, select, option, label");
}

function paintSignupStatus() {
  const status = document.getElementById("entry-status");
  if (!status) return;
  const text = state.error || state.note || "";
  status.hidden = !text;
  status.className = state.error ? "error" : "ok";
  status.textContent = text;
  const note = document.getElementById("reg-code-note");
  const issued = document.getElementById("reg-issued");
  if (note && issued) {
    if (state.issuedCode) {
      note.hidden = false;
      issued.hidden = false;
      issued.textContent = state.issuedCode;
      note.textContent = "这次没有发出短信，数字只出现在测试里。";
    } else {
      issued.hidden = true;
      issued.textContent = "";
      note.hidden = !state.smsNote;
      note.textContent = state.smsNote || "";
    }
  }
  const profile = document.getElementById("reg-profile");
  if (profile) profile.hidden = !state.needProfile;
  const wechat = document.getElementById("reg-wechat");
  if (wechat && state.wechatNote) {
    wechat.hidden = false;
    wechat.textContent = state.wechatNote;
  }
}

function renderSignup() {
  const main = document.getElementById("main");
  const marker = state.screen === "signup" ? "reg-form" : "login-form";
  if (!document.getElementById(marker)) main.innerHTML = state.screen === "signup" ? viewSignup() : viewLogin();
  paintSignupStatus();
}

function menuHtml() {
  return `<div class="popover" id="me-menu" role="menu">
    <button type="button" data-go="home">首页</button>
    <button type="button" data-go="settings">设置</button>
    <button type="button" data-go="profile">编辑资料</button>
    <button type="button" data-go="memory">个人记忆与能力记录</button>
    <button type="button" data-act="logout">退出登录</button>
    <a href="/classic">旧工作台</a>
  </div>`;
}

function railContext() {
  const screen = state.screen;
  if (screen === "home") return "";
  if (["hubMine", "friends", "past", "growth", "stack", "profile", "memory"].includes(screen)) {
    return `<p class="rail-label">我的系统</p>
      <button type="button" data-go="hubMine" class="${screen === "hubMine" ? "on" : ""}">总览</button>
      <button type="button" data-go="friends" class="${screen === "friends" ? "on" : ""}">好友</button>
      <button type="button" data-go="past" class="${screen === "past" ? "on" : ""}">参加过的比赛</button>
      <button type="button" data-go="growth" class="${screen === "growth" ? "on" : ""}">成长系统</button>
      <button type="button" data-go="stack" class="${screen === "stack" ? "on" : ""}">我的技术栈</button>`;
  }
  if (["hubContest", "contest", "team", "teamspace", "mine", "talk", "topics", "skill", "vote", "docs", "captain", "log", "success"].includes(screen)) {
    return `<p class="rail-label">比赛系统</p>
      <button type="button" data-go="hubContest" class="${screen === "hubContest" ? "on" : ""}">总览</button>
      <button type="button" data-go="contest" class="${screen === "contest" ? "on" : ""}">赛事信息</button>
      <button type="button" data-go="team" class="${screen === "team" ? "on" : ""}">组队</button>
      <button type="button" data-go="teamspace" class="${screen === "teamspace" ? "on" : ""}">团队空间</button>
      <button type="button" data-go="mine" class="${screen === "mine" ? "on" : ""}">我的空间</button>`;
  }
  return "";
}

const PRIMARY = [
  ["messages", "消息"],
  ["teamspace", "团队"],
  ["board", "任务"],
  ["progress", "进度"],
  ["friends", "好友"],
  ["contest", "赛事"],
  ["space", "个人"],
];

function renderRail() {
  const rail = document.getElementById("rail");
  if (!rail) return;
  const current = state.screen === "home" ? "messages" : state.screen;
  const icons = PRIMARY.map(([id, label]) => `<button type="button" class="rail-icon ${current === id ? "on" : ""}" data-go="${id}">${esc(label)}</button>`).join("");
  rail.innerHTML = `<button type="button" class="me-btn" data-go="profile" title="修改个人信息">${avatarHtml(state.me?.avatar_url, state.me?.name || "我")}</button>
    <div class="rail-scroll">${icons}</div>`;
}

function renderSubrail() {
  const sub = document.getElementById("subrail");
  const app = document.getElementById("app");
  if (!sub) return;
  const screen = state.screen === "home" ? "messages" : state.screen;
  const open = screen === "messages" || screen === "friends";
  if (app) app.classList.toggle("has-sub", open);
  if (!open) {
    sub.innerHTML = "";
    return;
  }
  if (screen === "friends") {
    const friends = state.me?.friends || [];
    const items = friends.map((friend) => `<button type="button" data-act="openFriend" data-id="${esc(friend.user_id)}" class="${state.friendCard?.user_id === friend.user_id ? "on" : ""}">${esc(friend.name)}<br><span class="muted">${esc(friend.phone || "未显示手机号")}</span></button>`).join("");
    sub.innerHTML = `<div class="sub-head">好友</div><div class="sub-list">${items || "<p class=\"muted\">还没有好友。</p>"}</div>`;
    return;
  }
  const friends = (state.me?.friends || []).map((friend) => `<button type="button" data-act="openThread" data-kind="dm" data-id="${esc(friend.user_id)}" class="${state.threadKind === "dm" && state.threadId === friend.user_id ? "on" : ""}">${esc(friend.name)}</button>`).join("");
  const squads = (state.me?.squads || []).map((squad) => `<button type="button" data-act="openThread" data-kind="squad" data-id="${esc(squad.id)}" class="${state.threadKind === "squad" && state.threadId === squad.id ? "on" : ""}">${esc(squad.name)} · 群</button>`).join("");
  sub.innerHTML = `<div class="sub-head">消息</div><div class="sub-list"><p class="rail-label">好友</p>${friends || "<p class=\"muted\">加了好友才能私聊。</p>"}<p class="rail-label">团队群</p>${squads || "<p class=\"muted\">还没有队伍。</p>"}<button type="button" data-go="vote">投票表决</button></div>`;
}

function threadTitle() {
  if (state.threadKind === "dm") {
    const friend = (state.me?.friends || []).find((item) => item.user_id === state.threadId);
    return friend?.name || "好友";
  }
  if (state.threadKind === "squad") {
    const squad = (state.me?.squads || []).find((item) => item.id === state.threadId);
    return squad?.name || "团队群";
  }
  return "";
}

function viewMessages() {
  if (!state.threadId) {
    return `<h2>消息</h2><p class="muted">从左侧点开好友或团队群。创建队伍后，消息栏会出现同名团队群。</p>`;
  }
  const lines = (state.threadMessages || []).map((line) => {
    const mine = line.sender_id === state.me?.id;
    const who = mine ? "" : `<div class="wx-name">${esc(line.sender_name || "队友")}</div>`;
    return `<div class="wx-row ${mine ? "me" : ""}">${who}<div class="wx-bubble">${esc(line.body)}</div></div>`;
  }).join("");
  const roster = state.threadKind === "squad" && state.showRoster
    ? `<div class="roster"><p class="kicker">群成员</p>${(state.threadRoster || []).map((member) => `<p>${esc(member.name)} · ${esc(member.role || "未填职位")}</p>`).join("") || "<p class=\"muted\">还没有成员。</p>"}<p class="muted">加人请到团队空间，这里不能加。</p></div>`
    : "";
  const chips = (state.agentLines || []).map((line, index) => `<div class="agent-chip" draggable="true" data-agent-index="${index}"><p class="muted">我：${esc(line.me)}</p><p>${esc(line.reply)}</p><button class="btn ghost" type="button" data-act="uploadAgent" data-index="${index}">上传到团队资料库</button></div>`).join("");
  return `<section class="wx-split">
    <section class="wx">
      <div class="wx-bar"><strong>${esc(threadTitle())}</strong><span>
        ${state.threadKind === "squad" ? `<button class="btn ghost" type="button" data-act="toggleRoster">群成员</button>` : ""}
        <button class="btn ghost" type="button" data-act="reloadThread">查看新消息</button>
      </span></div>
      ${roster}
      <div class="wx-log">${lines}</div>
      <form data-act="sendMessage" class="wx-compose">
        <input id="msg-body" name="body" maxlength="2000" placeholder="发消息。可以把右侧回答拖到这里，再点发送" autocomplete="off" autofocus>
        <button class="wx-send" type="submit">发送</button>
      </form>
    </section>
    <aside class="agent">
      <div class="agent-head"><strong>我的智能体</strong><p class="muted">${state.me?.model_ready ? `使用你接入的 ${esc(state.me.model_name || "模型")}。不会自动进群。` : "先在个人页保存你的 API。对话只留在这一侧，除非你拖去发送或上传。"}</p></div>
      <div class="agent-log">${chips || `<p class="muted">在这里问你自己的模型。回答可以拖进左边输入框，或上传到团队资料库。</p>`}</div>
      <form data-act="askAgent" class="agent-compose">
        <input name="message" placeholder="问我的模型" ${state.squadId ? "" : "disabled"}>
        <button class="btn" type="submit" ${state.squadId ? "" : "disabled"}>问</button>
      </form>
    </aside>
  </section>`;
}

function branchNodes(tasks, parentId) {
  return tasks.filter((task) => (task.parent_id || "") === parentId);
}

function mindNode(task, tasks, editing) {
  const children = branchNodes(tasks, task.id).map((child) => mindNode(child, tasks, editing)).join("");
  const editor = editing ? `<form data-act="saveBranch"><input type="hidden" name="id" value="${esc(task.id)}"><input name="title" value="${esc(task.title)}" aria-label="分支文字"><button class="btn ghost" type="submit">保存文字</button></form>
      <form data-act="addBranch"><input type="hidden" name="owner_id" value="${esc(task.owner_id)}"><input type="hidden" name="parent_id" value="${esc(task.id)}"><input name="title" placeholder="新的分支" required><button class="btn ghost" type="submit">加分支</button></form>
      <button class="btn ghost" type="button" data-act="deleteBranch" data-id="${esc(task.id)}">拖进垃圾箱</button>` : `<strong>${esc(task.title)}</strong>`;
  return `<div class="mind-node" draggable="${editing ? "true" : "false"}" data-branch-id="${esc(task.id)}">${editor}${children}</div>`;
}

function viewBoard() {
  const members = state.squad?.members || [];
  const tasks = state.squad?.tasks || [];
  const editing = !!state.boardEdit && !!state.squad?.me?.captain;
  const cols = members.map((member) => {
    const roots = tasks.filter((task) => task.owner_id === member.user_id && !(task.parent_id || ""));
    const nodes = roots.map((task) => mindNode(task, tasks.filter((item) => item.owner_id === member.user_id), editing)).join("") || `<p class="muted">还没有从名字延伸出去的分支。</p>`;
    const addRoot = editing ? `<form data-act="addBranch"><input type="hidden" name="owner_id" value="${esc(member.user_id)}"><input type="hidden" name="parent_id" value=""><input name="title" placeholder="从这个名字长出一条" required><button class="btn ghost" type="submit">加分支</button></form>` : "";
    return `<div class="mind-root"><p class="kicker">${esc(member.name)}</p><p class="muted">${esc(member.role || "未填职位")} · ${esc(member.responsibility || member.doing || "职责待填写")}</p>${nodes}${addRoot}</div>`;
  }).join("");
  const trash = editing ? `<div class="trash" id="task-trash">把不要的分支拖到这里</div>` : "";
  return `<h2>任务看板</h2>
    <div class="row">
      <p class="muted">每个人的名字是思维导图的起点。编辑时可以改文字、加分支，或把分支拖进垃圾箱。</p>
      ${state.squad?.me?.captain ? `<button class="btn ghost" type="button" data-act="toggleBoardEdit">${editing ? "完成编辑" : "编辑"}</button>` : ""}
    </div>
    <div class="mind">${cols || "<p class=\"muted\">先加入或创建队伍。</p>"}</div>
    ${trash}`;
}

function viewProgress() {
  if (!state.squad) return `<h2>个人进度</h2><p class="muted">先加入队伍。</p>`;
  const mine = (state.squad.tasks || []).filter((task) => task.owner_id === state.squad.me.id);
  const items = mine.map((task) => `<li><strong>${esc(task.title)}</strong><p class="muted">截止 ${esc(when(task.due_at))} · 现在 ${esc(task.progress || 0)}%${state.squad.me.doing ? ` · ${esc(state.squad.me.doing)}` : ""}</p>
      <form data-act="saveProgress"><input type="hidden" name="id" value="${esc(task.id)}"><label>正在做</label><input name="doing" value="${esc(state.squad.me.doing || "")}" maxlength="40"><label>进度 0-100</label><input name="progress" type="number" min="0" max="100" value="${esc(task.progress || 0)}"><button class="btn" type="submit">更新</button></form></li>`).join("");
  return `<h2>个人进度</h2>
    <p class="muted">这里比团队看板多写「正在干什么」。更新后团队看板读的是同一条任务。</p>
    <ol class="chain">${items || "<li>还没有分给你的任务。</li>"}</ol>`;
}

function viewSpace() {
  const me = state.me || {};
  const tags = String(me.skills || "").split(/[、,，]/).map((part) => part.trim()).filter(Boolean);
  const chips = tags.map((tag) => `<span>${esc(tag)}</span>`).join("");
  return `<h2>个人空间</h2>
    <div class="card">
      <p class="kicker">画像</p>
      <p><strong>${esc(me.name || "")}</strong></p>
      <p>${esc(me.profile || "还没写自己做过什么。")}</p>
      <div class="contest-chips">${chips || "<span>还没写技能</span>"}</div>
      <div class="row" style="margin-top:12px"><button class="btn ghost" type="button" data-go="profile">修改资料</button><button class="btn ghost" type="button" data-go="memory">个人记忆</button></div>
    </div>
    <div class="card"><p class="kicker">做过的比赛</p>
      <button class="btn ghost" type="button" data-go="past">查看全部比赛卡</button>
      ${savedContests().map((contest) => `<p>${esc(contest.name)}</p>`).join("") || "<p class=\"muted\">还没有赛事卡。</p>"}
    </div>
    <div class="card"><p class="kicker">成长</p><pre>${esc(me.growth || "结束一场比赛后，这里按真实完成的任务记一句。")}</pre></div>`;
}

function render() {
  const app = document.getElementById("app");
  if (!state.token) {
    if (state.screen !== "signup" && state.screen !== "login") state.screen = "login";
    state.menuOpen = false;
    if (app) app.classList.remove("signed");
    const rail = document.getElementById("rail");
    if (rail) rail.innerHTML = "";
    renderSignup();
    clearInterval(state.tick);
    state.tick = null;
    return;
  }
  if (app) app.classList.add("signed");
  renderRail();
  renderSubrail();
  const view = views[state.screen] || viewHome;
  document.getElementById("main").innerHTML = banners() + view();
  const log = document.querySelector(".wx-log");
  if (log) log.scrollTop = log.scrollHeight;
  armCountdown();
}

function contestDropZone(node) {
  return node && (node.id === "contest-drop" || (node.closest && node.closest("#contest-drop")));
}

function urlFromShortcutText(text) {
  const blob = text || "";
  const plist = /<key>URL<\/key>\s*<string>(.*?)<\/string>/i.exec(blob);
  if (plist) return plist[1].trim();
  const ini = /^\s*URL\s*=\s*(\S+)/im.exec(blob);
  if (ini) return ini[1].trim();
  const http = /https?:\/\/[^\s<>"']+/i.exec(blob);
  return http ? http[0].replace(/[)，。；、！？]+$/, "") : "";
}

const WECHAT_DROP_TIP = "微信群里的公众号卡片拖不进浏览器（微信不提供真实链接）。请点开卡片 → 右上角 ⋯ → 复制链接 → 再点「从剪贴板导入公众号链接」。";

function urlsFromDataTransfer(dt) {
  const chunks = [];
  const types = dt?.types ? Array.from(dt.types) : [];
  for (const type of types) {
    try {
      const value = dt.getData(type);
      if (value) chunks.push(value);
    } catch {
      /* some types are not readable */
    }
  }
  const uri = dt.getData("text/uri-list") || "";
  const plain = dt.getData("text/plain") || "";
  const html = dt.getData("text/html") || "";
  const joined = [uri, plain, html, ...chunks].join("\n");
  const href = /href=["']([^"']+)["']/i.exec(html || joined);
  const fromUri = uri.split(/\r?\n/).map((line) => line.trim()).find((line) => /^https?:\/\//i.test(line) && !line.startsWith("#"));
  return {
    url: fromUri || (href ? href[1] : "") || urlFromShortcutText(joined),
    text: plain || html.replace(/<[^>]+>/g, " ") || joined,
    hadTypes: types.length > 0,
  };
}

function stashContestAttachment(patch) {
  const nameInput = document.getElementById("cname");
  const urlInput = document.getElementById("curl");
  state.contestDraft = {
    ...(state.contestDraft || {}),
    name: nameInput?.value || state.contestDraft?.name || "",
    url: urlInput?.value || state.contestDraft?.url || "",
    ...patch,
  };
  state.note = patch.note || "已附上资料，点「确认比赛」开始整理。";
  state.screen = "contest";
  render();
}

async function handleContestDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  const zone = document.getElementById("contest-drop");
  if (zone) zone.classList.remove("on");
  state.error = "";
  state.screen = "contest";
  try {
    const dt = event.dataTransfer;
    const file = dt?.files?.[0];
    if (file && (file.size > 0 || (file.name || "").length > 0)) {
      const name = (file.name || "").toLowerCase();
      if (name.endsWith(".webloc") || name.endsWith(".url") || file.size < 8000) {
        try {
          const text = await file.text();
          const link = urlFromShortcutText(text);
          if (link) {
            stashContestAttachment({ url: link, fileName: "", fileText: "", note: "已放入公众号链接，点「确认比赛」。" });
            return;
          }
          if (text.trim()) {
            stashContestAttachment({ fileText: text, fileName: file.name || "拖入的文字", note: "已附上文字资料，点「确认比赛」。" });
            return;
          }
        } catch {
          /* fall through */
        }
      }
      if (file.size > 0) {
        const formData = new FormData();
        formData.append("file", file);
        const data = await apiUpload("/api/studio/contests/import-file", formData);
        if (data.url) {
          stashContestAttachment({ url: data.url, fileName: "", fileText: "", note: "已放入链接，点「确认比赛」。" });
          return;
        }
        stashContestAttachment({
          fileText: data.source_text || "",
          fileName: data.filename || file.name,
          note: "已附上文件，点「确认比赛」。",
        });
        return;
      }
    }
    const found = urlsFromDataTransfer(dt);
    if (found.url) {
      stashContestAttachment({ url: found.url, note: "已放入链接，点「确认比赛」。" });
      return;
    }
    if (String(found.text || "").trim()) {
      stashContestAttachment({ fileText: found.text, fileName: "拖入的文字", note: "已附上文字，点「确认比赛」。" });
      return;
    }
    throw new Error(WECHAT_DROP_TIP);
  } catch (error) {
    state.error = error.message || WECHAT_DROP_TIP;
    render();
  }
}

function installContestDnD() {
  if (window.__songbanContestDnD) return;
  window.__songbanContestDnD = true;
  const mark = (on) => {
    const zone = document.getElementById("contest-drop");
    if (zone) zone.classList.toggle("on", on);
  };
  document.addEventListener("dragenter", (event) => {
    if (!contestDropZone(event.target)) return;
    event.preventDefault();
    mark(true);
  });
  document.addEventListener("dragover", (event) => {
    if (!contestDropZone(event.target)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    mark(true);
  });
  document.addEventListener("dragleave", (event) => {
    const zone = document.getElementById("contest-drop");
    if (!zone) return;
    if (!zone.contains(event.relatedTarget)) mark(false);
  });
  document.addEventListener("drop", (event) => {
    if (!contestDropZone(event.target)) return;
    handleContestDrop(event);
  });
  document.addEventListener("paste", async (event) => {
    if (state.screen !== "contest" || !state.token) return;
    const target = event.target;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA") && target.id !== "contest-drop") return;
    const text = event.clipboardData?.getData("text/plain") || "";
    const link = urlFromShortcutText(text);
    if (!link && !/mp\.weixin\.qq\.com\/s/i.test(text)) return;
    event.preventDefault();
    state.error = "";
    stashContestAttachment({ url: link || text.trim(), note: "已粘贴链接，点「确认比赛」。" });
  });
  document.addEventListener("change", async (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.id !== "cfile") return;
    const file = input.files?.[0];
    if (!file) return;
    state.error = "";
    try {
      const formData = new FormData();
      formData.append("file", file);
      const data = await apiUpload("/api/studio/contests/import-file", formData);
      if (data.url) {
        stashContestAttachment({ url: data.url, note: "已放入链接，点「确认比赛」。" });
      } else {
        stashContestAttachment({
          fileText: data.source_text || "",
          fileName: data.filename || file.name,
          note: "已附上文件，点「确认比赛」。",
        });
      }
    } catch (error) {
      state.error = error.message;
      render();
    } finally {
      input.value = "";
    }
  });
}

function activeContest() {
  if (state.squad?.contest?.deadline) return state.squad.contest;
  const saved = savedContests();
  return saved.find((contest) => contest.id === state.contestId) || state.contestPreview || saved[0] || null;
}

function paintDeadlineDock() {
  const dock = document.getElementById("deadline-dock");
  if (!dock) return;
  const contest = activeContest();
  const show = !!(state.token && contest?.deadline && COUNTDOWN_SCREENS.has(state.screen));
  dock.hidden = !show;
  if (!show) return;
  const source = contest.official_url
    ? (contest.deadline_checked_at ? "依据最后一次从官方页面确认的作品截止时间" : "赛事卡已有官方链接，尚未复核。显示卡上的截止时间")
    : "没有官方页面，显示你确认时写入比赛卡的截止时间";
  dock.innerHTML = `<div class="deadline-tab" tabindex="0"><span class="deadline-peek">倒计时</span><div class="deadline-full"><strong id="count">--:--:--</strong><p>${esc(contest.name)}</p><p>${esc(source)}</p><p>截止 ${esc(when(contest.deadline))}</p>${contest.official_url ? `<button class="btn ghost" type="button" data-act="syncDeadline" data-id="${esc(contest.id)}">按官方页面复核</button>` : ""}</div></div>`;
}

function armCountdown() {
  clearInterval(state.tick);
  state.tick = null;
  paintDeadlineDock();
  const contest = activeContest();
  if (!contest?.deadline || !COUNTDOWN_SCREENS.has(state.screen)) return;
  const end = new Date(contest.deadline);
  const paint = () => {
    const node = document.getElementById("count");
    if (!node) return;
    if (Number.isNaN(end.getTime())) { node.textContent = "时间未导入"; return; }
    const left = end - Date.now();
    if (left <= 0) { node.textContent = "已截止"; return; }
    const hours = Math.floor(left / 3600000);
    const minutes = Math.floor((left % 3600000) / 60000);
    const seconds = Math.floor((left % 60000) / 1000);
    const pad = (n) => String(n).padStart(2, "0");
    node.textContent = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  };
  paint();
  state.tick = setInterval(paint, 1000);
}

async function go(id) {
  if (!state.token && id !== "login" && id !== "signup") {
    state.screen = "login";
    render();
    return;
  }
  if (!state.token) {
    state.screen = id;
    state.error = "";
    render();
    return;
  }
  const gate = canOpen(id);
  if (gate !== true) {
    state.error = gate;
    render();
    return;
  }
  state.error = "";
  state.note = "";
  state.menuOpen = false;
  state.screen = id;
  if (state.token && id !== "signup") {
    try {
      await reload();
      if (id === "messages") await loadThread();
    } catch (error) { state.error = error.message; }
  }
  render();
}

async function adopt(data, _phone) {
  clearPrivateView();
  state.token = data.token;
  state.needProfile = false;
  state.issuedCode = "";
  state.wechatTicket = "";
  saveSession();
  state.me = await api("GET", "/api/studio/me");
  state.squad = null;
  state.squadId = "";
  if (state.me.squads[0]) {
    rememberSquad(state.me.squads[0].id);
    state.squad = await api("GET", `/api/studio/squads/${state.squadId}`);
  }
  if (!state.contestId && state.me.contests[0]) state.contestId = state.me.contests[0].id;
  saveSession();
  state.note = data.notice || "";
  state.screen = "messages";
}

const actions = {
  async requestCode(button) {
    const form = button.closest("form");
    const phone = form.phone.value.trim();
    const data = await api("POST", "/api/studio/codes", { phone });
    state.issuedCode = "";
    state.note = data.notice;
    state.error = "";
  },
  async wechat() {
    const data = await api("GET", "/api/studio/connect");
    if (data.wechat && data.wechat.ready) {
      const invite = state.wechatInvite || new URLSearchParams(location.search).get("wechat_invite") || "";
      if (invite) sessionStorage.setItem("songban_wechat_invite", invite);
      window.location.assign("/api/studio/wechat/start");
      return;
    }
    state.wechatNote = ((data.wechat && data.wechat.missing) || []).join(" ");
    state.error = state.wechatNote || "微信登录还没配好。";
    state.token = "";
  },
  async wechatInvite() {
    const data = await api("POST", "/api/studio/wechat/invite");
    state.note = data.notice || "邀请已生成。";
    const box = document.getElementById("wechat-invite-link");
    if (box) {
      box.hidden = false;
      box.textContent = data.link || data.code;
    }
    try { await navigator.clipboard.writeText(data.link || data.code); state.note += " 链接已复制。"; } catch (_) {}
  },
  toggleMenu() {
    state.menuOpen = !state.menuOpen;
    renderRail();
  },
  logout() {
    clearPrivateView();
    state.token = "";
    state.me = null;
    state.squad = null;
    state.squadId = "";
    state.menuOpen = false;
    state.screen = "login";
    saveSession();
  },
  async saveProfile(form) {
    const data = await api("PATCH", "/api/studio/me", { name: val(form, "name").trim(), profile: val(form, "profile").trim(), skills: val(form, "skills").trim() });
    state.note = "资料已保存。";
    saveSession();
    await reload();
  },
  async addMemory(form) {
    const data = await api("POST", "/api/studio/memory", { text: form.text.value });
    state.note = "已记入个人记忆。没有读取旧对话。";
    if (state.me) state.me.growth = data.growth;
    await reload();
  },
  async login(form) {
    const data = await api("POST", "/api/studio/login", {
      account: form.phone.value.trim(),
      password: form.password.value,
    });
    await adopt(data, data.phone || form.account.value.trim());
  },
  async enter(form) {
    if (state.wechatTicket) {
      const invite = state.wechatInvite || sessionStorage.getItem("songban_wechat_invite") || "";
      const data = await api("POST", "/api/studio/wechat/finish", {
        ticket: state.wechatTicket,
        invite,
        name: val(form, "name").trim(),
        profile: val(form, "profile").trim(),
        skills: val(form, "skills").trim(),
      });
      sessionStorage.removeItem("songban_wechat_invite");
      state.wechatInvite = "";
      await adopt(data, data.phone || `微信·${data.name}`);
      return;
    }
    if (form.password.value !== form.password2.value) throw new Error("两次密码不一致。");
    const phone = form.phone.value.trim();
    const body = { phone, code: form.code.value.trim(), password: form.password.value };
    if (state.needProfile) {
      body.name = val(form, "name").trim();
      body.profile = val(form, "profile").trim();
      body.skills = val(form, "skills").trim();
    }
    try {
      const data = await api("POST", "/api/studio/register", body);
      await adopt(data, phone);
    } catch (error) {
      state.token = "";
      if (error.code === "profile_required") {
        state.needProfile = true;
        state.error = "";
        state.note = error.message;
        return;
      }
      throw error;
    }
  },
  async confirmContest(form) {
    const draft = state.contestDraft || {};
    const name = form.name.value.trim();
    const url = form.url.value.trim() || draft.url || "";
    const text = draft.fileText || "";
    if (!name) throw new Error("先填写比赛名称。");
    if (!url && !text) throw new Error("请上传文件，或填写微信公众号网址。");
    state.confirmingContest = true;
    state.error = "";
    state.note = "正在确认比赛并整理关键信息…";
    render();
    try {
      const data = await api("POST", "/api/studio/contests/confirm", {
        name,
        url,
        file_text: text,
        text,
      });
      state.contestId = data.id;
      state.contestDraft = null;
      state.contestPreview = data;
      state.contestAskReply = "";
      saveSession();
      state.me = await api("GET", "/api/studio/me");
      state.note = "已搜到。细则在赛事记忆里，页面只留概要。";
      state.screen = "contest";
    } finally {
      state.confirmingContest = false;
      render();
    }
  },
  async saveContestCard(button) {
    const id = button.dataset.id || state.contestPreview?.id;
    if (!id) throw new Error("先搜到一场比赛。");
    const theme = document.getElementById("theme-status");
    await api("POST", `/api/studio/contests/${id}/card`, { theme_status: theme?.value || "open" });
    state.contestPreview = null;
    state.contestId = id;
    saveSession();
    state.note = "已保存为赛事卡。个人页可以查看全部比赛卡。";
    state.screen = "past";
    await reload();
  },
  async clearContestPreview() {
    state.contestPreview = null;
    state.note = "可以再搜一场。刚才的细则仍留在赛事记忆里。";
  },
  async showContest(button) {
    state.contestId = button.dataset.id;
    saveSession();
    state.screen = "past";
  },
  async askContest(form) {
    const cid = form.contest_id.value || state.contestId;
    if (!cid) throw new Error("先确认一场比赛。");
    const question = form.question.value.trim();
    if (!question) throw new Error("先写下问题。");
    const data = await api("POST", `/api/studio/contests/${cid}/ask`, { question });
    state.contestAskReply = data.reply || "";
    state.contestId = cid;
    state.note = "已根据比赛记忆回答。";
  },
  async useContest(button) {
    state.contestId = button.dataset.id;
    saveSession();
    state.note = "已选中这场。接下来创建队伍。";
    state.screen = "team";
    await reload();
  },
  async publishTask(form) {
    const body = {
      title: form.title.value,
      owner_id: form.owner_id.value,
      priority: form.priority.value,
      talk_to: form.talk_to.value,
      alone: !form.talk_to.value.trim(),
    };
    if (form.due_at.value) body.due_at = toIso(form.due_at.value);
    const data = await api("POST", `/api/studio/squads/${state.squadId}/tasks`, body);
    state.note = data.supervise
      ? `任务已发布。赛规提醒：${data.supervise}`
      : "这一项已发布，没有等表决。队员在我的空间能看到自己的任务。";
    await reload();
  },
  async createSquad(form) {
    const contestId = form.contest_id.value || state.contestId;
    if (!contestId) throw new Error("先从比赛卡池选择一场比赛。");
    const body = { contest_id: contestId, name: form.name.value };
    if (form.project_brief) body.project_brief = form.project_brief.value.trim();
    const data = await api("POST", "/api/studio/squads", body);
    state.contestId = contestId;
    rememberSquad(data.id);
    state.squad = await api("GET", `/api/studio/squads/${data.id}`);
    state.me = await api("GET", "/api/studio/me");
    state.threadKind = "squad";
    state.threadId = data.id;
    state.screen = "messages";
    await loadThread();
    state.note = `团队群「${state.squad.squad.name}」已出现在消息栏。`;
  },
  async joinSquad(form) {
    const data = await api("POST", "/api/studio/squads/join", { code: form.code.value.trim() });
    rememberSquad(data.id);
    state.squad = await api("GET", `/api/studio/squads/${data.id}`);
    state.me = await api("GET", "/api/studio/me");
    state.note = data.notice;
  },
  async addFriend(form) {
    const phone = form.phone.value.trim();
    if (!phone) throw new Error("填写对方的手机号。没有也可以直接发队伍码。");
    const data = await api("POST", "/api/studio/friends", { phone });
    state.note = `已加上 ${data.name}。对方仍可以用队伍码加入。`;
    await reload();
  },
  async renameSquad(form) {
    const data = await api("PATCH", `/api/studio/squads/${state.squadId}`, { name: form.name.value });
    state.note = `队伍名称已改为「${data.name}」。`;
    await reload();
  },
  async copyCode() {
    const code = state.squad.squad.code;
    try {
      await navigator.clipboard.writeText(code);
      state.note = "队伍码已复制。";
    } catch {
      state.note = `请手动选中队伍码：${code}`;
    }
  },
  async saveIntro(form) {
    let role = form.role.value;
    if (role === "其他") role = form.role_custom.value.trim();
    if (!role) throw new Error("选择职位，或自己写一个。");
    const responsibility = form.responsibility.value.trim();
    const data = await api("POST", `/api/studio/squads/${state.squadId}/intro`, { role, responsibility });
    state.note = `已记下：${role} · ${data.responsibility || responsibility}`;
    await reload();
  },
  async saveBrief(form) {
    const data = await api("PATCH", `/api/studio/squads/${state.squadId}`, {
      name: state.squad.squad.name,
      project_brief: form.project_brief.value.trim(),
    });
    state.note = "项目开发内容已保存。";
    state.squad.squad.project_brief = data.project_brief;
    await reload();
  },
  async inviteFriend(form) {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/invite-friend`, { friend_id: form.friend_id.value });
    state.note = data.joined ? `已邀请 ${data.name} 入队。` : `${data.name} 已经在队里。`;
    await reload();
  },
  async refreshOverview() {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/overview`, {});
    state.note = data.source_label ? `综述来自${data.source_label}。` : "已更新团队综述。";
    await reload();
  },
  async syncDeadline(button) {
    const id = button.dataset.id || state.squad?.contest?.id || state.contestId;
    const data = await api("POST", `/api/studio/contests/${id}/sync`);
    state.note = data.notice || (data.changed ? "官方截止时间有更新。" : "官方截止时间没有变化。");
    await reload();
  },
  async toggleRoster() {
    state.showRoster = !state.showRoster;
  },
  async askAgent(form) {
    const message = form.message.value.trim();
    if (!message) throw new Error("先写一句。");
    if (!state.squadId) throw new Error("先加入一支队伍，侧边智能体才能使用你的 API。");
    const data = await api("POST", `/api/studio/squads/${state.squadId}/coach`, { message });
    state.agentLines.push({ me: message, reply: data.reply || "" });
    form.message.value = "";
  },
  async uploadAgent(button) {
    const line = state.agentLines[Number(button.dataset.index)];
    if (!line) throw new Error("这条回答已经不在。");
    if (!state.squadId) throw new Error("先加入队伍，才能放进团队资料库。");
    await api("POST", `/api/studio/squads/${state.squadId}/library`, {
      body: `个人模型回答\n我问：${line.me}\n模型答：${line.reply}`,
    });
    state.note = "已上传到团队资料库。没有自动发到聊天里。";
    await reload();
  },
  async toggleBoardEdit() {
    state.boardEdit = !state.boardEdit;
  },
  async addBranch(form) {
    const title = form.title.value.trim();
    if (!title) throw new Error("先写分支上的文字。");
    await api("POST", `/api/studio/squads/${state.squadId}/tasks`, {
      title,
      owner_id: form.owner_id.value,
      parent_id: form.parent_id.value,
      priority: "must",
      alone: true,
    });
    state.note = "分支已加到这个人的名字后面。";
    await reload();
  },
  async saveBranch(form) {
    await api("PATCH", `/api/studio/squads/${state.squadId}/tasks/${val(form, "id")}`, { title: val(form, "title").trim() });
    state.note = "分支文字已更新。";
    await reload();
  },
  async deleteBranch(button) {
    await api("DELETE", `/api/studio/squads/${state.squadId}/tasks/${button.dataset.id}`);
    state.note = "这条分支和它下面的分支已放进垃圾箱。";
    await reload();
  },
  async confirmTeam() {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/confirm`);
    await reload();
    state.screen = data.show_check ? "success" : "home";
    state.note = "";
  },
  async sendIdea(form) {
    await api("POST", `/api/studio/squads/${state.squadId}/ideas`, { body: form.body.value });
    state.note = "已记入本队候选，并按贴题、队内能力和剩余时间重排。没有读取没贴出来的旧对话。";
    await reload();
  },
  async confirmTopic(button) {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/topic`, { idea_id: button.dataset.id });
    state.note = `题目已确认为「${data.topic}」。接下来每人安装同一份技能。`;
    state.screen = "skill";
    await reload();
  },
  async downloadSkill() {
    const response = await fetch(`/api/studio/squads/${state.squadId}/skill`, { headers: { Authorization: `Bearer ${state.token}` } });
    if (!response.ok) throw new Error("技能还没生成。先确认题目。");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "team-skill.md";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    state.note = "已下载 team-skill.md。队友下载到的是同一份文字。";
  },
  async installSkill(button) {
    const tool = button.dataset.tool;
    await api("POST", `/api/studio/squads/${state.squadId}/skill/install`, { tool });
    state.note = tool === "codex" ? "已标记装进 Codex。本机没有连接 Codex。" : "已标记装进 Workbuddy。本机没有连接 Workbuddy。";
    await reload();
  },
  async sendLibrary(form) {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/library`, { body: form.body.value });
    await reload();
    if (data.vote) {
      state.note = `${data.suggestion} 已发起表决，任务板没改。`;
      state.screen = "vote";
    } else {
      state.note = data.suggestion;
    }
  },
  async cast(button) {
    const data = await api("POST", `/api/studio/votes/${button.dataset.id}/ballots`, { choice: button.dataset.choice });
    state.note = data.status === "recorded"
      ? "全队都表过态了。题目、主干和提交清单仍保持原样。若要改任务，队长再发布一项。"
      : "票已记下。还没收齐。题目和主干没改。";
    await reload();
  },
  async flipTask(button) {
    await api("PATCH", `/api/studio/squads/${state.squadId}/tasks/${button.dataset.id}`, { priority: button.dataset.next });
    state.note = "已改这一项的必须或可选。其他任务没动。";
    await reload();
  },
  async reassign(form) {
    await api("PATCH", `/api/studio/squads/${state.squadId}/tasks/${form.id.value}`, { owner_id: form.owner_id.value });
    state.note = "已改这一项的负责人。没有整份重排。";
    await reload();
  },
  async openThread(button) {
    state.threadKind = button.dataset.kind;
    state.threadId = button.dataset.id;
    state.threadMessages = [];
    if (state.threadKind === "squad") rememberSquad(state.threadId);
    state.screen = "messages";
    render();
    await loadThread();
  },
  async reloadThread() {
    await loadThread();
  },
  async sendMessage(form) {
    const body = form.body.value.trim();
    if (!body) throw new Error("先写一句。");
    if (body.length > 2000) throw new Error("一条消息最多 2000 字。");
    const payload = state.threadKind === "dm"
      ? { kind: "dm", peer_id: state.threadId, body }
      : { kind: "squad", squad_id: state.threadId, body };
    await api("POST", "/api/studio/messages", payload);
    form.body.value = "";
    await loadThread();
  },
  async openFriend(button) {
    state.friendCard = await api("GET", `/api/studio/people/${button.dataset.id}`);
    state.screen = "friends";
  },
  async saveProgress(form) {
    const progress = Number(form.progress.value);
    if (!Number.isInteger(progress)) throw new Error("进度用整数。");
    await api("POST", `/api/studio/squads/${state.squadId}/tasks/${form.id.value}/progress`, { progress, doing: form.doing.value });
    state.note = "进度已更新。头像旁会显示你正在做的事。";
    await reload();
  },
  async uploadShelf(form) {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/shelf`, {
      kind: form.kind.value,
      title: form.title.value,
      body: form.body.value,
      editors: checkedValues(form, "editors"),
    });
    await reload();
    if (data.stored === "vote") {
      state.note = "这会改题目、主干或提交清单，已改为表决，没有放上成果架。";
      state.screen = "vote";
    } else if (data.stored === "library") {
      state.note = data.suggestion;
      state.screen = "talk";
    } else {
      state.note = "已放上成果架，全队可见。";
    }
  },
  async editShelf(form) {
    await api("PATCH", `/api/studio/squads/${state.squadId}/shelf/${form.id.value}`, { body: form.body.value });
    state.note = "成果已改。没有权限的人只能看。";
    await reload();
  },
  async markGithub() {
    await api("POST", "/api/studio/links", { github: true, feishu: state.me.feishu_linked });
    state.note = "已标成本机绑定 GitHub。没有打开 GitHub。";
    await reload();
  },
  async markFeishu() {
    const next = !state.me?.feishu_linked;
    await api("POST", "/api/studio/links", { github: !!state.me?.github_linked, feishu: next });
    state.note = next ? "已标成本机绑定飞书。没有打开飞书。" : "已取消飞书标记。";
    await reload();
  },
  async makeRepo() {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/repo`);
    state.note = `仓库记录是 ${data.url}。没有调用 GitHub。`;
    await reload();
  },
  async leaveBrief(button) {
    const title = button.dataset.title;
    await api("POST", `/api/studio/squads/${state.squadId}/shelf`, { kind: "note", title, body: BRIEFS[title], editors: [] });
    state.note = `${title}简版已放上成果架。正式稿请到飞书写，这里没有打开飞书。`;
    await reload();
  },
  async makeFlow(form) {
    const data = await api("POST", `/api/studio/squads/${state.squadId}/flow`, { request: form.request.value });
    state.flow = data.chart;
    state.note = data.notice;
  },
  async uploadFlow() {
    if (!state.flow) throw new Error("先排成方框。");
    await api("POST", `/api/studio/squads/${state.squadId}/shelf`, { kind: "flow", title: "流程图", body: state.flow, editors: (state.squad.members || []).filter((member) => member.user_id !== state.squad.me.id).map((member) => member.user_id) });
    state.note = "流程图已进成果架。队里其他人可以改。题目和主干没变。";
    state.flow = "";
    await reload();
  },
  async chat(form) {
    const message = form.message.value.trim();
    if (!message) throw new Error("先写一句。");
    const path = COACH.has(state.screen) ? "coach" : "direction";
    const data = await api("POST", `/api/studio/squads/${state.squadId}/${path}`, { message });
    state.chats[state.screen] = state.chats[state.screen] || [];
    state.chats[state.screen].push({ me: message, reply: data.reply });
    form.message.value = "";
  },
  async saveModel(form) {
    const data = await api("POST", "/api/studio/me/model", {
      base_url: form.base_url.value.trim(),
      api_key: form.api_key.value,
      model_id: form.model_id.value.trim(),
    });
    form.api_key.value = "";
    state.note = data.notice;
    await reload();
  },
  async shareChat() {
    const lines = state.chats[state.screen] || [];
    const last = lines[lines.length - 1];
    if (!last) throw new Error("先问一句，再交给团队。");
    const data = await api("POST", `/api/studio/squads/${state.squadId}/library`, {
      body: `个人模型讨论\n我问：${last.me}\n模型答：${last.reply}`,
    });
    state.note = `${data.suggestion || "已交给团队。"}题目和任务没有被改掉。`;
  },
  async finishContest() {
    await api("POST", `/api/studio/squads/${state.squadId}/finish`);
    state.note = "已写入每人的成长记录。下次用手机号和密码进入，不会重问画像。";
    await reload();
  },
};

document.addEventListener("click", async (event) => {
  if (isTypingTarget(event.target)) return;
  if (state.menuOpen && !event.target.closest("#rail")) {
    state.menuOpen = false;
    renderRail();
  }
  const toggle = event.target.closest("[data-act='toggleMenu']");
  if (toggle) {
    event.preventDefault();
    actions.toggleMenu();
    return;
  }
  const destination = event.target.closest("[data-go]");
  if (destination) {
    event.preventDefault();
    await go(destination.dataset.go);
    return;
  }
  const button = event.target.closest("button[data-act]");
  if (!button || button.type === "submit") return;
  event.preventDefault();
  state.error = "";
  try { await actions[button.dataset.act](button); }
  catch (error) { state.error = error.message; }
  render();
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.dataset.act) return;
  event.preventDefault();
  state.error = "";
  try { await actions[form.dataset.act](form); }
  catch (error) { state.error = error.message; }
  render();
});

async function loadConnect() {
  try {
    const data = await api("GET", "/api/studio/connect");
    state.smsReady = !!(data.sms && data.sms.ready);
    state.smsNote = (data.sms && data.sms.notice) || "";
    state.teamModelName = (data.team_model && data.team_model.ready && data.team_model.name) || "";
  } catch {
    state.smsReady = false;
    state.smsNote = "";
  }
}

async function boot() {
  await loadConnect();
  const params = new URLSearchParams(location.search);
  const inviteParam = params.get("wechat_invite");
  if (inviteParam) {
    state.wechatInvite = inviteParam;
    sessionStorage.setItem("songban_wechat_invite", inviteParam);
  }
  const ticket = params.get("wechat_ticket");
  if (ticket) {
    history.replaceState({}, "", "/");
    state.wechatTicket = ticket;
    state.token = "";
    try {
      const invite = state.wechatInvite || sessionStorage.getItem("songban_wechat_invite") || "";
      const data = await api("POST", "/api/studio/wechat/finish", { ticket, invite });
      sessionStorage.removeItem("songban_wechat_invite");
      state.wechatInvite = "";
      await adopt(data, data.phone || `微信·${data.name}`);
    } catch (error) {
      state.token = "";
      if (error.code === "profile_required") {
        state.needProfile = true;
        state.note = error.message;
      } else {
        state.wechatTicket = "";
        state.error = error.message;
      }
    }
    render();
    return;
  }
  if (!state.token) { render(); return; }
  try {
    state.me = await api("GET", "/api/studio/me");
    if (!state.squadId && state.me.squads[0]) state.squadId = state.me.squads[0].id;
    if (state.squadId) {
      try { state.squad = await api("GET", `/api/studio/squads/${state.squadId}`); }
      catch { state.squadId = ""; state.squad = null; }
    }
    if (!state.contestId && state.me.contests[0]) state.contestId = state.me.contests[0].id;
    saveSession();
    state.screen = "messages";
  } catch (error) {
    state.token = "";
    state.error = error.message;
    state.screen = "login";
    saveSession();
  }
  render();
}

function installFlowDrag() {
  if (window.__songbanFlowDrag) return;
  window.__songbanFlowDrag = true;
  document.addEventListener("dragstart", (event) => {
    const chip = event.target.closest("[data-agent-index]");
    if (chip) {
      const line = state.agentLines[Number(chip.dataset.agentIndex)];
      if (line) event.dataTransfer.setData("text/plain", line.reply || "");
      return;
    }
    const branch = event.target.closest("[data-branch-id]");
    if (branch && state.boardEdit) {
      event.dataTransfer.setData("application/x-songban-branch", branch.dataset.branchId);
      event.dataTransfer.effectAllowed = "move";
    }
  });
  document.addEventListener("dragover", (event) => {
    if (event.target.closest("#task-trash") || event.target.closest(".wx-compose")) event.preventDefault();
  });
  document.addEventListener("drop", async (event) => {
    const trash = event.target.closest("#task-trash");
    if (trash) {
      event.preventDefault();
      const id = event.dataTransfer.getData("application/x-songban-branch");
      if (!id || !state.squadId) return;
      try {
        await api("DELETE", `/api/studio/squads/${state.squadId}/tasks/${id}`);
        state.note = "这条分支已拖进垃圾箱。";
        state.error = "";
        await reload();
      } catch (error) {
        state.error = error.message;
      }
      render();
      return;
    }
    const compose = event.target.closest(".wx-compose");
    if (!compose) return;
    const text = event.dataTransfer.getData("text/plain");
    if (!text) return;
    event.preventDefault();
    const input = document.getElementById("msg-body");
    if (input) input.value = text;
  });
}

installContestDnD();
installFlowDrag();
boot();
