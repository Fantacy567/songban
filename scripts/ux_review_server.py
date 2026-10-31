"""Independent user-journey review: real UI/SQLite, explicit SMS/model substitutes.

Starts with no users or teams. Reviewers must register and navigate in the UI.
Only writes beneath .browser-cache/ux-review; never touches the normal database.
"""
import argparse
import json
import os
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import create_app, now
from app.planner import PlannerError
from tests.test_materials import fixture_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--session', type=int, choices=range(1, 6), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    allowed = (ROOT / '.browser-cache' / 'ux-review').resolve()
    if not folder.is_relative_to(allowed) or args.port != 8900 + args.session:
        parser.error('Use an independent ux-review folder and port 8900 + session')
    folder.mkdir(parents=True, exist_ok=True)
    database = folder / 'review.sqlite3'
    if database.exists():
        parser.error('Choose a fresh folder; do not silently reuse review state')
    calls = []
    lock = threading.Lock()

    def record(kind, context):
        with lock:
            calls.append({'kind': kind, 'time': now(), 'selected_source_count': len(context.get('sources', []))})
            (folder / 'model-call-counts.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')

    def discuss(context):
        record('discussion', context)
        prompt = context['text']
        if '[UX_TIMEOUT]' in prompt:
            raise PlannerError('model_timeout', '体验测试模拟超时：结果未知，请核对保存状态。', 504)
        if '[UX_SLOW]' in prompt:
            time.sleep(5)
        if '[UX_FAIL]' in prompt:
            raise PlannerError('model_invalid_output', '体验测试模拟服务失败，输入已保留。', 502)
        role = context['role']['id']
        goal = (context.get('direction') or {}).get('goal') or '校园失物招领助手：让同学快速发布、查找和认领物品'
        sources = '、'.join(source['name'] for source in context['sources']) or '尚未选择材料'
        replies = {
            'materials': f'本轮材料：{sources}。先区分活动要求、自己的想法和仍待核实的信息。\n建议把目标用户、提交物、截止时间分别记下；没有原文依据的内容先列为问题，不补造规则。',
            'direction': f'可以从这个小目标开始：{goal}\n最小范围：发布一条失物信息、按类别查找、确认认领；先不做支付、复杂推荐和公开个人联系方式。\n需要确认：谁会先用、怎样验证需求、最终提交什么。你可以修改这份草稿，选择团队后由队长保存共同方向。',
            'next_step': '建议先整理一页项目说明，再准备一分钟演示。\n项目说明包含目标用户、核心问题、最小范围和三步使用流程；演示包含开场、操作顺序、限制与分工。\n把需要团队采用的结论显式共享，由队长在任务页发起统筹、核对后确认。完成后同步具体依据，并请另一位成员检查。',
        }
        return {'text': '【固定体验样例，非真实模型回答】\n' + replies[role],
                'requested_model': 'ux-review-sample', 'actual_model': 'ux-review-sample', 'mode': 'fixture',
                'actions': [{'type': 'prepare_direction', 'label': '核对方向草稿', 'fields': {'goal': goal, 'non_goals': '首版不做支付和复杂推荐。'}},
                            {'type': 'share_turn', 'label': '选择结论共享'},
                            {'type': 'request_team_review', 'label': '查看团队统筹'},
                            {'type': 'open_page', 'label': '回到资料入口', 'page': 'materials'}]}

    def coordinate(context):
        record('coordination', context)
        members = context['members']
        return {'summary': '固定体验样例：先整理项目说明，再准备可交接的演示；实际作品仍需本人完成。',
                'findings': [{'topic': '先完成最小成果', 'decision': '用一页项目说明和一分钟演示明确范围。', 'reason': '让成员有可检查的交接依据。', 'source_ids': ['direction'], 'needs_check': True}],
                'tasks': [{'key': 'T1', 'title': '整理一页项目说明', 'owner_id': members[0]['id'], 'acceptance': '包含目标用户、核心问题、最小范围和三步使用流程；队友逐项核对。', 'depends_on': [], 'source_ids': ['direction']},
                          {'key': 'T2', 'title': '准备一分钟演示与交付清单', 'owner_id': members[-1]['id'], 'acceptance': '包含开场、三步演示、已知限制与分工；另一成员核对并留下检查依据。', 'depends_on': ['T1'], 'source_ids': ['direction']}],
                'questions': ['实际作品是否符合活动原文要求，需要主办方核对？']}

    def materials(context):
        record('materials', context)
        return fixture_model(context)

    with ExitStack() as stack:
        stack.enter_context(patch('app.studio.must_deliver', return_value=False))
        stack.enter_context(patch('app.studio.test_codes_allowed', return_value=True))
        stack.enter_context(patch('app.studio.deliver_login_code', return_value=(False, '独立体验测试，不向手机发送短信')))
        stack.enter_context(patch('app.team_core.team_model_config', return_value={'api_key': '', 'model_id': '固定体验样例'}))
        app = create_app(database, core_only=True, core_model_runner=coordinate, materials_model_runner=materials, workbench_model_runner=discuss)

        @app.get('/api/ux-review')
        def marker():
            return {'session': args.session, 'sms': 'fixture', 'model': 'fixture', 'initial_users': 0, 'initial_teams': 0}

        (folder / 'manifest.json').write_text(json.dumps({'pid': os.getpid(), 'session': args.session, 'url': f'http://127.0.0.1:{args.port}', 'database': str(database), 'started_at': now(), 'sms': 'fixture', 'model': 'fixture', 'initial_users': 0, 'initial_teams': 0}, ensure_ascii=False, indent=2), encoding='utf-8')
        import uvicorn
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
