"""Offline rubric check and time-pressure suggestions. Not a language model."""
import re
from datetime import datetime

LABEL = "离线规则 · 按赛规原文里的交付物名称对照任务，非大模型"

# A sentence is a criterion when it talks about scoring or what must be handed in.
CRITERION = re.compile(r"评分|得分|加分|提交|材料|演示|答辩|路演|作品|仓库|文档|接口|页面|视频")
SPLIT = re.compile(r"[。；;]+")
# Longer phrases first so「需求文档」不会被拆成单独的「文档」。
ANCHORS = (
    "演示视频",
    "项目说明",
    "说明文档",
    "需求文档",
    "业务流程图",
    "提交入口",
    "仓库链接",
    "演示文稿",
    "接口文档",
    "交接文档",
    "操作页面",
    "协作页面",
    "截图",
    "海报",
    "仓库",
    "视频",
    "答辩",
    "路演",
    "原型",
    "接口",
    "页面",
    "文档",
    "ppt",
)


def _pieces(body):
    found = []
    for line in body.splitlines():
        for part in SPLIT.split(line):
            text = part.strip(" \t，,、")
            if 6 <= len(text) <= 300 and CRITERION.search(text) and text in body and text not in found:
                found.append(text)
                if len(found) >= 12:
                    return found
    return found


def anchors_in(text):
    """Non-overlapping delivery names, longest first, original spelling kept."""
    folded = text.lower()
    if len(folded) != len(text):
        folded = text
    occupied = [False] * len(folded)
    found = []
    for word in sorted(ANCHORS, key=len, reverse=True):
        needle = word.lower() if folded is not text else word
        start = 0
        while True:
            index = folded.find(needle, start)
            if index < 0:
                break
            end = index + len(needle)
            if not any(occupied[index:end]):
                occupied[index:end] = [True] * (end - index)
                found.append(text[index:end])
            start = end
    return found


def _blob(task):
    return "\n".join(str(task.get(key) or "") for key in ("title", "acceptance", "deliverable")).lower()


def rubric_coverage(rules_sources, tasks):
    """Match rule sentences to tasks. Does not change tasks or decide the project is ready."""
    items = []
    for source in rules_sources:
        if source.get("kind") not in (None, "rules"):
            continue
        for quote in _pieces(source.get("body") or ""):
            needed = anchors_in(quote)
            if not needed:
                items.append({
                    "quote": quote,
                    "source_id": source.get("id"),
                    "status": "manual",
                    "task_id": None,
                    "task_title": None,
                    "gap": "这条没有写明演示视频、文档、接口、页面这类交付物名称，请人工对照原文。",
                })
                continue
            hits, waiting, missing_names = [], [], []
            for name in needed:
                needle = name.lower()
                matches = [task for task in tasks if needle in _blob(task)]
                accepted = [task for task in matches if task.get("status") == "accepted"]
                if accepted:
                    hits.append(accepted[0])
                elif matches:
                    hits.append(matches[0])
                    waiting.append(matches[0])
                else:
                    missing_names.append(name)
            if missing_names:
                status, chosen = "missing", None
                gap = "还没有任务标题、验收标准或成果说明写到：" + "、".join(missing_names) + "。"
            elif waiting:
                status, chosen, gap = "pending", waiting[0], ""
            else:
                status, chosen, gap = "covered", hits[0], ""
            items.append({
                "quote": quote,
                "source_id": source.get("id"),
                "status": status,
                "task_id": chosen.get("id") if chosen else None,
                "task_title": chosen.get("title") if chosen else None,
                "gap": gap,
            })
    summary = {name: sum(item["status"] == name for item in items) for name in ("covered", "pending", "missing", "manual")}
    summary["total"] = len(items)
    if not items:
        note = "赛规里没有识别到评分、提交、演示、文档、接口或页面相关的句子。请人工对照原文。"
    elif summary["missing"]:
        note = "有条款还没有对应成果。对照只看名称是否出现，不能代替打开提交入口检查文件。"
    elif summary["pending"] or summary["manual"]:
        note = "还有条款在等验收，或需要人工判断。必须任务全部通过，也不等于这些条款都已交齐。"
    else:
        note = "识别到的交付物名称都出现在已验收任务里。请再打开提交入口，确认文件真的交了。"
    return {"source_label": LABEL, "items": items, "summary": summary, "note": note}


def scope_advice(deadline, current, tasks):
    """Suggest what to drop or narrow. Never edits the task list."""
    if not tasks:
        return {
            "source_label": LABEL,
            "applicable": False,
            "tight": False,
            "remaining_hours": None,
            "unfinished_must_hours": 0.0,
            "optional_hours": 0.0,
            "drop": [],
            "narrow": [],
            "note": "确认分工之后，这里会按剩余时间给出砍范围建议。建议不会改动已确认的任务。",
        }
    end, start = datetime.fromisoformat(deadline), datetime.fromisoformat(current)
    if (end.tzinfo is None) != (start.tzinfo is None):
        end, start = end.replace(tzinfo=None), start.replace(tzinfo=None)
    remaining = round(max(0.0, (end - start).total_seconds() / 3600), 2)
    open_tasks = [task for task in tasks if task.get("status") != "accepted"]
    must = [task for task in open_tasks if task.get("priority") == "must"]
    optional = [task for task in open_tasks if task.get("priority") != "must"]
    must_hours = round(sum(float(task["estimated_hours"]) for task in must), 2)
    optional_hours = round(sum(float(task["estimated_hours"]) for task in optional), 2)
    tight = must_hours > remaining + 1e-8

    def brief(task):
        return {"task_key": task.get("task_key") or task.get("key") or "", "title": task.get("title") or "", "estimated_hours": float(task["estimated_hours"])}

    drop = [brief(task) for task in sorted(optional, key=lambda task: -float(task["estimated_hours"]))]
    narrow = [brief(task) for task in sorted(must, key=lambda task: -float(task["estimated_hours"]))[:2]] if tight else []
    if tight and drop:
        note = "未完成的必须任务估时已经超过剩余时间。建议先不做下面的可选项，并把估时最大的必须任务收窄到能演示的一步。确认后的任务不会被自动修改，请团队约定后再做。"
    elif tight:
        note = "未完成的必须任务估时已经超过剩余时间，而且没有可选项可以先不做。请把估时最大的必须任务收窄到能演示的一步。确认后的任务不会被自动修改。"
    else:
        note = "按估时，剩余时间还够完成未完成的必须任务。可选项留到必须任务验收之后。此建议不会改动已确认的任务。"
    return {
        "source_label": LABEL,
        "applicable": True,
        "tight": tight,
        "remaining_hours": remaining,
        "unfinished_must_hours": must_hours,
        "optional_hours": optional_hours,
        "drop": drop if tight else [],
        "narrow": narrow,
        "note": note,
    }


def advice_markdown(rubric, scope):
    status = {"covered": "已覆盖", "pending": "未验收", "missing": "未覆盖", "manual": "人工核对"}
    lines = ["", "## 赛规对照", rubric["source_label"], rubric["note"]]
    if not rubric["items"]:
        lines.append("- （没有识别到评分或提交条款）")
    for item in rubric["items"]:
        extra = f"；对应 {item['task_title']}" if item.get("task_title") else ""
        gap = f"；{item['gap']}" if item.get("gap") else ""
        lines.append(f"- [{status[item['status']]}] {item['quote']}{extra}{gap}")
    if scope.get("applicable"):
        lines.extend([
            "",
            "## 时间与范围",
            scope["source_label"],
            scope["note"],
            f"- 剩余约 {scope['remaining_hours']} 小时，未完成必须任务约 {scope['unfinished_must_hours']} 小时",
        ])
        if scope["drop"]:
            lines.append("- 建议先不做：" + "、".join(f"{task['task_key']} {task['title']}" for task in scope["drop"]))
        if scope["narrow"]:
            lines.append("- 建议先收窄：" + "、".join(f"{task['task_key']} {task['title']}" for task in scope["narrow"]))
    return lines
