import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parent.parent/'plugins/songban-team/bridge.py'
spec=importlib.util.spec_from_file_location('songban_bridge',PATH)
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cwd=patch.object(bridge.Path,'cwd',return_value=self.root);self.cwd.start()
        self.env=patch.dict('os.environ',{'SONGBAN_URL':'http://127.0.0.1:8888','SONGBAN_TEAM_ID':'test-team','SONGBAN_TOKEN':'sbconn_connector-test-token'},clear=False);self.env.start()

    def tearDown(self):self.env.stop();self.cwd.stop();self.tmp.cleanup()

    def test_offline_keeps_queue_and_retry_keeps_event(self):
        update=self.root/'songban-update.json';update.write_text(json.dumps({'event_id':'offline-one','summary':'重要进展'}))
        with patch.object(bridge,'call',side_effect=bridge.BridgeError('网络不可用')):
            with self.assertRaises(bridge.BridgeError):bridge.sync_file(update)
        queued=list((self.root/'.songban/outbox').glob('*.json'));self.assertEqual(len(queued),1)
        with patch.object(bridge,'call',return_value={'report_id':'saved','duplicate':False}) as call:
            result=bridge.flush();self.assertEqual(result['sent'],1);self.assertEqual(call.call_args.args[1]['event_id'],'offline-one')
        self.assertEqual(len(list((self.root/'.songban/outbox').glob('*.json'))),0)

    def test_rejected_old_task_does_not_block_new_report(self):
        bridge.enqueue(bridge.prepare({'event_id':'old','summary':'旧任务'}));bridge.enqueue(bridge.prepare({'event_id':'new','summary':'新进展'}))
        with patch.object(bridge,'call',side_effect=[bridge.BridgeError('旧版本',status=409),{'report_id':'new-ok'}]):
            result=bridge.flush()
        self.assertEqual(result['sent'],1);self.assertEqual(len(result['rejected']),1)
        self.assertEqual(len(list((self.root/'.songban/rejected').glob('*.json'))),1)

    def test_switch_team_never_leaks_queued_report(self):
        bridge.enqueue(bridge.prepare({'event_id':'private-team-one','summary':'仅第一队'}))
        with patch.dict('os.environ',{'SONGBAN_TEAM_ID':'second-team'}),patch.object(bridge,'call') as call:
            self.assertEqual(bridge.flush()['sent'],0);call.assert_not_called()

    def test_unchanged_file_retries_same_id(self):
        update=self.root/'songban-update.json';update.write_text(json.dumps({'summary':'同一条进展'}))
        ids=[]
        with patch.object(bridge,'call',side_effect=lambda p,b:ids.append(b['event_id']) or {'report_id':'ok'}):
            bridge.sync_file(update);bridge.sync_file(update)
        self.assertEqual(ids[0],ids[1])

    def test_redacts_common_credentials_before_queue(self):
        data=bridge.prepare({'summary':'API_KEY=sk-EXAMPLE1234567890','excerpt':'Bearer sbconn_secret-test-12345'})
        self.assertNotIn('EXAMPLE1234567890',json.dumps(data));self.assertNotIn('secret-test',json.dumps(data))

    def test_does_not_read_other_projects(self):
        with tempfile.TemporaryDirectory() as other:
            p=Path(other)/'private.json';p.write_text('{}')
            with self.assertRaises(bridge.BridgeError):bridge.read_update(p)

    def test_rejects_unknown_identity_fields(self):
        with self.assertRaises(bridge.BridgeError):bridge.prepare({'summary':'hello','user_id':'someone-else'})

    def test_file_agent_receives_direction_and_own_tasks(self):
        expected={'direction':{'goal':'共同目标'},'plan_version':2,'revision':9,'tasks':[{'key':'T1','title':'本人任务'}]}
        with patch.object(bridge,'call',return_value=expected):
            bridge.pull_local_tasks()
        actual=json.loads((self.root/'.songban/team-state.json').read_text(encoding='utf-8'))
        self.assertEqual(actual,expected)

    def test_remote_plain_http_rejected(self):
        with patch.dict('os.environ',{'SONGBAN_URL':'http://example.com'}):
            with self.assertRaises(bridge.BridgeError):bridge.config()

if __name__=='__main__':unittest.main()
