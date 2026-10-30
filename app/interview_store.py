"""Per-person interview persistence and web endpoints (INTERVIEW-02).

Owner-only. Nothing here is shown to teams or plugins, and nothing writes people.profile/skills.
Model calls run with no database transaction open; results are saved only if the state version is unchanged.
"""
import hashlib
import json
import re
import threading

from fastapi import Header

from .interview import AGE_BANDS, CONTROL, MAX_QUESTIONS, MAX_USER_TEXT, STAGES, InterviewError, next_turn

SCHEMA = """
CREATE TABLE IF NOT EXISTS core_interviews (
 user_id TEXT PRIMARY KEY REFERENCES people(id), age_band TEXT NOT NULL, stage TEXT NOT NULL,
 status TEXT NOT NULL, version INTEGER NOT NULL, current_question_id TEXT,
 draft TEXT, draft_meta TEXT, source TEXT NOT NULL, confirmed_at TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS core_interview_messages (
 user_id TEXT NOT NULL REFERENCES people(id), seq INTEGER NOT NULL, id TEXT NOT NULL, role TEXT NOT NULL,
 text TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '', dimension TEXT NOT NULL DEFAULT '', model_id TEXT,
 created_at TEXT NOT NULL, PRIMARY KEY(user_id, seq), UNIQUE(user_id, id)
);
CREATE TABLE IF NOT EXISTS core_interview_requests (
 user_id TEXT NOT NULL REFERENCES people(id), request_id TEXT NOT NULL, kind TEXT NOT NULL,
 fingerprint TEXT NOT NULL, version_after INTEGER NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(user_id, request_id)
);
"""
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")


def register_interview(api, db, problem, now, person, runner=None, scrub=lambda text: text):
    busy, busy_lock = set(), threading.Lock()

    def owner(con, header):
        if header.startswith("Bearer sbconn_"):
            raise problem(403, "browser_required", "访谈只能在网页登录后进行，插件不能读取或代答。")
        return person(con, header)["id"]

    def fields(body, allowed, required=()):
        if not isinstance(body, dict) or set(body) - set(allowed) or any(k not in body for k in required):
            raise problem(422, "invalid_input", "请求字段不正确。")

    def version_of(body):
        value = body["version"]
        if type(value) is not int or value < 1:
            raise problem(422, "invalid_input", "version必须是正整数。")
        return value

    def request_id_of(body):
        value = body["request_id"]
        if not isinstance(value, str) or not REQUEST_ID.fullmatch(value):
            raise problem(422, "invalid_input", "request_id必须是8到64位字母、数字、下划线或连字符。")
        return value

    def fingerprint(kind, payload):
        return hashlib.sha256(json.dumps([kind, payload], ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def load(con, user):
        row = con.execute("SELECT * FROM core_interviews WHERE user_id=?", (user,)).fetchone()
        if not row:
            return None, []
        return dict(row), [dict(m) for m in con.execute("SELECT * FROM core_interview_messages WHERE user_id=? ORDER BY seq", (user,))]

    def view(row, msgs, replayed=False):
        if not row:
            return {"status": "not_started"}
        out, number = [], 0
        for m in msgs:
            item = {"id": m["id"], "role": m["role"], "text": m["text"]}
            if m["role"] == "assistant":
                number += 1
                item["number"] = number
            out.append(item)
        current = next(({"id": m["id"], "text": m["text"], "number": m["number"]} for m in out if m["id"] == row["current_question_id"]), None)
        profile = None
        if row["draft"]:
            meta = json.loads(row["draft_meta"])
            profile = {"status": row["status"], "draft": json.loads(row["draft"]), "missing_fields": meta["missing_fields"],
                       "reason": meta["reason"], "model": meta["model"], "confirmed_at": row["confirmed_at"]}
        return {"status": row["status"], "version": row["version"], "asked_count": number, "max_questions": MAX_QUESTIONS,
                "age_band": row["age_band"], "stage": row["stage"], "messages": out, "current_question": current,
                "profile": profile, "source": json.loads(row["source"]), "replayed": replayed,
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def details(row):
        return {"status": row["status"], "current_version": row["version"]}

    def replayed(con, user, request_id, fp):
        row = con.execute("SELECT fingerprint FROM core_interview_requests WHERE user_id=? AND request_id=?", (user, request_id)).fetchone()
        if row and row["fingerprint"] != fp:
            raise problem(409, "request_id_reused", "这个请求编号已经用于另一项操作，请换一个新的编号。")
        return bool(row)

    def require(row, version, status="asking"):
        if not row:
            raise problem(409, "interview_not_started", "还没有开始访谈。", {"status": "not_started", "current_version": None})
        if row["status"] != status:
            raise problem(409, "interview_closed", "访谈已经结束，不能再回答。", details(row))
        if row["version"] != version:
            raise problem(409, "version_conflict", "访谈已经更新，请刷新后再操作。", details(row))

    def model_turn(user, request, version):
        with busy_lock:
            if user in busy:
                raise problem(409, "interview_busy", "上一次操作还在处理中，请稍后刷新。", {"retryable": True, "current_version": version})
            busy.add(user)
        try:
            return next_turn(request, runner)
        except InterviewError as exc:
            raise problem(exc.status, exc.code, exc.message, {"retryable": exc.retryable, "current_version": version}) from None
        finally:
            with busy_lock:
                busy.discard(user)

    def store(con, user, seq, answer, result, ts):
        if answer is not None:
            con.execute("INSERT INTO core_interview_messages(user_id,seq,id,role,text,created_at) VALUES(?,?,?,?,?,?)", (user, seq, f"u{seq}", "user", answer, ts))
            seq += 1
        source = json.dumps({"kind": "model", "model": result["model"]} if result["model"] else {"kind": "no_answers", "model": None}, ensure_ascii=False)
        if result["type"] == "ask":
            con.execute("INSERT INTO core_interview_messages(user_id,seq,id,role,text,purpose,dimension,model_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (user, seq, f"q{seq}", "assistant", result["question"], result["purpose"], result["dimension"], result["model"], ts))
            con.execute("UPDATE core_interviews SET status='asking',current_question_id=?,source=?,updated_at=? WHERE user_id=?", (f"q{seq}", source, ts, user))
        else:
            meta = json.dumps({"missing_fields": result["missing_fields"], "reason": result["reason"], "model": result["model"]}, ensure_ascii=False)
            con.execute("UPDATE core_interviews SET status='pending_confirmation',current_question_id=NULL,draft=?,draft_meta=?,source=?,updated_at=? WHERE user_id=?",
                        (json.dumps(result["draft"], ensure_ascii=False), meta, source, ts, user))

    def commit_turn(user, kind, request_id, fp, version, expected_question, answer, result):
        with db(True) as con:
            row, msgs = load(con, user)
            if replayed(con, user, request_id, fp):
                return view(row, msgs, True)
            if row["status"] != "asking" or row["version"] != version or row["current_question_id"] != expected_question:
                raise problem(409, "version_conflict", "访谈已经被另一次提交更新，本次结果没有保存，请刷新。", details(row))
            ts = now()
            store(con, user, len(msgs) + 1, answer, result, ts)
            con.execute("UPDATE core_interviews SET version=version+1 WHERE user_id=?", (user,))
            con.execute("INSERT INTO core_interview_requests(user_id,request_id,kind,fingerprint,version_after,created_at) VALUES(?,?,?,?,?,?)",
                        (user, request_id, kind, fp, version + 1, ts))
            return view(*load(con, user))

    def history(row, msgs):
        return {"age_band": row["age_band"], "stage": row["stage"], "messages": [{"id": m["id"], "role": m["role"], "text": m["text"]} for m in msgs],
                "asked_count": sum(m["role"] == "assistant" for m in msgs)}

    @api.get("/api/core/interview")
    def interview_state(authorization: str = Header(default="")):
        with db() as con:
            return view(*load(con, owner(con, authorization)))

    @api.post("/api/core/interview/start")
    def interview_start(body: dict, authorization: str = Header(default="")):
        fields(body, {"age_band", "stage"})
        age, stage = body.get("age_band") or "undisclosed", body.get("stage") or "undisclosed"
        if age not in AGE_BANDS or stage not in STAGES:
            raise problem(422, "invalid_input", "年龄段或当前阶段不在给定选项中；也可以不填。")
        with db() as con:
            user = owner(con, authorization)
            row, _ = load(con, user)
        if row:
            raise problem(409, "interview_exists", "访谈已经开始，不能重新开始；请读取当前状态继续。", details(row))
        result = model_turn(user, {"age_band": age, "stage": stage, "messages": [], "asked_count": 0}, None)
        with db(True) as con:
            row, _ = load(con, user)
            if row:
                raise problem(409, "interview_exists", "访谈已经开始，不能重新开始；请读取当前状态继续。", details(row))
            ts = now()
            con.execute("INSERT INTO core_interviews(user_id,age_band,stage,status,version,source,created_at,updated_at) VALUES(?,?,?,?,1,?,?,?)",
                        (user, age, stage, "asking", "{}", ts, ts))
            store(con, user, 1, None, result, ts)
            return view(*load(con, user))

    @api.post("/api/core/interview/answer")
    def interview_answer(body: dict, authorization: str = Header(default="")):
        fields(body, {"version", "question_id", "request_id", "text"}, ("version", "question_id", "request_id", "text"))
        version, request_id, question_id, text = version_of(body), request_id_of(body), body["question_id"], body["text"]
        if not isinstance(question_id, str) or not isinstance(text, str) or CONTROL.search(text):
            raise problem(422, "invalid_input", "question_id和回答必须是文字，且不能含控制字符。")
        text = text.strip()
        if not text:
            raise problem(422, "empty_answer", "回答是空的，没有计入新问题；说“不知道”或“跳过”也可以。")
        if len(text) > MAX_USER_TEXT:
            raise problem(422, "text_too_long", f"回答最多{MAX_USER_TEXT}字。")
        fp = fingerprint("answer", {"version": version, "question_id": question_id, "text": text})
        with db() as con:
            user = owner(con, authorization)
            row, msgs = load(con, user)
            if row and replayed(con, user, request_id, fp):
                return view(row, msgs, True)
            require(row, version)
            if row["current_question_id"] != question_id:
                raise problem(409, "stale_question", "这个问题已经回答过或不是当前问题，请刷新。", details(row))
        clean = scrub(text)
        request = history(row, msgs)
        request["messages"].append({"id": f"u{len(msgs) + 1}", "role": "user", "text": clean})
        result = model_turn(user, request, version)
        return commit_turn(user, "answer", request_id, fp, version, question_id, clean, result)

    @api.post("/api/core/interview/finish")
    def interview_finish(body: dict, authorization: str = Header(default="")):
        fields(body, {"version", "request_id"}, ("version", "request_id"))
        version, request_id = version_of(body), request_id_of(body)
        fp = fingerprint("finish", {"version": version})
        with db() as con:
            user = owner(con, authorization)
            row, msgs = load(con, user)
            if row and replayed(con, user, request_id, fp):
                return view(row, msgs, True)
            require(row, version)
        result = model_turn(user, {**history(row, msgs), "finish": True}, version)
        return commit_turn(user, "finish", request_id, fp, version, row["current_question_id"], None, result)

    @api.post("/api/core/interview/confirm")
    def interview_confirm(body: dict, authorization: str = Header(default="")):
        fields(body, {"version", "request_id"}, ("version", "request_id"))
        version, request_id = version_of(body), request_id_of(body)
        fp = fingerprint("confirm", {"version": version})
        with db(True) as con:
            user = owner(con, authorization)
            row, msgs = load(con, user)
            if row and replayed(con, user, request_id, fp):
                return view(row, msgs, True)
            if not row or row["status"] == "asking":
                raise problem(409, "no_draft", "还没有待确认的画像草稿。", details(row) if row else {"status": "not_started", "current_version": None})
            if row["status"] == "confirmed":
                raise problem(409, "already_confirmed", "画像已经确认过了。", details(row))
            if row["version"] != version:
                raise problem(409, "version_conflict", "草稿已经更新，请刷新后确认最新版本。", details(row))
            ts = now()
            con.execute("UPDATE core_interviews SET status='confirmed',confirmed_at=?,version=version+1,updated_at=? WHERE user_id=?", (ts, ts, user))
            con.execute("INSERT INTO core_interview_requests(user_id,request_id,kind,fingerprint,version_after,created_at) VALUES(?,?,?,?,?,?)",
                        (user, request_id, "confirm", fp, version + 1, ts))
            return view(*load(con, user))
