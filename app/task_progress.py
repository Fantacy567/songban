"""Read-only member progress from the current confirmed plan and its latest reports."""


def member_task_progress(members, tasks):
    result = []
    for member in members:
        owned = [task for task in tasks if task['owner_id'] == member['id']]
        done = [task for task in owned if task['status'] == 'reported_done' and task['handoff_state'] in ('waiting_review', 'accepted')]
        accepted = sum(task['handoff_state'] == 'accepted' for task in owned)
        active = sorted((task for task in owned if task['status'] in ('in_progress', 'blocked') or task['handoff_state'] in ('changes_requested', 'dependency_changed')), key=lambda task: task.get('latest_report_seq', 0), reverse=True)
        current = active[0] if active else None
        if current:
            kind = 'changes_requested' if current['handoff_state'] in ('changes_requested', 'dependency_changed') else current['status']
            current_info = {'key': current['key'], 'title': current['title'], 'kind': kind}
        else:
            next_task = next((task for task in owned if task not in done and not task.get('waiting_on')), None)
            pending = next((task for task in done if task['handoff_state'] == 'waiting_review'), None)
            task = next_task or pending
            current_info = {'key': task['key'], 'title': task['title'], 'kind': 'next' if next_task else 'waiting_review'} if task else None
        total = len(owned)
        result.append({'user_id': member['id'], 'name': member['name'], 'total': total, 'completed': len(done), 'accepted': accepted, 'percent': len(done) * 100 // total if total else 0, 'current_task': current_info, 'all_waiting': bool(total and not current_info and len(done) < total)})
    return result
