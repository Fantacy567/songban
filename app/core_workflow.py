"""Read-only collaboration guidance, adapted to Songban's confirmed-plan loop.

Inspired by hackathon-field-guide's home-next and space-workflow concepts.
No model calls, fabricated progress, or second editable task list.
"""
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS core_task_checks (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 squad_id TEXT NOT NULL, plan_version INTEGER NOT NULL, task_key TEXT NOT NULL,
 report_id TEXT NOT NULL, reviewer_id TEXT NOT NULL, verdict TEXT NOT NULL,
 note TEXT NOT NULL, created_at TEXT NOT NULL, dependency_reports TEXT NOT NULL DEFAULT '{}',
 UNIQUE(squad_id,plan_version,task_key,report_id)
);
CREATE INDEX IF NOT EXISTS core_task_checks_team ON core_task_checks(squad_id,plan_version);
"""


def enrich_handoffs(tasks):
    by_key = {t['key']: t for t in tasks}
    def resolve(task):
        if 'handoff_state' in task:
            return task['handoff_state']
        waiting = [key for key in task.get('depends_on', []) if key not in by_key or resolve(by_key[key]) != 'accepted']
        check = task.get('handoff')
        state = (check['verdict'] if check else 'waiting_review') if task['status'] == 'reported_done' else 'not_reported'
        changed = check and any(check.get('dependency_reports', {}).get(key) != by_key.get(key, {}).get('latest_report_id') for key in task.get('depends_on', []))
        if state == 'accepted' and (waiting or changed):
            state = 'dependency_changed'
        task['handoff_state'], task['waiting_on'] = state, waiting
        return state
    for task in tasks:
        resolve(task)


def build_workflow(snap, current_time):
    direction = snap['direction']
    tasks = snap['active_plan'].get('tasks', [])
    mine = [t for t in tasks if t['owner_id'] == snap['me']['id']]
    waiting = [t for t in tasks if t['handoff_state'] == 'waiting_review' and not t['waiting_on'] and t['owner_id'] != snap['me']['id']]
    accepted = [t for t in tasks if t['handoff_state'] == 'accepted']
    own_blocked = [t for t in mine if t['status'] == 'blocked']
    own_changes = [t for t in mine if t['handoff_state'] in ('changes_requested','dependency_changed')]
    started = [t for t in mine if t['status'] == 'in_progress']
    available = [t for t in mine if not t['waiting_on'] and t['status'] == 'todo']
    proposal = snap.get('proposal')

    def action(kind, title, reason, page='overview', task_key=''):
        return {'kind': kind, 'title': title, 'reason': reason, 'page': page, 'task_key': task_key}

    if not direction.get('goal', '').strip():
        next_action = action('direction', '先写清这次必须做出什么', '共同目标还是空的，先让所有个人智能体获得相同的工作边界。', 'direction')
    elif not direction.get('rules', '').strip():
        next_action = action('rules', '补上这场比赛的要求', '还没有主办方原文，不能判断必交材料。先粘贴已确认的内容，未知项如实保留。', 'direction')
    elif waiting:
        task = waiting[0]
        next_action = action('check', '先检查队友交来的「' + task['title'] + '」', '按检查方法试用成果，留下通过或需补充的原因，帮助后续任务解除等待。', task_key=task['key'])
    elif own_blocked:
        task = own_blocked[0]
        next_action = action('unblock', '先解开「' + task['title'] + '」的阻塞', '回到个人工具说明缺什么、需要谁配合；补充新进展后再统筹。', task_key=task['key'])
    elif own_changes:
        task = own_changes[0]
        next_action = action('revise', '补齐「' + task['title'] + '」再交接', '前置成果发生变化，请重新核对并同步新报告，原检查记录保留供追溯。' if task['handoff_state']=='dependency_changed' else task['handoff']['note'], task_key=task['key'])
    elif not snap['plan_version']:
        if snap['me']['captain'] and proposal and not proposal['stale']:
            next_action = action('confirm', '核对草案，再确认分工', '重点看负责人、前置成果、检查方法和取舍；草案尚未成为正式任务。')
        elif snap['me']['captain']:
            next_action = action('review', '把当前资料交给团队智能体统筹', '先同步重要进展，再点击综合当前信息。模型调用可能产生费用，需要你主动操作。')
        else:
            next_action = action('await_plan', '同步你的工作情况，等待队长确认安排', '可以先做技术验证或说明风险；个人建议不会自动发布成团队任务。', 'plugin')
    elif started:
        task = started[0]
        next_action = action('continue', '继续「' + task['title'] + '」', '完成后同步任务编号、当前计划版本和可核对的成果依据。', task_key=task['key'])
    elif available:
        task = available[0]
        next_action = action('start', '可以先做「' + task['title'] + '」', '它的前置成果已有检查记录，开始前仍需核对当前版本与检查方法。', task_key=task['key'])
    elif mine and any(t['waiting_on'] for t in mine):
        task = next(t for t in mine if t['waiting_on'])
        next_action = action('dependency', '先核对「' + task['title'] + '」的前置成果', '仍在等待：' + '、'.join(task['waiting_on']) + '。可并行准备的工作请按实际依赖判断。', task_key=task['key'])
    elif mine and any(t['handoff_state'] == 'waiting_review' for t in mine):
        next_action = action('await_check', '成果已报告，等待另一成员检查', '本人报告完成与同伴检查通过是两件事；新修改后请重新同步成果。')
    elif tasks and len(accepted) == len(tasks):
        next_action = action('delivery', '核对本次交接与正式提交要求', '当前任务已有同伴检查记录；代码版本、演示文件和主办方回执仍需分别核对。')
    elif not tasks:
        next_action = action('empty_plan', '核对当前安排里还缺哪些任务', '正式任务列表为空，不代表作品已经完成。队长需要时可重新统筹。')
    else:
        next_action = action('team', '看看队友还缺什么配合', '你目前没有可开始的本人任务。先看团队进展，再由队长确认新增安排。')

    checks = [
        {'key': 'goal', 'title': '共同目标', 'state': 'recorded' if direction.get('goal') else 'missing', 'detail': '已保存团队目标。' if direction.get('goal') else '尚未填写共同目标。', 'page': 'direction'},
        {'key': 'rules', 'title': '赛事要求与评分', 'state': 'recorded' if direction.get('rules') and direction.get('rubric') else 'missing', 'detail': '已保存原文和评分依据，内容仍需对照主办方核实。' if direction.get('rules') and direction.get('rubric') else '缺少赛事原文或评分依据；不能由AI补造。', 'page': 'direction'},
        {'key': 'plan', 'title': '已确认安排', 'state': 'recorded' if snap['plan_version'] and tasks else 'missing', 'detail': f"当前安排 v{snap['plan_version']}，共 {len(tasks)} 项任务；空安排不代表完成。", 'page': 'overview'},
        {'key': 'handoffs', 'title': '成果交接检查', 'state': 'recorded' if tasks and len(accepted) == len(tasks) else 'attention', 'detail': f'{len(tasks)} 项任务中，{len(accepted)} 项的当前成果有同伴检查通过记录。', 'page': 'overview'},
        {'key': 'runtime', 'title': '演示与文件能否使用', 'state': 'manual', 'detail': '用准备提交的实际版本走一遍演示，检查PPT、视频与访问权限；任务检查不能证明现场环境已就绪。', 'page': 'overview'},
        {'key': 'submission', 'title': '主办方正式收件', 'state': 'unknown', 'detail': '松伴没有读取主办方收件状态。请到正式入口提交并保存真实回执。', 'page': 'direction'},
    ]
    deadline = {'state': 'unknown', 'text': '未提供可核对的截止时间。', 'hours_left': None, 'advice': '先填写实际截止；暂不判断是否来得及。'}
    try:
        end = datetime.fromisoformat(direction.get('deadline', '').replace('Z', '+00:00'))
        current = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
        if end.tzinfo is None or current.tzinfo is None:
            raise ValueError()
        hours = (end.astimezone(timezone.utc) - current.astimezone(timezone.utc)).total_seconds() / 3600
        pending = len(tasks) - len(accepted)
        state = 'past_due' if hours <= 0 else 'soon' if hours < 2 else 'known'
        deadline = {'state': state, 'text': '已到填写的截止时间。' if hours <= 0 else f'距填写的截止约 {hours:.1f} 小时。', 'hours_left': round(hours, 2), 'advice': ('先核对平台收件状态与可补交规则，不继续把未知结果当作已提交。' if hours <= 0 else f'还有 {pending} 项当前成果未检查通过。保住共同目标里的最小演示，留时间核对文件与回执。' if hours < 2 else '剩余时间不代表一定能完成；按实际依赖并行推进，预留演示与提交缓冲。')}
    except (ValueError, TypeError, AttributeError):
        pass
    return {'next_action': next_action, 'my_tasks': mine, 'reviewable_tasks': [t['key'] for t in waiting], 'checks': checks, 'deadline': deadline, 'accepted_tasks': len(accepted), 'total_tasks': len(tasks), 'all_handoffs_checked': bool(tasks) and len(accepted) == len(tasks), 'source_label': '依据当前记录生成的操作指引 · 不调用模型', 'notice': '交接检查只对应当前任务、计划版本和成果报告；不等于正式提交、获奖或独立技术认证。'}


def handoff_markdown(snap):
    names = {m['id']: m['name'] for m in snap['members']}
    lines = ['# ' + snap['team']['name'] + ' · 交接核对清单', '', '计划版本：v' + str(snap['plan_version']), '', '## 共同目标', snap['direction'].get('goal') or '尚未填写', '', '## 任务与当前成果']
    for task in snap['active_plan'].get('tasks', []):
        check = task.get('handoff')
        lines += ['', '### ' + task['key'] + ' ' + task['title'], '负责人：' + names.get(task['owner_id'], '未知成员'), '检查方法：' + task['acceptance'], '交接状态：' + {'accepted': '同伴检查通过', 'changes_requested': '需要补充', 'waiting_review': '等待同伴检查', 'not_reported': '尚未报告完成','dependency_changed':'前置成果变化，需重新核对'}[task['handoff_state']]]
        if task.get('latest_progress'):
            lines += ['本人报告：' + task['latest_progress']['summary'], '成员提供的依据：'] + ['- ' + x for x in task['latest_progress']['evidence']]
        if check:
            lines += ['检查人：' + names.get(check['reviewer_id'], '未知成员'), '检查说明：' + check['note'], '对应报告：' + check['report_id'], '检查记录：' + check['id']]
    lines += ['', '## 提交前仍需核对']
    lines += ['- ' + c['title'] + '：' + c['detail'] for c in snap['workflow']['checks']]
    lines += ['', snap['workflow']['notice']]
    return '\n'.join(lines) + '\n'
