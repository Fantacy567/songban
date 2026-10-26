"""Local stand-in for the locked team flow. No SMS, OAuth, or paid model calls."""
import json
import re
import secrets
from datetime import datetime

from fastapi import Header
from fastapi.responses import PlainTextResponse

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
 id TEXT PRIMARY KEY, phone TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 profile TEXT NOT NULL DEFAULT '', skills TEXT NOT NULL DEFAULT '',
 github_linked INTEGER NOT NULL DEFAULT 0, feishu_linked INTEGER NOT NULL DEFAULT 0,
 token_hash TEXT NOT NULL UNIQUE, growth TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS friendships (
 user_id TEXT NOT NULL, friend_id TEXT NOT NULL, PRIMARY KEY (user_id, friend_id)
);
CREATE TABLE IF NOT EXISTS contests (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL, deadline TEXT NOT NULL,
 source_text TEXT NOT NULL, submissions TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS squads (
 id TEXT PRIMARY KEY, contest_id TEXT NOT NULL, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
 captain_id TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0, topic TEXT NOT NULL DEFAULT '',
 topic_core TEXT NOT NULL DEFAULT '', trunk TEXT NOT NULL DEFAULT '', skill_body TEXT NOT NULL DEFAULT '',
 draft TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT 'forming', finished INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS squad_members (
 squad_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
 intro TEXT NOT NULL DEFAULT '', extract TEXT NOT NULL DEFAULT '', doing TEXT NOT NULL DEFAULT '',
 skill_installed INTEGER NOT NULL DEFAULT 0, tool TEXT NOT NULL DEFAULT '',
 PRIMARY KEY (squad_id, user_id)
);
CREATE TABLE IF NOT EXISTS ideas (
 id TEXT PRIMARY KEY, squad_id TEXT NOT NULL, author_id TEXT NOT NULL, body TEXT NOT NULL,
 core TEXT NOT NULL, fit INTEGER NOT NULL, ability INTEGER NOT NULL, finishable INTEGER NOT NULL,
 score INTEGER NOT NULL, problems TEXT NOT NULL, realistic TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS library_notes (
 id TEXT PRIMARY KEY, squad_id TEXT NOT NULL, author_id TEXT NOT NULL, body TEXT NOT NULL,
 suggestion TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS votes (
 id TEXT PRIMARY KEY, squad_id TEXT NOT NULL, author_id TEXT NOT NULL, body TEXT NOT NULL,
 kind TEXT NOT NULL, clarify TEXT NOT NULL, frame TEXT NOT NULL, parts TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ballots (
 vote_id TEXT NOT NULL, user_id TEXT NOT NULL, choice TEXT NOT NULL,
 PRIMARY KEY (vote_id, user_id)
);
CREATE TABLE IF NOT EXISTS squad_tasks (
 id TEXT PRIMARY KEY, squad_id TEXT NOT NULL, title TEXT NOT NULL, owner_id TEXT NOT NULL,
 priority TEXT NOT NULL, due_at TEXT NOT NULL, talk_to TEXT NOT NULL DEFAULT '',
 alone INTEGER NOT NULL DEFAULT 1, progress INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shelf (
 id TEXT PRIMARY KEY, squad_id TEXT NOT NULL, author_id TEXT NOT NULL, kind TEXT NOT NULL,
 title TEXT NOT NULL, body TEXT NOT NULL, editors TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS squad_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, squad_id TEXT NOT NULL, actor_id TEXT,
 detail TEXT NOT NULL, created_at TEXT NOT NULL
);
"""

SUBMISSION_RULES = (
    ("宣传片", ("宣传片", "宣传视频", "promo")),
    ("PPT", ("ppt", "幻灯", "路演胶片")),
    ("分工说明", ("分工说明", "团队分工", "成员分工", "分工写")),
    ("GitHub 仓库", ("github", "代码仓库", "仓库链接")),
    ("可演示作品", ("可演示", "演示作品", "演示视频", "现场演示", "demo")),
    ("项目说明", ("项目说明", "说明文档")),
)
LABEL = "离线规则 · 非大模型"


def ensure_schema(con):
    con.executescript(SCHEMA)


def normalize_phone(value):
    phone = re.sub(r"[\s\-]", "", value or "")
    if not re.fullmatch(r"\d{6,20}", phone):
        return None
    return phone


def extract_submissions(text):
    """Copy of organizer wording already in hand. Does not fetch a URL."""
    folded = text.lower()
    found = []
    for label, keys in SUBMISSION_RULES:
        if any(key.lower() in folded for key in keys):
            found.append(label)
    return found


def extract_intro(intro, role, skills):
    blob = f"{intro} {role} {skills}"
    keys = [word for word in ("前端", "后端", "设计", "产品", "路演", "演示", "文档", "视频", "海报", "接口", "页面") if word in blob]
    if keys:
        return "、".join(keys)
    line = intro.strip().split("。")[0].strip()
    return line[:80] or role


def draft_plan(members):
    lines = []
    for member in members:
        optional = member["extract"] == "海报" or (member["extract"] and "海报" in member["extract"] and not any(word in member["extract"] for word in ("前端", "后端", "产品", "接口", "页面", "文档")))
        lines.append({"name": member["name"], "user_id": member["user_id"], "work": member["extract"] or member["role"], "priority": "should" if optional else "must"})
    return lines


def _hours_left(deadline, current):
    end, start = datetime.fromisoformat(deadline), datetime.fromisoformat(current)
    if (end.tzinfo is None) != (start.tzinfo is None):
        end, start = end.replace(tzinfo=None), start.replace(tzinfo=None)
    return (end - start).total_seconds() / 3600


def rank_idea(body, skills_blob, hours_left):
    fit = 2 if any(word in body for word in ("协作", "比赛", "提交", "演示", "黑客松", "分工")) else 1
    ability = 2 if any(word and word in body for word in skills_blob.split()) else 1
    if any(word in skills_blob and word in body for word in ("前端", "后端", "产品", "设计", "页面", "文档")):
        ability = 2
    finishable = 1
    if any(word in body for word in ("主办方系统", "全套培训", "自动找队友", "全国排名")):
        finishable = 0
    elif hours_left >= 8 and len(body) <= 280:
        finishable = 2
    problems = "范围可能超出剩余时间。" if finishable < 2 else "主要风险是把可选项也做成必须。"
    if finishable == 0:
        realistic = "这场先不做完整版，只留下一条记录。"
    elif finishable == 2:
        realistic = "截止前可以做出一条能演示的路径。"
    else:
        realistic = "截止前只做最小的一块，其余记下。"
    return {"core": body.strip().split("。")[0][:80], "fit": fit, "ability": ability, "finishable": finishable, "score": fit + ability + finishable, "problems": problems, "realistic": realistic}


def split_ranked(ideas):
    ordered = sorted(ideas, key=lambda item: (-item["score"], item["created_at"]))
    return ordered[:3], ordered[3:]


def skill_text(topic, trunk, submissions):
    lines = ["# 我们在做什么", "", f"题目：{topic}", f"主干：{trunk}", "必须提交："]
    lines.extend(f"- {item}" for item in submissions)
    lines.extend(["", "这份技能全队相同。", "用它回答「我们在做什么」，并指出和题目、主干、提交清单不一致的话。", "技术设计和实现不在这里，由每个人在自己的工具里做。", LABEL])
    return "\n".join(lines)


def strategic_kind(text):
    if any(word in text for word in ("改题目", "换题目", "换题", "不做这个题目")):
        return "topic"
    if any(word in text for word in ("改主干", "加进主干", "改主线", "必须任务加上")):
        return "trunk"
    if any(word in text for word in ("改提交", "不用交", "去掉宣传片", "去掉 PPT", "去掉PPT", "改提交清单")):
        return "submissions"
    return None


def vote_packet(kind, body, members):
    label = {"topic": "已确认的题目", "trunk": "主干", "submissions": "提交清单"}[kind]
    clarify = f"这条建议想改{label}。原文：{body.strip()[:180]}"
    frame = f"先保住现在的{label}。若队决定改，只改这一处，不推倒整份方案。"
    parts = [{"user_id": member["user_id"], "name": member["name"], "part": f"按你现在的{member['role'] or '角色'}，截止前先做完自己的必须项，再决定这条建议还排不排得下。"} for member in members]
    return clarify, frame, parts


def library_suggestion(body, topic, trunk):
    if topic and strategic_kind(body) == "topic":
        return f"资料库已记下。这和已确认的题目「{topic}」不是同一件事，不会自动改题目。"
    if trunk and strategic_kind(body) == "trunk":
        return f"资料库已记下。主干仍是「{trunk}」，这条只是建议。"
    return "资料库已记下。已确认的主干不变。队长若要采纳，请在规划里发布或调整一项。"


def direction_reply(message, topic, trunk, submissions):
    subs = "、".join(submissions) or "还没有提交清单"
    if any(word in message for word in ("我们在做什么", "在做什么", "做什么")):
        return f"题目是{topic or '还没确认'}。主干是{trunk or '还没确认'}。要交：{subs}。"
    kind = strategic_kind(message)
    if kind == "topic" and topic:
        return f"这和已确认的题目「{topic}」不一致。队员提出的改题目要先表决。"
    if kind == "trunk" and trunk:
        return f"这和已确认的主干「{trunk}」不一致。不会自动改任务。"
    if kind == "submissions":
        return f"提交清单现在是：{subs}。改清单要先表决。"
    return f"按已确认的题目和提交清单看，没有发现偏离。{LABEL}"


def coach_reply(message, skills):
    if "流程图" in message:
        return "流程图可以用这句话排成方框。技术细节留在你自己的工具里。这是离线教练，没有读取旧对话。"
    if "多长" in message or "PPT" in message or "ppt" in message:
        return f"按你登记的水平（{skills[:40] or '尚未填写'}），PPT 先讲清题目、谁做什么、演示路径。{LABEL}"
    return f"按你登记的水平回答：{skills[:40] or '尚未填写'}。这是离线教练，不是大模型，也没有读取旧对话。"


def flow_boxes(sentence):
    parts = [part.strip(" ：:") for part in re.split(r"[，。、]|(?:->)|(?:→)", sentence) if part.strip(" ：:")]
    return " → ".join(parts[:6] or ["开始", "完成"])


def growth_line(role, done_titles):
    done = "、".join(done_titles) if done_titles else "还没有把进度标到完成"
    return f"这场角色是{role or '未填'}。完成的任务：{done}。下一场仍按这个水平分配，不把没做过的技术写成已经会。"


def register_studio(api, db, problem, now, uid, digest):
    def log(con, squad_id, actor, detail):
        con.execute("INSERT INTO squad_log(squad_id,actor_id,detail,created_at) VALUES(?,?,?,?)", (squad_id, actor, detail, now()))

    def person_from_header(con, header):
        if not header.startswith("Bearer ") or len(header) > 600:
            raise problem(401, "unauthorized", "请先用手机号进入。")
        row = con.execute("SELECT * FROM people WHERE token_hash=?", (digest(header[7:]),)).fetchone()
        if not row:
            raise problem(401, "unauthorized", "登录已失效，请用同一个手机号再进入。")
        return dict(row)

    def squad_of(con, squad_id, user_id):
        squad = con.execute("SELECT * FROM squads WHERE id=?", (squad_id,)).fetchone()
        if not squad:
            raise problem(404, "not_found", "队伍不存在。")
        member = con.execute("SELECT * FROM squad_members WHERE squad_id=? AND user_id=?", (squad_id, user_id)).fetchone()
        if not member:
            raise problem(403, "not_in_squad", "你不在这支队伍里。")
        return dict(squad), dict(member)

    def members_of(con, squad_id):
        rows = con.execute("""SELECT m.*, p.name, p.skills, p.phone FROM squad_members m
            JOIN people p ON p.id=m.user_id WHERE m.squad_id=? ORDER BY m.rowid""", (squad_id,)).fetchall()
        return [dict(row) for row in rows]

    def public_member(member, captain_id):
        return {"user_id": member["user_id"], "name": member["name"], "role": member["role"], "extract": member["extract"],
                "doing": member["doing"], "skill_installed": bool(member["skill_installed"]), "tool": member["tool"],
                "captain": member["user_id"] == captain_id, "avatar": member["name"][:1]}

    def snapshot(con, squad_id, user):
        squad, me = squad_of(con, squad_id, user["id"])
        contest = dict(con.execute("SELECT * FROM contests WHERE id=?", (squad["contest_id"],)).fetchone())
        contest["submissions"] = json.loads(contest["submissions"])
        members = members_of(con, squad_id)
        ideas = [dict(row) for row in con.execute("SELECT * FROM ideas WHERE squad_id=? ORDER BY created_at", (squad_id,))]
        top, rest = split_ranked(ideas)
        tasks = [dict(row) for row in con.execute("SELECT * FROM squad_tasks WHERE squad_id=? ORDER BY rowid", (squad_id,))]
        notes = [dict(row) for row in con.execute("SELECT * FROM library_notes WHERE squad_id=? ORDER BY created_at", (squad_id,))]
        votes = []
        for vote in con.execute("SELECT * FROM votes WHERE squad_id=? ORDER BY created_at", (squad_id,)):
            item = dict(vote)
            item["parts"] = json.loads(item["parts"])
            item["ballots"] = [dict(row) for row in con.execute("SELECT user_id, choice FROM ballots WHERE vote_id=?", (vote["id"],))]
            votes.append(item)
        shelf = []
        for row in con.execute("SELECT * FROM shelf WHERE squad_id=? ORDER BY created_at", (squad_id,)):
            item = dict(row)
            item["editors"] = json.loads(item["editors"])
            shelf.append(item)
        names = {member["user_id"]: member["name"] for member in members}
        events = [dict(row) for row in con.execute("SELECT * FROM squad_log WHERE squad_id=? ORDER BY id", (squad_id,))]
        for event in events:
            event["actor"] = names.get(event["actor_id"], "")
        return {"squad": {**squad, "draft": json.loads(squad["draft"] or "[]"), "confirmed": bool(squad["confirmed"]), "finished": bool(squad["finished"])},
                "contest": contest, "me": {"id": user["id"], "name": user["name"], "phone": user["phone"], "skills": user["skills"],
                "profile": user["profile"], "github_linked": bool(user["github_linked"]), "feishu_linked": bool(user["feishu_linked"]),
                "growth": user["growth"], "captain": user["id"] == squad["captain_id"], "skill_installed": bool(me["skill_installed"]),
                "doing": me["doing"], "role": me["role"]},
                "members": [public_member(member, squad["captain_id"]) for member in members],
                "ideas": {"top": top, "rest": rest}, "tasks": tasks, "library": notes, "votes": votes, "shelf": shelf, "log": events,
                "source_label": LABEL}

    @api.post("/api/studio/register")
    def register(body: dict, authorization: str = ""):
        phone = normalize_phone(body.get("phone", ""))
        if not phone:
            raise problem(422, "invalid_phone", "手机号用 6 到 20 位数字，作为本机登录名。没有短信。")
        with db(True) as con:
            existing = con.execute("SELECT * FROM people WHERE phone=?", (phone,)).fetchone()
            if existing:
                token_clear = secrets.token_urlsafe(24)
                con.execute("UPDATE people SET token_hash=? WHERE id=?", (digest(token_clear), existing["id"]))
                existing = dict(existing)
                return {"user_id": existing["id"], "token": token_clear, "returning": True, "name": existing["name"],
                        "skills": existing["skills"], "profile": existing["profile"], "growth": existing["growth"],
                        "github_linked": bool(existing["github_linked"]), "feishu_linked": bool(existing["feishu_linked"]),
                        "notice": "这个手机号已经注册。画像和技能保持第一次填写的，没有覆盖。"}
            name = str(body.get("name") or "").strip()
            profile = str(body.get("profile") or "").strip()
            skills = str(body.get("skills") or "").strip()
            if not name or not profile or not skills:
                raise problem(422, "profile_required", "第一次进入要填写名字、画像和目前做得到的事。")
            pid, token_clear = uid(), secrets.token_urlsafe(24)
            con.execute("""INSERT INTO people(id,phone,name,profile,skills,github_linked,feishu_linked,token_hash,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (pid, phone, name[:40], profile[:2000], skills[:500], int(bool(body.get("github"))), int(bool(body.get("feishu"))), digest(token_clear), now()))
            return {"user_id": pid, "token": token_clear, "returning": False, "name": name[:40], "skills": skills[:500],
                    "profile": profile[:2000], "growth": "", "github_linked": bool(body.get("github")), "feishu_linked": bool(body.get("feishu")),
                    "notice": "本机用手机号当作登录名，没有发送短信。"}

    @api.post("/api/studio/links")
    def links(body: dict, authorization: str = Header(default="")):
        with db(True) as con:
            user = person_from_header(con, authorization)
            github = int(bool(body.get("github")))
            feishu = int(bool(body.get("feishu")))
            con.execute("UPDATE people SET github_linked=?, feishu_linked=? WHERE id=?", (github, feishu, user["id"]))
            return {"github_linked": bool(github), "feishu_linked": bool(feishu), "notice": "本机只做标记，没有打开 GitHub 或飞书。"}

    @api.get("/api/studio/me")
    def me(authorization: str = Header(default="")):
        with db() as con:
            user = person_from_header(con, authorization)
            squads = [dict(row) for row in con.execute("""SELECT s.id, s.name, s.code, s.stage, s.topic, c.name AS contest
                FROM squads s JOIN squad_members m ON m.squad_id=s.id JOIN contests c ON c.id=s.contest_id
                WHERE m.user_id=? ORDER BY s.created_at DESC""", (user["id"],))]
            contests = [dict(row) for row in con.execute("SELECT id, name, deadline, submissions, created_at FROM contests WHERE owner_id=? ORDER BY created_at DESC", (user["id"],))]
            for contest in contests:
                contest["submissions"] = json.loads(contest["submissions"])
            friends = [dict(row) for row in con.execute("""SELECT p.id AS user_id, p.name, p.phone FROM friendships f
                JOIN people p ON p.id=f.friend_id WHERE f.user_id=?""", (user["id"],))]
            return {"id": user["id"], "name": user["name"], "phone": user["phone"], "profile": user["profile"], "skills": user["skills"],
                    "growth": user["growth"], "github_linked": bool(user["github_linked"]), "feishu_linked": bool(user["feishu_linked"]),
                    "squads": squads, "contests": contests, "friends": friends}

    @api.post("/api/studio/friends")
    def add_friend(body: dict, authorization: str = Header(default="")):
        phone = normalize_phone(body.get("phone", ""))
        if not phone:
            raise problem(422, "invalid_phone", "请填写对方注册时用的手机号。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            friend = con.execute("SELECT id, name FROM people WHERE phone=?", (phone,)).fetchone()
            if not friend:
                raise problem(404, "not_found", "对方还没注册。队伍码不需要先加好友。")
            if friend["id"] == user["id"]:
                raise problem(422, "invalid_friend", "不能加自己。")
            con.execute("INSERT OR IGNORE INTO friendships(user_id, friend_id) VALUES(?,?)", (user["id"], friend["id"]))
            return {"user_id": friend["id"], "name": friend["name"]}

    @api.post("/api/studio/contests")
    def create_contest(body: dict, authorization: str = Header(default="")):
        name = str(body.get("name") or "").strip()
        deadline = str(body.get("deadline") or "").strip()
        source = str(body.get("source_text") or "").strip()
        if not name or not deadline or len(source) < 8:
            raise problem(422, "contest_required", "填写比赛名称、结束时间，并粘贴主办方公开材料。")
        try:
            datetime.fromisoformat(deadline)
        except ValueError:
            raise problem(422, "invalid_deadline", "结束时间要带时区，例如 2026-10-28T18:00:00+08:00。") from None
        if source.lower().startswith("http://") or source.lower().startswith("https://"):
            raise problem(422, "paste_text", "本机不抓取网页。请粘贴公开材料的正文。")
        found = extract_submissions(source)
        with db(True) as con:
            user = person_from_header(con, authorization)
            cid = uid()
            con.execute("INSERT INTO contests(id,owner_id,name,deadline,source_text,submissions,created_at) VALUES(?,?,?,?,?,?,?)",
                        (cid, user["id"], name[:80], deadline, source[:20000], json.dumps(found, ensure_ascii=False), now()))
            return {"id": cid, "name": name[:80], "deadline": deadline, "submissions": found, "source_label": LABEL,
                    "notice": "清单从粘贴的正文抽出。没有自动读取主办方帖子。"}

    @api.post("/api/studio/squads")
    def create_squad(body: dict, authorization: str = Header(default="")):
        name = str(body.get("name") or "").strip()
        if not name:
            raise problem(422, "name_required", "先写队伍名称。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            contest = con.execute("SELECT * FROM contests WHERE id=? AND owner_id=?", (body.get("contest_id"), user["id"])).fetchone()
            if not contest:
                raise problem(404, "not_found", "先选择一场你导入的比赛。")
            sid, code = uid(), uid()[:8]
            con.execute("INSERT INTO squads(id,contest_id,name,code,captain_id,created_at) VALUES(?,?,?,?,?,?)", (sid, contest["id"], name[:40], code, user["id"], now()))
            con.execute("INSERT INTO squad_members(squad_id,user_id,role) VALUES(?,?,?)", (sid, user["id"], ""))
            log(con, sid, user["id"], f"{user['name']} 创建队伍，成为队长。")
            return {"id": sid, "code": code, "captain": True}

    @api.patch("/api/studio/squads/{sid}")
    def rename_squad(sid: str, body: dict, authorization: str = Header(default="")):
        name = str(body.get("name") or "").strip()
        if not name:
            raise problem(422, "name_required", "队伍名称不能空。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if user["id"] != squad["captain_id"]:
                raise problem(403, "captain_required", "由队长修改队伍名称。")
            con.execute("UPDATE squads SET name=? WHERE id=?", (name[:40], sid))
            log(con, sid, user["id"], f"队长把队伍名称改为「{name[:40]}」。")
            return {"name": name[:40]}

    @api.post("/api/studio/squads/join")
    def join_squad(body: dict, authorization: str = Header(default="")):
        code = str(body.get("code") or "").strip()
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad = con.execute("SELECT * FROM squads WHERE code=?", (code,)).fetchone()
            if not squad:
                raise problem(404, "not_found", "队伍码不对。")
            if squad["confirmed"]:
                raise problem(409, "team_locked", "这支队伍已经确认，本机版本不再加入新人。")
            already = con.execute("SELECT 1 FROM squad_members WHERE squad_id=? AND user_id=?", (squad["id"], user["id"])).fetchone()
            con.execute("INSERT OR IGNORE INTO squad_members(squad_id,user_id,role) VALUES(?,?,?)", (squad["id"], user["id"], ""))
            friends = con.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?", (squad["captain_id"], user["id"])).fetchone()
            if not already:
                log(con, squad["id"], user["id"], f"{user['name']} 用队伍码加入。")
            return {"id": squad["id"], "friend_of_captain": bool(friends), "already_member": bool(already),
                    "notice": "你已经在这支队伍里。" if already else "队伍码可以直接加入，不必先成为好友。"}

    @api.post("/api/studio/squads/{sid}/intro")
    def save_intro(sid: str, body: dict, authorization: str = Header(default="")):
        role = str(body.get("role") or "").strip()
        intro = str(body.get("intro") or "").strip()
        if len(intro) < 8 or not role:
            raise problem(422, "intro_required", "贴一段自我介绍，并选一个角色。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if squad["confirmed"]:
                raise problem(409, "team_locked", "分工草案已经确认。")
            extract = extract_intro(intro, role, user["skills"])
            con.execute("UPDATE squad_members SET role=?, intro=?, extract=? WHERE squad_id=? AND user_id=?", (role[:40], intro[:4000], extract, sid, user["id"]))
            return {"extract": extract}

    @api.get("/api/studio/squads/{sid}")
    def get_squad(sid: str, authorization: str = Header(default="")):
        with db() as con:
            user = person_from_header(con, authorization)
            return snapshot(con, sid, user)

    @api.post("/api/studio/squads/{sid}/confirm")
    def confirm_squad(sid: str, authorization: str = Header(default="")):
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if user["id"] != squad["captain_id"]:
                raise problem(403, "captain_required", "由队长确认分工草案。")
            if squad["confirmed"]:
                raise problem(409, "already_confirmed", "已经确认过了。")
            members = members_of(con, sid)
            if len(members) < 2 or any(not member["intro"] or not member["role"] for member in members):
                raise problem(422, "intros_required", "至少两人，且每人都贴了介绍并选了角色。")
            plan = draft_plan(members)
            con.execute("UPDATE squads SET confirmed=1, draft=?, stage='topic' WHERE id=?", (json.dumps(plan, ensure_ascii=False), sid))
            log(con, sid, user["id"], "队长确认分工草案。进入选题确认。")
            return {"stage": "topic", "draft": plan, "show_check": True}

    @api.post("/api/studio/squads/{sid}/ideas")
    def add_idea(sid: str, body: dict, authorization: str = Header(default="")):
        text = str(body.get("body") or "").strip()
        if len(text) < 4:
            raise problem(422, "idea_required", "写下要评估的想法。引用旧对话时，把那段贴在这里。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if not squad["confirmed"]:
                raise problem(409, "team_not_ready", "先确认组队。")
            if squad["topic"]:
                raise problem(409, "topic_locked", "题目已经确认。要改题目，请把建议送进团队空间走表决。")
            contest = con.execute("SELECT deadline FROM contests WHERE id=?", (squad["contest_id"],)).fetchone()
            skills = " ".join(member["skills"] + member["role"] for member in members_of(con, sid))
            ranked = rank_idea(text, skills, _hours_left(contest["deadline"], now()))
            iid = uid()
            con.execute("""INSERT INTO ideas(id,squad_id,author_id,body,core,fit,ability,finishable,score,problems,realistic,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (iid, sid, user["id"], text[:2000], ranked["core"], ranked["fit"], ranked["ability"], ranked["finishable"], ranked["score"], ranked["problems"], ranked["realistic"], now()))
            log(con, sid, user["id"], "送入一条本队想法。")
            return {"id": iid, **ranked, "source_label": LABEL}

    @api.post("/api/studio/squads/{sid}/topic")
    def confirm_topic(sid: str, body: dict, authorization: str = Header(default="")):
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if user["id"] != squad["captain_id"]:
                raise problem(403, "captain_required", "由队长确认题目。")
            idea = con.execute("SELECT * FROM ideas WHERE id=? AND squad_id=?", (body.get("idea_id"), sid)).fetchone()
            if not idea:
                raise problem(404, "not_found", "这不是本队的候选。")
            contest = con.execute("SELECT submissions FROM contests WHERE id=?", (squad["contest_id"],)).fetchone()
            submissions = json.loads(contest["submissions"])
            trunk = f"做出「{idea['core']}」里截止前能演示的一条路径"
            skill = skill_text(idea["core"], trunk, submissions)
            con.execute("UPDATE squads SET topic=?, topic_core=?, trunk=?, skill_body=? WHERE id=?", (idea["core"], idea["core"], trunk, skill, sid))
            log(con, sid, user["id"], f"队长确认题目：{idea['core']}")
            return {"topic": idea["core"], "trunk": trunk, "skill": skill}

    @api.get("/api/studio/squads/{sid}/skill")
    def get_skill(sid: str, authorization: str = Header(default="")):
        with db() as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if not squad["skill_body"]:
                raise problem(409, "topic_required", "先确认题目，才会生成全队同一份技能。")
            return PlainTextResponse(squad["skill_body"], media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="team-skill.md"'})

    @api.post("/api/studio/squads/{sid}/skill/install")
    def install_skill(sid: str, body: dict, authorization: str = Header(default="")):
        tool = body.get("tool")
        if tool not in {"codex", "workbuddy"}:
            raise problem(422, "tool_required", "选 Codex 或 Workbuddy。本机只标记已安装，不连接这两个工具。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if not squad["skill_body"]:
                raise problem(409, "topic_required", "先确认题目。")
            con.execute("UPDATE squad_members SET skill_installed=1, tool=? WHERE squad_id=? AND user_id=?", (tool, sid, user["id"]))
            log(con, sid, user["id"], f"{user['name']} 安装了全队同一份技能（{tool}）。")
            return {"installed": True, "tool": tool, "same_file": True}

    def accept_library(con, sid, user, text):
        squad = con.execute("SELECT topic, trunk FROM squads WHERE id=?", (sid,)).fetchone()
        suggestion = library_suggestion(text, squad["topic"], squad["trunk"])
        nid = uid()
        con.execute("INSERT INTO library_notes(id,squad_id,author_id,body,suggestion,created_at) VALUES(?,?,?,?,?,?)", (nid, sid, user["id"], text[:4000], suggestion, now()))
        vote = None
        kind = strategic_kind(text)
        if kind and squad["topic"]:
            clarify, frame, parts = vote_packet(kind, text, members_of(con, sid))
            vid = uid()
            con.execute("INSERT INTO votes(id,squad_id,author_id,body,kind,clarify,frame,parts,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (vid, sid, user["id"], text[:2000], kind, clarify, frame, json.dumps(parts, ensure_ascii=False), now()))
            log(con, sid, user["id"], f"建议会改{ {'topic':'题目','trunk':'主干','submissions':'提交清单'}[kind] }，发起表决，未改任务。")
            vote = {"id": vid, "kind": kind, "applied": False}
        else:
            log(con, sid, user["id"], "一条讨论写入团队资料库。")
        return {"id": nid, "suggestion": suggestion, "vote": vote, "tasks_unchanged": True}

    @api.post("/api/studio/squads/{sid}/library")
    def add_library(sid: str, body: dict, authorization: str = Header(default="")):
        text = str(body.get("body") or "").strip()
        if len(text) < 2:
            raise problem(422, "empty", "写一点再发送。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad_of(con, sid, user["id"])
            before = con.execute("SELECT topic, trunk FROM squads WHERE id=?", (sid,)).fetchone()
            result = accept_library(con, sid, user, text)
            after = con.execute("SELECT topic, trunk FROM squads WHERE id=?", (sid,)).fetchone()
            if before["topic"] != after["topic"] or before["trunk"] != after["trunk"]:
                raise problem(500, "internal_error", "资料库不应改写题目或主干。")
            return result

    @api.post("/api/studio/votes/{vid}/ballots")
    def ballot(vid: str, body: dict, authorization: str = Header(default="")):
        choice = body.get("choice")
        if choice not in {"yes", "no"}:
            raise problem(422, "choice_required", "选择同意或先不改。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            vote = con.execute("SELECT * FROM votes WHERE id=?", (vid,)).fetchone()
            if not vote:
                raise problem(404, "not_found", "表决不存在。")
            squad_of(con, vote["squad_id"], user["id"])
            before = con.execute("SELECT topic, trunk FROM squads WHERE id=?", (vote["squad_id"],)).fetchone()
            con.execute("INSERT INTO ballots(vote_id,user_id,choice) VALUES(?,?,?) ON CONFLICT(vote_id,user_id) DO UPDATE SET choice=excluded.choice", (vid, user["id"], choice))
            total = con.execute("SELECT COUNT(*) c FROM squad_members WHERE squad_id=?", (vote["squad_id"],)).fetchone()["c"]
            cast = con.execute("SELECT COUNT(*) c FROM ballots WHERE vote_id=?", (vid,)).fetchone()["c"]
            status = "recorded" if cast >= total else "open"
            con.execute("UPDATE votes SET status=? WHERE id=?", (status, vid))
            after = con.execute("SELECT topic, trunk FROM squads WHERE id=?", (vote["squad_id"],)).fetchone()
            contest_same = before["topic"] == after["topic"] and before["trunk"] == after["trunk"]
            if not contest_same:
                raise problem(500, "internal_error", "表决不应改写题目或主干。")
            log(con, vote["squad_id"], user["id"], f"{user['name']} 表决：{'同意' if choice=='yes' else '先不改'}。任务板未改。")
            return {"status": status, "applied": False, "topic_unchanged": True, "trunk_unchanged": True}

    @api.post("/api/studio/squads/{sid}/tasks")
    def publish_task(sid: str, body: dict, authorization: str = Header(default="")):
        title = str(body.get("title") or "").strip()
        priority = body.get("priority")
        if priority not in {"must", "should"} or not title:
            raise problem(422, "task_required", "写上任务，并标必须或可选。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if user["id"] != squad["captain_id"]:
                raise problem(403, "captain_required", "只有队长发布任务，且不用等表决。")
            owner = body.get("owner_id")
            if not con.execute("SELECT 1 FROM squad_members WHERE squad_id=? AND user_id=?", (sid, owner)).fetchone():
                raise problem(422, "invalid_owner", "负责人要在这支队伍里。")
            contest = con.execute("SELECT deadline FROM contests WHERE id=?", (squad["contest_id"],)).fetchone()
            due = str(body.get("due_at") or contest["deadline"])
            try:
                if datetime.fromisoformat(due) > datetime.fromisoformat(contest["deadline"]):
                    raise problem(422, "invalid_due_date", "任务截止不能晚于比赛结束。")
            except ValueError:
                raise problem(422, "invalid_due_date", "截止时间格式不对。") from None
            tid = uid()
            con.execute("""INSERT INTO squad_tasks(id,squad_id,title,owner_id,priority,due_at,talk_to,alone,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (tid, sid, title[:120], owner, priority, due, str(body.get("talk_to") or "")[:40], int(bool(body.get("alone", True))), now()))
            log(con, sid, user["id"], f"队长发布任务：{title[:40]}。不等表决。")
            return {"id": tid, "waited_for_vote": False}

    @api.patch("/api/studio/squads/{sid}/tasks/{tid}")
    def adjust_task(sid: str, tid: str, body: dict, authorization: str = Header(default="")):
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if user["id"] != squad["captain_id"]:
                raise problem(403, "captain_required", "只有队长能改必须或可选、以及负责人。")
            task = con.execute("SELECT * FROM squad_tasks WHERE id=? AND squad_id=?", (tid, sid)).fetchone()
            if not task:
                raise problem(404, "not_found", "任务不存在。")
            priority = body.get("priority", task["priority"])
            owner = body.get("owner_id", task["owner_id"])
            if priority not in {"must", "should"}:
                raise problem(422, "task_required", "只能改成必须或可选。")
            if not con.execute("SELECT 1 FROM squad_members WHERE squad_id=? AND user_id=?", (sid, owner)).fetchone():
                raise problem(422, "invalid_owner", "负责人要在这支队伍里。")
            con.execute("UPDATE squad_tasks SET priority=?, owner_id=? WHERE id=?", (priority, owner, tid))
            log(con, sid, user["id"], f"队长调整任务「{task['title']}」。没有整份重排。")
            return {"id": tid, "priority": priority, "owner_id": owner}

    @api.post("/api/studio/squads/{sid}/tasks/{tid}/progress")
    def progress(sid: str, tid: str, body: dict, authorization: str = Header(default="")):
        value = body.get("progress")
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            raise problem(422, "progress_required", "进度用 0 到 100 的整数。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad_of(con, sid, user["id"])
            task = con.execute("SELECT * FROM squad_tasks WHERE id=? AND squad_id=?", (tid, sid)).fetchone()
            if not task or task["owner_id"] != user["id"]:
                raise problem(403, "owner_required", "只有负责人更新自己的进度。")
            doing = str(body.get("doing") if body.get("doing") is not None else "").strip()[:40]
            con.execute("UPDATE squad_tasks SET progress=? WHERE id=?", (value, tid))
            con.execute("UPDATE squad_members SET doing=? WHERE squad_id=? AND user_id=?", (doing, sid, user["id"]))
            return {"progress": value, "doing": doing}

    @api.post("/api/studio/squads/{sid}/shelf")
    def add_shelf(sid: str, body: dict, authorization: str = Header(default="")):
        kind = body.get("kind")
        title = str(body.get("title") or "").strip()
        text = str(body.get("body") or "").strip()
        if kind not in {"link", "ppt", "flow", "note"} or not title:
            raise problem(422, "shelf_required", "写上名称。类型是链接、PPT、流程图或笔记。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad_of(con, sid, user["id"])
            if strategic_kind(text):
                result = accept_library(con, sid, user, text)
                return {"stored": "vote" if result["vote"] else "library", **result}
            editors = body.get("editors") if isinstance(body.get("editors"), list) else []
            iid = uid()
            con.execute("INSERT INTO shelf(id,squad_id,author_id,kind,title,body,editors,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (iid, sid, user["id"], kind, title[:80], text[:8000], json.dumps(editors), now()))
            log(con, sid, user["id"], f"上传到成果架：{title[:40]}")
            return {"id": iid, "stored": "shelf", "vote": None}

    @api.patch("/api/studio/squads/{sid}/shelf/{iid}")
    def edit_shelf(sid: str, iid: str, body: dict, authorization: str = Header(default="")):
        text = str(body.get("body") or "").strip()
        if not text:
            raise problem(422, "shelf_required", "写下要改的内容。")
        if strategic_kind(text):
            raise problem(409, "needs_vote", "这会改题目、主干或提交清单。请送到讨论里走表决，不要直接改成果。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad_of(con, sid, user["id"])
            item = con.execute("SELECT * FROM shelf WHERE id=? AND squad_id=?", (iid, sid)).fetchone()
            if not item:
                raise problem(404, "not_found", "成果不在架上。")
            editors = json.loads(item["editors"] or "[]")
            if user["id"] != item["author_id"] and user["id"] not in editors:
                raise problem(403, "editor_required", "只有上传的人，或被授权的人，能改这份成果。")
            con.execute("UPDATE shelf SET body=? WHERE id=?", (text[:8000], iid))
            log(con, sid, user["id"], f"{user['name']} 修改了成果「{item['title']}」。")
            return {"id": iid}

    @api.post("/api/studio/squads/{sid}/repo")
    def make_repo(sid: str, authorization: str = Header(default="")):
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if user["id"] != squad["captain_id"]:
                raise problem(403, "captain_required", "由队长建立团队仓库记录。")
            if not user["github_linked"]:
                raise problem(409, "github_link_required", "先在注册信息里标成本机已绑定 GitHub。不会打开 GitHub。")
            iid = uid()
            local = f"local://squad/{squad['code']}"
            con.execute("INSERT INTO shelf(id,squad_id,author_id,kind,title,body,editors,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (iid, sid, user["id"], "link", "团队仓库", local, "[]", now()))
            log(con, sid, user["id"], "队长建立了本机团队仓库记录，没有调用 GitHub。")
            return {"id": iid, "url": local, "remote": False}

    @api.post("/api/studio/squads/{sid}/flow")
    def make_flow(sid: str, body: dict, authorization: str = Header(default="")):
        sentence = str(body.get("request") or "").strip()
        if len(sentence) < 2:
            raise problem(422, "request_required", "用一句话说明流程。")
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad_of(con, sid, user["id"])
            chart = flow_boxes(sentence)
            return {"chart": chart, "source_label": LABEL, "notice": "这是个人草稿。要给全队看，再上传到成果架。"}

    @api.post("/api/studio/squads/{sid}/coach")
    def coach(sid: str, body: dict, authorization: str = Header(default="")):
        message = str(body.get("message") or "").strip()
        with db() as con:
            user = person_from_header(con, authorization)
            squad_of(con, sid, user["id"])
            return {"reply": coach_reply(message, user["skills"]), "source_label": LABEL}

    @api.post("/api/studio/squads/{sid}/direction")
    def direction(sid: str, body: dict, authorization: str = Header(default="")):
        message = str(body.get("message") or "").strip()
        with db() as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            contest = con.execute("SELECT submissions FROM contests WHERE id=?", (squad["contest_id"],)).fetchone()
            return {"reply": direction_reply(message, squad["topic"], squad["trunk"], json.loads(contest["submissions"])), "source_label": LABEL}

    @api.post("/api/studio/squads/{sid}/finish")
    def finish(sid: str, authorization: str = Header(default="")):
        with db(True) as con:
            user = person_from_header(con, authorization)
            squad, _ = squad_of(con, sid, user["id"])
            if user["id"] != squad["captain_id"]:
                raise problem(403, "captain_required", "由队长结束这场，写入成长记录。")
            if squad["finished"]:
                return {"finished": True, "notice": "已经记过这场。"}
            tasks = [dict(row) for row in con.execute("SELECT * FROM squad_tasks WHERE squad_id=?", (sid,))]
            for member in members_of(con, sid):
                done = [task["title"] for task in tasks if task["owner_id"] == member["user_id"] and task["progress"] >= 100]
                line = growth_line(member["role"], done)
                previous = con.execute("SELECT growth FROM people WHERE id=?", (member["user_id"],)).fetchone()["growth"]
                merged = (previous + "\n" + line).strip()
                con.execute("UPDATE people SET growth=? WHERE id=?", (merged, member["user_id"]))
            con.execute("UPDATE squads SET finished=1, stage='done' WHERE id=?", (sid,))
            log(con, sid, user["id"], "队长结束这场。成长记录已写入每人的账号，没有重问画像。")
            return {"finished": True}
