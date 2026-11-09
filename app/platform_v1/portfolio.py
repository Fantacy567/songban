"""Private portfolio projections; original learning/competition facts stay authoritative.

The central router supplies a currently authenticated LearningV2 session and its
same-database transaction. This module never authenticates bearer credentials,
grants consent, calls a model, publishes work or advances a course/competition.
"""
import hashlib
import json
import secrets

from app.learning_v2.protocol import Problem, canonical, fail, revision
from app.topic_selection import claimed_owner

from .schemas import READ_OPS, WRITE_OPS, external_url, validate_request
from .storage import migrate_portfolio


def ident(prefix):
    return prefix + secrets.token_hex(16)


def text_output(label, text):
    return {"kind": "text", "label": label, "text": text, "url": None}


def link_output(label, url):
    return {"kind": "external_link", "label": label, "text": None, "url": url}


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def absent():
    fail(404, "resource_not_found", "找不到可访问的作品或来源。")


class PortfolioService:
    def __init__(self, learning):
        self.learning = learning
        self.store = learning.store
        self.creative_studio = None

    def migrate(self):
        migrate_portfolio(self.store, self.learning.stamp())

    @staticmethod
    def _has_table(con, name):
        return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())

    def _parent_summary(self, con, lid):
        scopes = set()
        for row in con.execute("SELECT * FROM learn_consents WHERE learner_id=?", (lid,)):
            scopes.update(self.learning.effective(con, row))
        if not {"learning", "parent_summary"} <= scopes:
            fail(403, "consent_required", "有效学习及家长摘要授权尚未建立或已经撤回。")

    def _access(self, con, session, lid, *roles):
        self.learning.role(session, *(roles or ("learner", "manager")))
        self.learning.learner(con, session, lid)
        self.learning.learning_access(con, lid)
        if session["mode"] == "manager":
            self._parent_summary(con, lid)

    def _external_row(self, con, lid, wid):
        row = con.execute("SELECT * FROM platform_external_works WHERE id=? AND learner_id=?", (wid, lid)).fetchone()
        if not row:
            absent()
        return row

    def _project(self, con, pid, actor):
        if not all(self._has_table(con, name) for name in ("squads", "squad_members", "core_settings")):
            fail(403, "source_account_mismatch", "当前认证账号没有可关联的比赛项目。")
        row = con.execute("""SELECT s.id,s.name,c.revision,c.plan_version,c.active_plan
            FROM squads s JOIN squad_members m ON m.squad_id=s.id
            JOIN core_settings c ON c.squad_id=s.id
            WHERE s.id=? AND m.user_id=?""", (pid, actor)).fetchone()
        if not row:
            fail(403, "source_account_mismatch", "只能选择当前实际认证账号所属的比赛项目。")
        return row

    def _source_previews(self, con, project, actor):
        """Only this member's bounded report facts/tasks; never full team snapshot."""
        values = []
        if self._has_table(con, "core_reports"):
            for row in con.execute("SELECT id,body FROM core_reports WHERE squad_id=? AND user_id=? ORDER BY seq DESC LIMIT 80", (project["id"], actor)):
                body = json.loads(row["body"])
                summary = body.get("summary", "")
                if not isinstance(summary, str):
                    continue
                outputs = [text_output("本人进展（自报，未独立核实）", summary[:3500])]
                evidence_list = body.get("evidence", [])
                for evidence in evidence_list[:8] if isinstance(evidence_list, list) else []:
                    if not isinstance(evidence, str):
                        continue
                    try:
                        url = external_url(evidence)
                    except ValueError:
                        outputs.append(text_output("本人证据说明", evidence[:1000]))
                    else:
                        outputs.append(link_output("本人提供的产物链接（未独立核实）", url))
                values.append({"ref": "report:" + row["id"], "label": "本人进展", "text": summary[:3500], "outputs": outputs})
        plan = json.loads(project["active_plan"])
        for task in plan.get("tasks", [])[:100]:
            if not isinstance(task, dict) or not isinstance(task.get("key"), str):
                continue
            if task.get("claim_required") and not self._has_table(con, "core_task_claims"):
                continue
            if claimed_owner(con, project["id"], project["plan_version"], task) != actor:
                continue
            title = str(task.get("title", task["key"]))[:300]
            description = str(task.get("description", ""))[:1600]
            label = title + ("\n" + description if description else "")
            values.append({"ref": f"task:{project['plan_version']}:{task['key']}", "label": "本人任务（不代表已完成）", "text": label,
                           "outputs": [text_output("本人任务安排（不代表已完成）", label)]})
        return values

    def _snapshot(self, con, project, actor, refs):
        available = {value["ref"]: value for value in self._source_previews(con, project, actor)}
        if any(ref not in available for ref in refs):
            fail(409, "source_changed", "所选本人来源已变化或不再可访问，请重新核对。", "reload")
        return {"project_name": project["name"], "sources": [available[ref] for ref in refs]}

    def _link_row(self, con, session, lid, link_id):
        row = con.execute("SELECT * FROM platform_competition_links WHERE id=? AND learner_id=?", (link_id, lid)).fetchone()
        if not row:
            absent()
        self._parent_summary(con, lid)
        owner = con.execute("""SELECT f.owner_id FROM learn_learners l
            JOIN learn_families f ON f.id=l.family_id WHERE l.id=?""", (lid,)).fetchone()
        if not owner or owner[0] != row["source_actor_id"]:
            absent()
        try:
            self._project(con, row["project_id"], row["source_actor_id"])
        except Problem as exc:
            if exc.code == "source_account_mismatch":
                absent()
            raise
        # A removed report cannot remain visible through a cached source copy.
        body = json.loads(row["body"])
        for ref in body["selected_refs"]:
            if ref.startswith("report:"):
                if not self._has_table(con, "core_reports") or not con.execute(
                        "SELECT 1 FROM core_reports WHERE id=? AND squad_id=? AND user_id=?",
                        (ref[7:], row["project_id"], row["source_actor_id"])).fetchone():
                    absent()
        return row

    def authorize(self, con, op, session, params, body=None):
        """Central MUST call before idempotency replay; each operation also checks."""
        if op not in READ_OPS | WRITE_OPS:
            raise ValueError("Unknown portfolio operation")
        lid = params["learner_id"]
        roles = ("manager",) if op in ("competitionSources", "createCompetitionLink") else ("learner",) if op in (
            "createExternalWork", "versionExternalWork", "decideCompetitionLink") else ("learner", "manager")
        self._access(con, session, lid, *roles)
        if op in WRITE_OPS:
            b = validate_request(op, body)
            if op == "versionExternalWork":
                self._external_row(con, lid, params["work_id"])
            elif op == "createCompetitionLink":
                self._parent_summary(con, lid)
                self._project(con, b["project_id"], session["actor_id"])
            elif op == "decideCompetitionLink":
                self._link_row(con, session, lid, params["link_id"])

    def replay(self, con, op, session, params, body, cached_result):
        """Return a currently authorized projection, never the cached old state.

        The shared router already checked request fingerprint. Replaying a
        receipt must not repeat its action or revive a withdrawn association.
        """
        self.authorize(con, op, session, params, body)
        lid = params["learner_id"]
        if op in ("createExternalWork", "versionExternalWork"):
            return self.read(con, "work", session, {"learner_id": lid, "work_id": cached_result["id"]}, {})
        if op in ("createCompetitionLink", "decideCompetitionLink"):
            return self._link_view(self._link_row(con, session, lid, cached_result["id"]))
        raise ValueError("Not a replayable portfolio operation")

    def _base(self, lid, wid, origin, title, summary, rev, source_id, source_version,
              version_id, number, outputs, contribution, provenance, updated_at, actions):
        return {"id": wid, "learner_id": lid, "origin": origin, "title": title, "summary": summary,
                "revision": rev, "source_ref": {"domain": origin, "id": source_id, "version": str(source_version)},
                "current_version": {"id": version_id, "number": number}, "actual_outputs": outputs,
                "cover_asset_id": None, "contribution": contribution, "provenance": provenance,
                "visibility": "private", "updated_at": updated_at, "available_actions": actions}

    @staticmethod
    def _card_outputs(version):
        labels = {"title": "标题", "audience": "邀请谁", "date": "日期", "start_time": "开始时间", "end_time": "结束时间",
                  "time": "时间", "place": "地点", "preparation": "准备", "invitation_line": "邀请语"}
        content = version["content"]
        text = "\n".join(f"{labels.get(key, key)}：{value}" for key, value in content.items())
        return [text_output("已保存邀请卡内容", text)]

    def _learning(self, con, session, lid, artifact_id, detail=False):
        artifact = self.learning.owned(con, session, artifact_id, "artifact")
        # owned checks the underlying resource; additionally bind the requested lid.
        if artifact["learner_id"] != lid:
            absent()
        current = artifact["current_version"]
        authorship = current["authorship"]
        ai = "generated" if authorship == "ai_candidate_unedited" else "assisted" if authorship == "ai_candidate_edited" else "unknown"
        outputs = self._card_outputs(current)
        value = self._base(lid, "learning_" + artifact_id, "learning", current["content"].get("title", "我的学习作品"),
                           "课程中保存的作品版本；学习检查结果以原课程记录为准。", artifact["revision"], artifact_id,
                           current["id"], current["id"], current["version"], outputs,
                           "依据原作品版本记录：" + authorship,
                           {"kind": "learning_record", "ai_assistance": ai, "source_label": "学习作品原始记录"},
                           artifact["saved_at"], ["open_learning"])
        if detail:
            versions = self.learning.objects(con, "version", lid=lid, run=artifact["run_id"])
            value["versions"] = [{"id": ver["id"], "number": ver["version"], "actual_outputs": self._card_outputs(ver), "created_at": ver["created_at"]}
                                 for ver in versions if ver["artifact_id"] == artifact_id]
        return value

    def _external(self, con, session, row, detail=False):
        versions = con.execute("SELECT * FROM platform_external_versions WHERE work_id=? ORDER BY number", (row["id"],)).fetchall()
        current = versions[-1]
        body = json.loads(current["body"])
        outputs = [link_output("作品链接（本人提供，未独立核实）", body["url"])]
        value = self._base(row["learner_id"], row["id"], "external", body["title"], body["summary"], row["revision"],
                           row["id"], current["id"], current["id"], current["number"], outputs, body["contribution"],
                           {"kind": "self_reported", "ai_assistance": body["ai_assistance"], "source_label": body["tool_name"]},
                           row["updated_at"], ["save_version"] if session["mode"] == "learner" else [])
        if detail:
            value["versions"] = [{"id": ver["id"], "number": ver["number"], "actual_outputs": [link_output("作品链接（本人提供，未独立核实）", json.loads(ver["body"])["url"])], "created_at": ver["created_at"]} for ver in versions]
        return value

    @staticmethod
    def _link_view(row):
        body = json.loads(row["body"])
        return {"id": row["id"], "learner_id": row["learner_id"], "project_id": row["project_id"],
                "source_revision": row["source_revision"], "revision": row["revision"], "state": row["state"],
                "title": body["title"], "summary": body["summary"], "contribution": body["contribution"],
                "selected_refs": body["selected_refs"], "sources": body["snapshot"]["sources"],
                "source_label": body["snapshot"]["project_name"], "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def _competition(self, row, detail=False):
        body = json.loads(row["body"])
        outputs = [output for source in body["snapshot"]["sources"] for output in source["outputs"]]
        vid = f"{row['id']}:{row['revision']}"
        value = self._base(row["learner_id"], "competition_" + row["id"], "competition", body["title"], body["summary"],
                           row["revision"], row["project_id"], row["source_revision"], vid, row["revision"], outputs, body["contribution"],
                           {"kind": "guardian_statement_learner_confirmed", "ai_assistance": "unknown", "source_label": body["snapshot"]["project_name"]},
                           row["updated_at"], ["open_competition"])
        if detail:
            value["versions"] = [{"id": vid, "number": row["revision"], "actual_outputs": outputs, "created_at": row["updated_at"]}]
        return value

    def read(self, con, op, session, params, query):
        self.authorize(con, op, session, params)
        if query:
            fail(422, "invalid_input", "该作品操作不接受查询参数。")
        lid = params["learner_id"]
        if op == "competitionSources":
            if not all(self._has_table(con, name) for name in ("squads", "squad_members", "core_settings")):
                return {"items": []}
            items = []
            for row in con.execute("SELECT squad_id FROM squad_members WHERE user_id=? ORDER BY squad_id", (session["actor_id"],)):
                try:
                    project = self._project(con, row[0], session["actor_id"])
                except Problem as exc:
                    if exc.code == "source_account_mismatch":
                        continue
                    raise
                items.append({"project_id": project["id"], "name": project["name"], "source_revision": project["revision"],
                              "available_refs": self._source_previews(con, project, session["actor_id"])})
            return {"items": items}
        if op == "competitionLinks":
            self._parent_summary(con, lid)
            items = []
            for row in con.execute("SELECT id FROM platform_competition_links WHERE learner_id=? ORDER BY updated_at DESC,id", (lid,)):
                try:
                    items.append(self._link_view(self._link_row(con, session, lid, row["id"])))
                except Problem as exc:
                    if exc.status == 404:
                        continue
                    raise
            return {"items": items}
        if op == "work":
            wid = params["work_id"]
            if self.creative_studio is not None and wid.startswith('csa_'):
                return self.creative_studio.portfolio_work(con, session, lid, wid)
            if wid.startswith("learning_"):
                return self._learning(con, session, lid, wid[9:], detail=True)
            if wid.startswith("competition_"):
                row = self._link_row(con, session, lid, wid[12:])
                if row["state"] != "accepted":
                    absent()
                return self._competition(row, detail=True)
            return self._external(con, session, self._external_row(con, lid, wid), detail=True)
        if op == "works":
            items = []
            if self.creative_studio is not None:
                items.extend(self.creative_studio.portfolio_items(con, session, lid))
            if self._has_table(con, "learn_course_objects"):
                for row in con.execute("SELECT id FROM learn_course_objects WHERE kind='artifact' AND learner_id=?", (lid,)):
                    try:
                        items.append(self._learning(con, session, lid, row["id"]))
                    except Problem as exc:
                        if exc.status in (403, 404, 410):
                            continue
                        raise
            for row in con.execute("SELECT * FROM platform_external_works WHERE learner_id=?", (lid,)):
                items.append(self._external(con, session, row))
            try:
                self._parent_summary(con, lid)
            except Problem as exc:
                if exc.code != "consent_required":
                    raise
            else:
                for row in con.execute("SELECT id FROM platform_competition_links WHERE learner_id=? AND state='accepted'", (lid,)):
                    try:
                        items.append(self._competition(self._link_row(con, session, lid, row["id"])))
                    except Problem as exc:
                        if exc.status == 404:
                            continue
                        raise
            items.sort(key=lambda item: (item["updated_at"], item["id"]), reverse=True)
            return {"items": items, "next_cursor": None}
        raise ValueError("Not a portfolio read operation")

    def _record_link(self, con, row):
        con.execute("INSERT INTO platform_competition_link_history VALUES(?,?,?,?,?)", (row["id"], row["revision"], row["state"], row["body"], row["updated_at"]))

    def write(self, con, op, session, params, body):
        self.authorize(con, op, session, params, body)
        b = validate_request(op, body)
        lid, stamp = params["learner_id"], self.learning.stamp()
        if op in ("createExternalWork", "versionExternalWork"):
            if op == "createExternalWork":
                wid, number = ident("pw_"), 1
                con.execute("INSERT INTO platform_external_works VALUES(?,?,1,?,?)", (wid, lid, stamp, stamp))
            else:
                row = self._external_row(con, lid, params["work_id"])
                revision(b["expected_revision"], row["revision"])
                wid, number = row["id"], row["revision"] + 1
                con.execute("UPDATE platform_external_works SET revision=?,updated_at=? WHERE id=?", (number, stamp, wid))
            content = {key: b[key] for key in ("title", "summary", "url", "tool_name", "contribution", "ai_assistance")}
            con.execute("INSERT INTO platform_external_versions VALUES(?,?,?,?,?)", (ident("pwv_"), wid, number, canonical(content), stamp))
            return self._external(con, session, self._external_row(con, lid, wid), detail=True)
        if op == "createCompetitionLink":
            project = self._project(con, b["project_id"], session["actor_id"])
            if project["revision"] != b["expected_source_revision"]:
                fail(409, "source_changed", "比赛资料版本已变化，请重新选择本人来源。", "reload")
            snapshot = self._snapshot(con, project, session["actor_id"], b["selected_refs"])
            content = {key: b[key] for key in ("title", "summary", "contribution", "selected_refs")}
            content["snapshot"] = snapshot
            old = con.execute("SELECT * FROM platform_competition_links WHERE learner_id=? AND project_id=? AND source_actor_id=?", (lid, project["id"], session["actor_id"])).fetchone()
            if old and old["state"] in ("offered", "accepted"):
                fail(409, "source_link_exists", "本项目已有待确认或已接受来源，请先核对原记录。", "reload")
            link_id, rev = (old["id"], old["revision"] + 1) if old else (ident("pcl_"), 1)
            con.execute("""INSERT INTO platform_competition_links VALUES(?,?,?,?,?,?,?,'offered',?,?,?)
                ON CONFLICT(id) DO UPDATE SET source_revision=excluded.source_revision,source_hash=excluded.source_hash,
                revision=excluded.revision,state=excluded.state,body=excluded.body,updated_at=excluded.updated_at""",
                (link_id, lid, project["id"], session["actor_id"], project["revision"], fingerprint(snapshot), rev, canonical(content), old["created_at"] if old else stamp, stamp))
            row = self._link_row(con, session, lid, link_id)
            self._record_link(con, row)
            return self._link_view(row)
        if op == "decideCompetitionLink":
            row = self._link_row(con, session, lid, params["link_id"])
            revision(b["expected_revision"], row["revision"])
            allowed = {"accept": ("offered",), "decline": ("offered",), "revoke": ("offered", "accepted")}
            if row["state"] not in allowed[b["decision"]]:
                fail(409, "source_confirmation_required", "来源状态已变化，请核对当前记录。", "reload")
            if b["decision"] == "accept":
                project = self._project(con, row["project_id"], row["source_actor_id"])
                content = json.loads(row["body"])
                current = self._snapshot(con, project, row["source_actor_id"], content["selected_refs"])
                if project["revision"] != row["source_revision"] or fingerprint(current) != row["source_hash"]:
                    fail(409, "source_changed", "比赛来源在提议后发生变化，请家长重新核对。", "reload")
            state = {"accept": "accepted", "decline": "declined", "revoke": "revoked"}[b["decision"]]
            con.execute("UPDATE platform_competition_links SET state=?,revision=revision+1,updated_at=? WHERE id=?", (state, stamp, row["id"]))
            row = self._link_row(con, session, lid, row["id"])
            self._record_link(con, row)
            return self._link_view(row)
        raise ValueError("Not a portfolio write operation")
