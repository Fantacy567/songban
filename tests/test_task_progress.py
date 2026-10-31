import unittest
from app.task_progress import member_task_progress
from tests import test_team_core as fixtures


class TaskProgressTests(unittest.TestCase):
    setUp = fixtures.CoreTests.setUp
    tearDown = fixtures.CoreTests.tearDown
    snap = fixtures.CoreTests.snap
    report = fixtures.CoreTests.report
    review = fixtures.CoreTests.review
    confirm = fixtures.CoreTests.confirm

    def member(self, user='a'):
        return next(m for m in self.snap()['task_progress'] if m['user_id'] == user)

    def publish(self):
        self.assertEqual(self.confirm(self.review()).status_code, 200)

    def check(self, verdict):
        snap = self.snap();task = snap['active_plan']['tasks'][0]
        r = self.client.post(self.base+'/tasks/T1/check', headers=self.h('b'), json={'expected_revision': snap['revision'], 'plan_version': snap['plan_version'], 'report_id': task['latest_report_id'], 'verdict': verdict, 'note': '测试：按检查方法核对成果'})
        self.assertEqual(r.status_code, 200, r.text)

    def test_completion_is_persisted_shared_and_idempotent(self):
        self.publish();self.assertEqual(self.member()['percent'], 0)
        r = self.report(event='start', task_key='T1', plan_version=1, status='in_progress')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.member()['current_task']['kind'], 'in_progress')
        for _ in range(2):
            r = self.report(event='done', task_key='T1', plan_version=1, status='reported_done', evidence=['实际成果说明'])
            self.assertEqual(r.status_code, 200)
        self.assertEqual(self.member()['completed'], 1)
        self.assertEqual(self.member()['percent'], 100)
        self.assertEqual(self.member()['accepted'], 0)
        other = self.client.get(self.base, headers=self.h('b')).json()
        self.assertEqual(next(m for m in other['task_progress'] if m['user_id']=='a'), self.member())
        self.check('accepted');self.assertEqual(self.member()['accepted'], 1)
        self.assertEqual(self.member()['percent'], 100)

    def test_returned_task_reopens_progress_without_affecting_teammate(self):
        self.publish();self.report(event='done', task_key='T1', plan_version=1, status='reported_done', evidence=['需核对的成果'])
        self.check('changes_requested')
        self.assertEqual(self.member()['percent'], 0)
        self.assertEqual(self.member()['current_task']['kind'], 'changes_requested')
        self.assertEqual(self.member('b')['completed'], 0)
        self.report(event='fixed', task_key='T1', plan_version=1, status='reported_done', evidence=['修正后的成果'])
        self.assertEqual(self.member()['percent'], 100)

    def test_wrong_owner_or_version_cannot_change_progress(self):
        self.publish()
        for headers,version in [(self.h('b'),1),(self.h('a'),99)]:
            r=self.report(headers=headers,event='invalid'+str(version),task_key='T1',plan_version=version,status='reported_done')
            self.assertEqual(r.status_code,409)
        self.assertEqual(self.member()['percent'],0)

    def test_no_tasks_is_zero_and_half_completion_uses_current_plan_only(self):
        self.assertEqual(self.member()['percent'],0)
        self.assertEqual(self.member()['total'],0)
        self.assertIsNone(self.member()['current_task'])
        members=[{'id':'a','name':'同伴'}]
        def task(key,status,handoff,seq=0):return {'key':key,'owner_id':'a','title':key,'status':status,'handoff_state':handoff,'latest_report_seq':seq,'waiting_on':[]}
        values=member_task_progress(members,[task('T1','reported_done','accepted'),task('T2','in_progress','not_reported',10)])
        self.assertEqual(values[0]['percent'],50)
        self.assertEqual(values[0]['current_task']['key'],'T2')
