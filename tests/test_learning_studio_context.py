"""Bounded teaching context, using synthetic SQLite and offline model transport."""
import unittest
from dataclasses import replace

try:
    from .test_learning_v2_models import ModelFixture
except ImportError:
    from test_learning_v2_models import ModelFixture


class StudioContextTests(ModelFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.service.settings = replace(self.service.settings, studio_enabled=True)

    def ask(self, text, mode='static', task='S2.1'):
        return self.post('/runs/'+self.rid_run+'/help', dict(expected_revision=self.fresh()['revision'],
            role_id='guide', help_level=1, mode=mode, question=text, source_ids=[],
            task_id=task, task_card_version='0.1.0'), 202)

    def test_new_prompt_uses_only_last_four_relevant_turns(self):
        self.ask('不同关卡不要带入', task='S1.1')
        for n in range(6):
            self.ask('第'+str(n)+'次问题')
        event = self.ask('现在怎么修改', mode='mock')
        with self.service.store.transaction() as con:
            payload = self.service.meta(con, event['model_run_id'])['input_snapshot']
        self.assertEqual([t['question'] for t in payload['conversation']], ['第2次问题', '第3次问题', '第4次问题', '第5次问题'])
        self.assertNotIn('learner_self_report', payload)
        self.assertLessEqual(sum(len(t['question']) + len(t['reply']) for t in payload['conversation']), 5200)
        self.assertEqual(self.calls, [])

    def test_legacy_layout_keeps_original_prompt_shape(self):
        self.service.settings = replace(self.service.settings, studio_enabled=False)
        self.ask('历史提问')
        event = self.ask('只问当前题', mode='mock')
        with self.service.store.transaction() as con:
            payload = self.service.meta(con, event['model_run_id'])['input_snapshot']
        self.assertNotIn('conversation', payload)
        self.assertNotIn('learner_self_report', payload)
        self.assertNotIn('workbench', payload)

    def test_studio_prompt_matches_actual_controlled_text_workflow(self):
        event = self.ask('我第一步做什么', mode='mock')
        with self.service.store.transaction() as con:
            payload = self.service.meta(con, event['model_run_id'])['input_snapshot']
        self.assertEqual(payload['workbench']['kind'], 'controlled_text_invitation')
        self.assertEqual(payload['workbench']['current_stage'], 'create')
        self.assertIn('打开已保存的作品', payload['workbench']['current_steps'])
        self.assertIn('没有页面大小', payload['workbench']['limits'])
        self.assertTrue(event['prompt_version'].endswith('+studio.1'))
        system = self.service._model_messages('help', payload)[0]['content']
        self.assertIn('不得发明控件', system)
        self.assertIn('每次先给一个', system)


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(StudioContextTests)
