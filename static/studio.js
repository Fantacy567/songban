const SAMPLE = "主办方要求：可演示作品、宣传片、PPT、分工说明，以及 GitHub 仓库链接。";
const NAV = [
  ["signup", "首次注册"],
  ["contest", "选择比赛"],
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
  ["teamspace", "团队空间"],
  ["mine", "我的空间"],
  ["home", "首页"],
  ["talk", "讨论"],
  ["topics", "选题空间"],
  ["skill", "安装同一技能"],
  ["vote", "团队表决"],
  ["docs", "需求与流程图"],
  ["team", "组队"],
  ["contest", "选择比赛"],
  ["log", "更改记录"],
  ["growth", "赛后成长"],
];
const CHAT = new Set(["team", "mine", "teamspace", "topics", "skill", "talk", "docs", "vote", "captain", "growth", "profile", "memory"]);
const COACH = new Set(["mine", "docs", "growth", "profile", "memory"]);
const NEED_SQUAD = new Set(["success", "home", "mine", "teamspace", "topics", "skill", "talk", "docs", "vote", "captain", "log", "growth"]);
const NEED_CONFIRMED = new Set(["success", "home", "mine", "teamspace", "topics", "skill", "talk", "docs", "vote", "captain", "growth"]);
const BRIEFS = {
  需求文档: "目标：做出截止前能演示的一条路径。\n谁用：本队。\n主路径：选比赛、组队、选题、安装同一技能、发布任务。\n这场不做：主办方系统和给其他队伍排名。",
  业务流程图: "注册 → 选比赛 → 组队 → 选题 → 安装同一技能 → 发布任务 → 提交清单上的成果",
  页面原型: "首页放比赛名、倒计时和提交清单。我的空间只放我的截止时间。团队空间放任务树、成果架和仓库记录。",
};

const state = {
  screen: "signup",
  token: localStorage.getItem("studio-token") || "",
  squadId: localStorage.getItem("studio-squad") || "",
  contestId: localStorage.getItem("studio-contest") || "",
  accounts: JSON.parse(localStorage.getItem("studio-accounts") || "{}"),
  me: null,
  squad: null,
  error: "",
  note: "",
  needProfile: false,
  issuedCode: "",
  wechatNote: "",
  menuOpen: false,
  chats: {},
  contestDraft: null,
  flow: "",
  tick: null,
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
  localStorage.setItem("studio-accounts", JSON.stringify(state.accounts));
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

function canOpen(id) {
  if (id === "signup") return true;
  if (!state.token) return "先用手机号进入。";
  if (id === "contest" || id === "team") return true;
  if (NEED_SQUAD.has(id) && !state.squad) return "先创建队伍，或凭队伍码加入。";
  if (NEED_CONFIRMED.has(id) && !state.squad.squad.confirmed) return "先让每人贴介绍并选角色，再由队长确认。";
  if ((id === "skill" || id === "docs") && !state.squad.squad.topic) return "先在选题空间确认题目。";
  if (id === "captain" && !state.squad.me.captain) return "队长规划只有队长能打开。你的任务在我的空间，全队任务在团队空间。";
  return true;
}

function nextStep() {
  if (!state.token) return "用手机号进入。第一次才填写画像和技能。";
  if (!state.squad && !(state.me?.contests || []).length) return "下一步：导入一场比赛。粘贴主办方正文，不要粘贴网址。";
  if (!state.squad) return "下一步：创建队伍，或让队友用自己的手机号进入后填写队伍码。";
  if (!state.squad.squad.confirmed) return "下一步：每人贴一段介绍并选角色。人齐了，队长再确认。确认后才会出现对勾。";
  if (!state.squad.squad.topic) return "下一步：到选题空间送入想法。队长确认一条，全队看见同一题。";
  if (state.squad.members.some((member) => !member.skill_installed)) return "下一步：每人下载并安装同一份技能。文件内容全队相同。";
  if (!state.squad.tasks.length) return state.squad.me.captain ? "下一步：在队长规划里发布任务。发布不用等表决。" : "下一步：等队长发布任务。会改题目、主干或提交清单的想法，先到团队表决。";
  if (!state.squad.squad.finished) return "任务已经发布。做完后由队长在赛后成长里记下这场。";
  return "这场已记入成长。下次用同一个手机号进入，不必重填画像。";
}

function page(inner) {
  const hint = state.screen === "signup" || state.screen === "success" ? "" : `<p class="hint">${esc(nextStep())}</p>`;
  const main = `<div>${hint}${inner}</div>`;
  if (!CHAT.has(state.screen)) return main;
  return `<div class="work">${main}${chatBox()}</div>`;
}

function chatBox() {
  const coach = COACH.has(state.screen);
  const lines = state.chats[state.screen] || [];
  const bubbles = lines.map((line) => `<div class="bubble me">${esc(line.me)}</div><div class="bubble">${esc(line.reply)}</div>`).join("");
  const idle = coach
    ? "可以问 PPT 要写多长，或用一句话让它排流程图。旧对话要自己贴过来。"
    : "可以问「我们在做什么」。它只按已确认的题目、主干和提交清单回答。";
  return `<aside class="chat">
    <h3>${coach ? "私人教练" : "团队方向"}</h3>
    <p class="muted">${coach ? "离线教练 · 非大模型。不读取旧对话，也不调用你的 API。" : "离线规则 · 非大模型。本机不调用 DeepSeek。"}</p>
    ${bubbles || `<div class="bubble">${esc(idle)}</div>`}
    <form data-act="chat" class="composer">
      <input name="message" aria-label="${coach ? "问私人教练" : "问团队方向"}" ${state.squad ? "" : "disabled"}>
      <button class="btn" type="submit" ${state.squad ? "" : "disabled"}>发送</button>
    </form>
  </aside>`;
}

function banners() {
  return `${state.error ? `<p class="error" role="alert">${esc(state.error)}</p>` : ""}${state.note ? `<p class="ok" role="status">${esc(state.note)}</p>` : ""}`;
}

function switcher() {
  const phones = Object.keys(state.accounts);
  if (!phones.length) return "";
  const options = phones.map((phone) => `<option value="${esc(phone)}" ${state.accounts[phone].token === state.token ? "selected" : ""}>${esc(state.accounts[phone].name)} · ${esc(phone)}</option>`).join("");
  return `<form data-act="switchAccount" class="switch"><label for="account">换一个人</label><select id="account" name="phone">${options}</select><button class="btn ghost" type="submit">切换</button></form>`;
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

function viewSignup() {
  return `<div class="reg-wrap"><h2>注册</h2>
    <p class="muted">先填写手机号，获取 6 位验证码，再把验证码填进去。验证码正确才会建立账号。</p>
    <form id="reg-form" data-act="enter" class="card">
      <label for="reg-phone">手机号</label>
      <input id="reg-phone" name="phone" type="tel" autocomplete="tel" inputmode="numeric" placeholder="6 到 20 位数字">
      <button class="btn ghost" type="button" data-act="requestCode">获取验证码</button>
      <p id="reg-code-note" class="muted" hidden>没有短信服务。验证码只显示在这里，没有发送，也没有花钱。</p>
      <p id="reg-issued" class="code" hidden></p>
      <label for="reg-code">验证码</label>
      <input id="reg-code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6 位数字">
      <div id="reg-profile" hidden>
        <label for="reg-name">名字</label>
        <input id="reg-name" name="name" maxlength="40" autocomplete="name">
        <label for="reg-about">我是谁、做过什么</label>
        <textarea id="reg-about" name="profile" placeholder="例如：高二，产品设计。会整理讨论和演示。"></textarea>
        <label for="reg-skills">目前做得到的事</label>
        <input id="reg-skills" name="skills" placeholder="例如：需求、流程图、路演">
        <p class="muted">只在第一次问。验证码还没通过时，填了也不会进入。</p>
      </div>
      <button class="btn" type="submit">验证并进入</button>
    </form>
    <div class="card">
      <button class="btn ghost" type="button" data-act="wechat">微信注册还缺开放平台网站应用和正式域名</button>
      <p id="reg-wechat" class="muted" hidden></p>
    </div>
    <p id="reg-status" hidden></p></div>`;
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
    </form>`);
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
      <p class="kicker">账号</p>
      <p>${esc(me.name || "")}</p>
      <p class="muted">手机号 ${esc(me.phone || "")}</p>
      <p class="muted">验证码在注册页核对。这台电脑没有短信服务，验证码不会发到手机上。</p>
      <div class="row">
        <button class="btn" type="button" data-go="profile">编辑资料</button>
        <button class="btn ghost" type="button" data-go="memory">个人记忆与能力记录</button>
      </div>
    </div>
    <div class="card">
      <p class="kicker">微信</p>
      <p>还没有接通。需要微信开放平台的网站应用 AppID，以及可公网回调的正式域名。127.0.0.1 完不成微信登录，这里不会编一个头像把人放进去。</p>
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

function viewContest() {
  const draft = state.contestDraft || {};
  const cards = (state.me?.contests || []).map((contest) => `<div class="person">
      <strong>${esc(contest.name)}</strong>
      <p class="muted">结束：${esc(when(contest.deadline))}</p>
      <p class="kicker">抽出的提交清单</p>
      ${submissionsOf(contest.submissions)}
      <button class="btn" type="button" data-act="useContest" data-id="${esc(contest.id)}">用这场组队</button>
    </div>`).join("");
  return `<h2>选择比赛</h2>
    <p class="muted">导入公开赛讯。不排其他队伍，不接现场大屏。本机不抓取网页。</p>
    <form data-act="saveContest" class="card">
      <label for="cname">比赛名称</label>
      <input id="cname" name="name" value="${esc(draft.name || "")}" required>
      <label for="cdeadline">结束时间</label>
      <input id="cdeadline" name="deadline" type="datetime-local" value="${esc(draft.deadline || "2026-10-28T18:00")}" required>
      <label for="csource">主办方公开材料正文</label>
      <textarea id="csource" name="source" required placeholder="把要求提交什么的那段粘在这里">${esc(draft.source || "")}</textarea>
      <div class="row">
        <button class="btn ghost" type="button" data-act="fillSample">填入示例正文</button>
        <button class="btn" type="submit">抽出提交清单</button>
      </div>
    </form>
    ${cards ? `<div class="card"><p class="kicker">已经导入的比赛</p>${cards}</div>` : ""}`;
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
    const contests = state.me?.contests || [];
    const options = contests.map((contest) => `<option value="${esc(contest.id)}" ${contest.id === state.contestId ? "selected" : ""}>${esc(contest.name)}</option>`).join("");
    return page(`<h2>组队</h2>
      <div class="split">
        <form data-act="createSquad" class="card">
          <p class="kicker">我来建队，创建的人是队长</p>
          <label for="squad-contest">用哪场比赛</label>
          <select id="squad-contest" name="contest_id" ${options ? "" : "disabled"}>${options || "<option value=\"\">还没有比赛</option>"}</select>
          <label for="squad-name">队伍名称</label>
          <input id="squad-name" name="name" maxlength="40" placeholder="例如：回响小队" required>
          <button class="btn" type="submit" ${options ? "" : "disabled"}>创建队伍</button>
        </form>
        <form data-act="joinSquad" class="card">
          <p class="kicker">我有队伍码</p>
          <label for="join-code">队伍码</label>
          <input id="join-code" name="code" autocomplete="off" required>
          <button class="btn" type="submit">加入</button>
          <p class="muted">不必先成为好友。</p>
        </form>
      </div>
      <form data-act="addFriend" class="card">
        <p class="kicker">可选：加好友</p>
        <label for="friend-phone">对方注册用的手机号</label>
        <input id="friend-phone" name="phone" inputmode="numeric">
        <button class="btn ghost" type="submit">加为好友</button>
        <p class="muted">好友不是加入的门槛。对方还没注册时，把队伍码发给对方即可。</p>
      </form>`);
  }
  const squad = state.squad.squad;
  const ready = state.squad.members.length >= 2 && state.squad.members.every((member) => member.role);
  const people = state.squad.members.map((member) => `<div class="person"><strong>${esc(member.name)}</strong> ${member.captain ? "<span class=\"tag\">队长</span>" : ""} <span class="tag">${esc(member.role || "还没选角色")}</span><p class="muted">${esc(member.extract || "还没贴介绍")}</p></div>`).join("");
  const plan = planRows().map((line) => `<li>${esc(line.name)}：${esc(line.work)}（${line.priority === "must" ? "必须" : "可选"}）</li>`).join("");
  return page(`<h2>组队</h2>
    <div class="card">
      <form data-act="renameSquad" class="row">
        <label for="rename" class="muted">队伍名称</label>
        <input id="rename" name="name" value="${esc(squad.name)}" ${state.squad.me.captain ? "" : "readonly"}>
        ${state.squad.me.captain ? `<button class="btn ghost" type="submit">改名称</button>` : ""}
      </form>
      <p class="kicker">队伍码 · 发给还不是好友的人</p>
      <p class="code">${esc(squad.code)}</p>
      <button class="btn ghost" type="button" data-act="copyCode">复制队伍码</button>
      <p class="muted">队友先用自己的手机号进入，再在右上角切换过来，填写这个码。不要用队长的号再注册一次。</p>
    </div>
    <div class="card">
      <p class="kicker">每个人</p>
      ${people}
      ${squad.confirmed ? "" : `<form data-act="saveIntro">
        <label for="role">我的角色</label>
        <select id="role" name="role">
          <option>产品</option><option>前端</option><option>后端</option><option>设计</option><option>路演</option>
        </select>
        <label for="intro">长自我介绍</label>
        <textarea id="intro" name="intro" required placeholder="贴你实际会做的事。不要贴密钥或整段旧对话，除非你打算让队里用到其中一段。"></textarea>
        <button class="btn" type="submit">抽出我能做的部分</button>
      </form>`}
      <p><strong>${squad.confirmed ? "已确认的分工草案" : "确认前的预览"}</strong></p>
      <ul>${plan}</ul>
      ${squad.confirmed ? `<p class="muted">草案已定。任务要等队长在规划里逐项发布，这里不会整份重排。</p>` : `<button class="btn" type="button" data-act="confirmTeam" ${state.squad.me.captain && ready ? "" : "disabled"}>${state.squad.me.captain ? "确认这版分工" : "等队长确认"}</button>
        <p class="muted">${ready ? "确认后出现对勾，并进入选题。" : "至少两人，且每人都贴了介绍并选了角色。"}</p>`}
    </div>
      ${squad.confirmed ? "" : `<form data-act="joinSquad" class="card">
      <p class="kicker">手里有另一支队伍的码</p>
      <label for="join-code">队伍码</label>
      <input id="join-code" name="code" autocomplete="off">
      <button class="btn ghost" type="submit">改加入这支队伍</button>
      <p class="muted">建错队伍时用。加入后，这个页面换到队长那一支。</p>
    </form>
    <form data-act="addFriend" class="card">
      <label for="friend-phone">可选：好友的手机号</label>
      <input id="friend-phone" name="phone" inputmode="numeric">
      <button class="btn ghost" type="submit">加为好友</button>
    </form>`}`);
}

function viewSuccess() {
  return `<div class="card pay"><div>
    <div class="tick" aria-hidden="true">✓</div>
    <h2>组队成功</h2>
    <p class="muted">对勾先出现，然后是阶段条。第一阶段是选题确认。</p>
    <ol class="stages"><li class="now">选题确认</li><li>之后的阶段还没定名</li></ol>
    <button class="btn" type="button" data-go="home">进入首页</button>
  </div></div>`;
}

function viewHome() {
  const contest = state.squad.contest;
  return `<p class="hint">${esc(nextStep())}</p>
    <p class="kicker">已导入的比赛</p>
    <p class="hero-name">${esc(contest.name)}</p>
    <p class="kicker">距结束 · ${esc(stageName())} · 用导入的结束时间，不是现场大屏</p>
    <p class="count" id="count">--:--:--</p>
    <p class="muted">结束时间：${esc(when(contest.deadline))}。按这台电脑的本地时间倒计时。</p>
    <div class="card"><p class="kicker">本场必须完成</p>${submissionsOf(contest.submissions)}<p class="muted">与选择比赛里抽出的是同一份清单。</p></div>
    <div class="split">
      <button class="card btn ghost" type="button" data-go="teamspace" style="text-align:left"><strong>团队空间</strong><br><span class="muted">任务、成果、仓库、PPT</span></button>
      <button class="card btn ghost" type="button" data-go="mine" style="text-align:left"><strong>我的空间</strong><br><span class="muted">我这场要交的东西</span></button>
    </div>`;
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
  const squad = state.squad;
  const must = squad.tasks.filter((task) => task.priority === "must");
  const optional = squad.tasks.filter((task) => task.priority !== "must");
  const taskLine = (task) => `<li>${esc(nameOf(task.owner_id))} · ${esc(task.title)} <div class="bar"><span style="width:${task.progress}%"></span></div></li>`;
  const people = squad.members.map((member) => `<div class="who"><div class="avatar">${esc(member.avatar)}</div><div>${esc(member.name)} · ${esc(member.role || "未选角色")}<br><span class="muted">${esc(member.doing || "还没说正在做什么")}</span></div></div>`).join("");
  const shelf = squad.shelf.map((item) => {
    const editable = item.author_id === squad.me.id || item.editors.includes(squad.me.id);
    return `<div class="item"><strong>${esc(item.title)}</strong><br><span class="muted">${esc(item.kind)} · ${esc(nameOf(item.author_id))}</span><pre>${esc(item.body)}</pre>${editable ? `<form data-act="editShelf"><input type="hidden" name="id" value="${esc(item.id)}"><textarea name="body">${esc(item.body)}</textarea><button class="btn ghost" type="submit">保存修改</button></form>` : `<p class="muted">全队可见。${item.editors.length ? `可编辑：${item.editors.map(nameOf).join("、")}` : "还没有额外授权。"}</p>`}</div>`;
  }).join("");
  return page(`<h2>团队空间</h2>
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
  const growth = state.me?.growth || state.squad.me.growth;
  return page(`<h2>赛后成长</h2>
    <div class="card">
      <p class="kicker">教练已经记住的</p>
      <pre>${esc(growth || "这场还没结束。结束后会按角色和完成的任务写下一句，不再问画像。")}</pre>
      ${state.squad.me.captain ? `<button class="btn" type="button" data-act="finishContest" ${state.squad.squad.finished ? "disabled" : ""}>${state.squad.squad.finished ? "这场已经记过" : "结束这场并写入成长"}</button>` : `<p class="muted">由队长结束这场。你的画像不会重问。</p>`}
    </div>`);
}

const views = {
  signup: viewSignup,
  contest: viewContest,
  team: viewTeam,
  success: viewSuccess,
  home: viewHome,
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
  const status = document.getElementById("reg-status");
  if (!status) return;
  const text = state.error || state.note || "";
  status.hidden = !text;
  status.className = state.error ? "error" : "ok";
  status.textContent = text;
  const note = document.getElementById("reg-code-note");
  const issued = document.getElementById("reg-issued");
  if (note && issued) {
    const show = !!state.issuedCode;
    note.hidden = !show;
    issued.hidden = !show;
    if (show) issued.textContent = state.issuedCode;
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
  if (!document.getElementById("reg-phone")) main.innerHTML = viewSignup();
  paintSignupStatus();
}

const RAIL_GROUPS = [
  ["空间", ["teamspace", "mine", "home"]],
  ["比赛中", ["talk", "topics", "skill", "vote", "docs", "captain"]],
  ["准备", ["team", "contest"]],
  ["记录", ["log", "growth"]],
];

function sideGroups() {
  const labels = Object.fromEntries([...SIDE, ["captain", "队长规划"]]);
  return RAIL_GROUPS.map(([title, ids]) => {
    const items = ids.filter((id) => id !== "captain" || state.squad?.me?.captain).map((id) => [id, labels[id]]);
    return [title, items];
  });
}

function menuHtml() {
  return `<div class="popover" id="me-menu" role="menu">
    <button type="button" data-go="settings">设置</button>
    <button type="button" data-go="profile">编辑资料</button>
    <button type="button" data-go="memory">个人记忆与能力记录</button>
    <button type="button" data-act="logout">退出登录</button>
    <a href="/classic">旧工作台</a>
    ${switcher()}
  </div>`;
}

function renderRail() {
  const rail = document.getElementById("rail");
  if (!rail) return;
  const buttons = sideGroups().map(([title, items]) => `<p class="rail-label">${title}</p>${items.map(([id, label]) => `<button type="button" data-go="${id}" class="${state.screen === id ? "on" : ""}">${label}</button>`).join("")}`).join("");
  const initial = (state.me?.name || "我").slice(0, 1);
  const squadName = state.squad?.squad?.name ? `<p class="rail-squad">${esc(state.squad.squad.name)}</p>` : "";
  rail.innerHTML = `<div class="brand">松伴${squadName}</div><div class="rail-scroll">${buttons}</div><div class="dock">${state.menuOpen ? menuHtml() : ""}<button type="button" class="me-btn" data-act="toggleMenu" aria-haspopup="menu" aria-expanded="${state.menuOpen ? "true" : "false"}"><span class="avatar">${esc(initial)}</span><span class="me-meta">${esc(state.me?.name || "")}<br><span class="muted">${esc(state.me?.phone || "")}</span></span></button></div>`;
}

function render() {
  const app = document.getElementById("app");
  if (!state.token) {
    state.screen = "signup";
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
  const view = views[state.screen] || viewHome;
  document.getElementById("main").innerHTML = banners() + view();
  armCountdown();
}

function armCountdown() {
  clearInterval(state.tick);
  state.tick = null;
  if (state.screen !== "home" || !state.squad) return;
  const end = new Date(state.squad.contest.deadline);
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
  if (!state.token) {
    state.screen = "signup";
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
    try { await reload(); } catch (error) { state.error = error.message; }
  }
  render();
}

async function adopt(data, phone) {
  state.token = data.token;
  state.accounts[phone] = { token: data.token, name: data.name };
  state.needProfile = false;
  state.issuedCode = "";
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
  if (state.squad?.squad.confirmed) state.screen = "home";
  else if (state.squad) state.screen = "team";
  else state.screen = "contest";
}

const actions = {
  async requestCode(button) {
    const form = button.closest("form");
    const phone = form.phone.value.trim();
    const data = await api("POST", "/api/studio/codes", { phone });
    state.issuedCode = data.code;
    state.note = data.notice;
    state.error = "";
  },
  wechat() {
    state.wechatNote = "还缺微信开放平台的网站应用 AppID，以及可公网回调的正式域名。127.0.0.1 完不成微信登录。没有进入，也没有头像。";
    state.error = "";
    state.token = "";
  },
  toggleMenu() {
    state.menuOpen = !state.menuOpen;
    renderRail();
  },
  logout() {
    if (state.me?.phone) delete state.accounts[state.me.phone];
    state.token = "";
    state.me = null;
    state.squad = null;
    state.squadId = "";
    state.menuOpen = false;
    state.screen = "signup";
    saveSession();
  },
  async saveProfile(form) {
    const data = await api("PATCH", "/api/studio/me", { name: val(form, "name").trim(), profile: val(form, "profile").trim(), skills: val(form, "skills").trim() });
    state.note = "资料已保存。";
    if (state.accounts[state.me.phone]) state.accounts[state.me.phone].name = data.name;
    saveSession();
    await reload();
  },
  async addMemory(form) {
    const data = await api("POST", "/api/studio/memory", { text: form.text.value });
    state.note = "已记入个人记忆。没有读取旧对话。";
    if (state.me) state.me.growth = data.growth;
    await reload();
  },
  async enter(form) {
    const phone = form.phone.value.trim();
    const body = { phone, code: form.code.value.trim() };
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
  async switchAccount(form) {
    const phone = form.phone.value;
    const saved = state.accounts[phone];
    if (!saved) throw new Error("还没有这个人。");
    state.token = saved.token;
    saveSession();
    try {
      state.me = await api("GET", "/api/studio/me");
    } catch (error) {
      if (error.status === 401) delete state.accounts[phone];
      state.token = "";
      saveSession();
      throw new Error("这个登录已失效。用手机号再进入一次。");
    }
    state.squad = null;
    state.squadId = state.me.squads[0]?.id || "";
    if (state.squadId) state.squad = await api("GET", `/api/studio/squads/${state.squadId}`);
    state.contestId = state.me.contests[0]?.id || "";
    saveSession();
    state.note = `现在是 ${state.me.name}。没有重新注册。`;
    state.screen = state.squad?.squad.confirmed ? "home" : state.squad ? "team" : "contest";
  },
  fillSample() {
    state.contestDraft = { name: "回响 · 48H 青年创造营", deadline: "2026-10-28T18:00", source: SAMPLE };
    state.note = "已填入示例正文。抽出之后，清单会出现在下面的比赛卡片里。";
  },
  async saveContest(form) {
    const data = await api("POST", "/api/studio/contests", {
      name: form.name.value,
      deadline: toIso(form.deadline.value),
      source_text: form.source.value,
    });
    state.contestId = data.id;
    state.contestDraft = null;
    saveSession();
    state.me = await api("GET", "/api/studio/me");
    const found = data.submissions.length ? data.submissions.join("、") : "没有提交项";
    state.note = `已抽出：${found}。${data.notice}`;
  },
  async useContest(button) {
    state.contestId = button.dataset.id;
    saveSession();
    state.note = "已选中这场。接下来创建队伍。";
    state.screen = "team";
    await reload();
  },
  async createSquad(form) {
    const contestId = form.contest_id.value || state.contestId;
    if (!contestId) throw new Error("先导入一场比赛。");
    const data = await api("POST", "/api/studio/squads", { contest_id: contestId, name: form.name.value });
    state.contestId = contestId;
    rememberSquad(data.id);
    state.squad = await api("GET", `/api/studio/squads/${data.id}`);
    state.me = await api("GET", "/api/studio/me");
    state.note = `队伍码 ${data.code}。把码发给队友。队友用自己的手机号进入后再加入。`;
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
    const data = await api("POST", `/api/studio/squads/${state.squadId}/intro`, { role: form.role.value, intro: form.intro.value });
    state.note = `抽出：${data.extract}。这还不是任务，等队长确认草案后再逐项发布。`;
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
  async publishTask(form) {
    const body = {
      title: form.title.value,
      owner_id: form.owner_id.value,
      priority: form.priority.value,
      talk_to: form.talk_to.value,
      alone: !form.talk_to.value.trim(),
    };
    if (form.due_at.value) body.due_at = toIso(form.due_at.value);
    await api("POST", `/api/studio/squads/${state.squadId}/tasks`, body);
    state.note = "这一项已发布，没有等表决。队员在我的空间能看到自己的任务。";
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
  },
  async finishContest() {
    await api("POST", `/api/studio/squads/${state.squadId}/finish`);
    state.note = "已写入每人的成长记录。下次用同一个手机号进入，不会重问画像。";
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

async function boot() {
  if (!state.token) { render(); return; }
  try {
    state.me = await api("GET", "/api/studio/me");
    const known = Object.values(state.accounts).some((item) => item.token === state.token);
    if (!known) state.accounts[state.me.phone] = { token: state.token, name: state.me.name };
    if (!state.squadId && state.me.squads[0]) state.squadId = state.me.squads[0].id;
    if (state.squadId) {
      try { state.squad = await api("GET", `/api/studio/squads/${state.squadId}`); }
      catch { state.squadId = ""; state.squad = null; }
    }
    if (!state.contestId && state.me.contests[0]) state.contestId = state.me.contests[0].id;
    saveSession();
    if (state.squad?.squad.confirmed) state.screen = "home";
    else if (state.squad) state.screen = "team";
    else state.screen = "contest";
  } catch (error) {
    state.token = "";
    state.error = error.message;
    state.screen = "signup";
    saveSession();
  }
  render();
}

boot();
