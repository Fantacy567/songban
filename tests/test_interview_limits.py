"""Bounded interviews and recovery of pre-existing long transcripts, offline only."""
import copy
import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app.interview import InterviewError, next_turn
from app.main import create_app, digest, now


def transcript(count, unanswered=False):
    messages = []
    for number in range(1, count + 1):
        messages.append({'id': f'q{len(messages)+1}', 'role': 'assistant', 'text': f'第{number}个想法是什么？'})
        if not unanswered or number < count:
            messages.append({'id': f'u{len(messages)+1}', 'role': 'user', 'text': f'虚构练习想法{number}'})
    return messages


def profile(messages):
    result = {key: [] for key in ('interests', 'goals', 'experiences', 'possible_strengths',
                                 'roles_to_try', 'help_needed', 'next_practice', 'conflicts', 'unknowns')}
    result.update(type='profile_draft', time_available=None)
    users = [m for m in messages if m['role'] == 'user']
    if users:
        result['goals'] = [{'text': users[-1]['text'][:60], 'basis': 'self_reported', 'evidence': [users[-1]['id']]}]
    return result


class FixtureRunner:
    def __init__(self):
        self.payloads = []
        self.fail_summary = False
        self.ignore_limit = False

    def __call__(self, system, payload):
        self.payloads.append(copy.deepcopy(payload))
        if payload['mode'] == 'profile_only' and not self.ignore_limit:
            if self.fail_summary:
                raise InterviewError('model_timeout', '虚构模型超时', 504, True)
            result = profile(payload['transcript'])
        else:
            result = {'type': 'ask', 'question': f'第{payload["asked_count"]+1}个想法是什么？',
                      'purpose': '虚构离线验证', 'dimension': 'want_to_make'}
        return json.dumps(result, ensure_ascii=False), 'offline-interview-fixture'


class InterviewLimitTests(unittest.TestCase):
    def test_eighth_question_is_last_and_ninth_is_rejected(self):
        runner = FixtureRunner()
        result = next_turn({'messages': transcript(7), 'asked_count': 7}, runner)
        self.assertEqual((result['number'], result['max_questions']), (8, 8))
        result = next_turn({'messages': transcript(8), 'asked_count': 8}, runner)
        self.assertEqual((result['type'], result['reason']), ('profile_draft', 'limit_reached'))
        self.assertEqual(runner.payloads[-1]['remaining_questions'], 0)
        runner.ignore_limit = True
        with self.assertRaises(InterviewError) as caught:
            next_turn({'messages': transcript(8), 'asked_count': 8}, runner)
        self.assertEqual(caught.exception.code, 'question_limit_reached')

    def test_legacy_transcripts_can_finish_without_losing_answers(self):
        for count in (17, 30):
            with self.subTest(count=count):
                runner = FixtureRunner()
                messages = transcript(count, unanswered=True)
                result = next_turn({'messages': messages, 'asked_count': count, 'finish': True}, runner)
                self.assertEqual(result['type'], 'profile_draft')
                self.assertEqual(runner.payloads[0]['transcript'], messages)
                self.assertEqual(runner.payloads[0]['mode'], 'profile_only')
                self.assertEqual(runner.payloads[0]['remaining_questions'], 0)

    def test_legacy_final_answer_only_summarizes(self):
        runner = FixtureRunner()
        result = next_turn({'messages': transcript(17), 'asked_count': 17}, runner)
        self.assertEqual(result['reason'], 'limit_reached')
        self.assertEqual(runner.payloads[0]['mode'], 'profile_only')

    def test_history_validation_and_finish_are_not_bypassed(self):
        runner = FixtureRunner()
        for request, code in [
            ({'messages': [], 'asked_count': 31, 'finish': True}, 'asked_count_over_limit'),
            ({'messages': transcript(2), 'asked_count': 17, 'finish': True}, 'asked_count_mismatch'),
        ]:
            with self.subTest(code=code), self.assertRaises(InterviewError) as caught:
                next_turn(request, runner)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(runner.payloads, [])
        runner.ignore_limit = True
        with self.assertRaises(InterviewError) as caught:
            next_turn({'messages': transcript(1), 'asked_count': 1, 'finish': True}, runner)
        self.assertEqual(caught.exception.code, 'finish_requested')


class InterviewFinishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'interview.sqlite3'
        self.runner = FixtureRunner()
        self.app = create_app(self.path, core_only=True, enforce_journey=True, interview_runner=self.runner)
        self.client = TestClient(self.app)
        with closing(sqlite3.connect(self.path)) as con:
            for user in ('a', 'b'):
                con.execute('INSERT INTO people(id,name,phone,token_hash,created_at) VALUES(?,?,?,?,?)',
                            (user, '虚构成员'+user, 'fixture-'+user, digest('fixture-token-'+user), now()))
            con.commit()

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def call(self, suffix='', body=None, status=200, user='a'):
        response = self.client.request('GET' if body is None else 'POST', '/api/core/interview'+suffix,
                                       headers={'Authorization': 'Bearer fixture-token-'+user}, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def answer_body(self, state, text='虚构回答'):
        return {'version': state['version'], 'question_id': state['current_question']['id'],
                'request_id': uuid.uuid4().hex, 'text': text}

    def seed_legacy(self):
        self.call('/start', {})
        messages = transcript(17, unanswered=True)
        with closing(sqlite3.connect(self.path)) as con:
            con.execute('DELETE FROM core_interview_messages WHERE user_id=?', ('a',))
            for seq, message in enumerate(messages, 1):
                con.execute('INSERT INTO core_interview_messages(user_id,seq,id,role,text,created_at) VALUES(?,?,?,?,?,?)',
                            ('a', seq, message['id'], message['role'], message['text'], now()))
            con.execute('UPDATE core_interviews SET current_question_id=?,version=17 WHERE user_id=?', (messages[-1]['id'], 'a'))
            con.commit()
        return self.call()

    def test_full_flow_stops_at_eight_and_requires_confirmation(self):
        state = self.call('/start', {})
        for number in range(1, 9):
            self.assertEqual(state['current_question']['number'], number)
            state = self.call('/answer', self.answer_body(state))
        self.assertEqual(state['status'], 'pending_confirmation')
        self.assertEqual(state['asked_count'], 8)
        self.assertEqual(len([m for m in state['messages'] if m['role'] == 'user']), 8)
        self.assertIsNone(state['current_question'])
        self.assertIsNone(state['profile']['confirmed_at'])
        state = self.call('/confirm', {'version': state['version'], 'request_id': uuid.uuid4().hex})
        self.assertEqual(state['status'], 'confirmed')

    def test_finish_saves_current_answer_atomically_and_is_idempotent(self):
        state = self.call('/start', {})
        body = self.answer_body(state, '我想做一个虚构的图书交换工具')
        done = self.call('/finish', body)
        self.assertEqual(done['status'], 'pending_confirmation')
        self.assertEqual(done['messages'][-1]['text'], body['text'])
        self.assertEqual(done['profile']['draft']['goals'][0]['evidence'], [done['messages'][-1]['id']])
        calls = len(self.runner.payloads)
        self.assertTrue(self.call('/finish', body)['replayed'])
        self.assertEqual(len(self.runner.payloads), calls)
        self.call('/finish', {**body, 'text': '换了内容'}, status=409)
        self.assertEqual(self.call(user='b')['status'], 'not_started')
        self.call('/finish', body, status=409, user='b')

    def test_legacy_seventeenth_question_can_finish_empty_and_survive_restart(self):
        state = self.seed_legacy()
        done = self.call('/finish', {'version': state['version'], 'request_id': uuid.uuid4().hex})
        self.assertEqual(done['messages'], state['messages'])
        self.assertEqual((done['asked_count'], done['max_questions']), (17, 8))
        self.assertEqual(done['status'], 'pending_confirmation')
        self.client.close()
        self.client = TestClient(create_app(self.path, core_only=True, enforce_journey=True, interview_runner=self.runner))
        self.assertEqual(self.call()['messages'], state['messages'])
        self.assertEqual(self.call()['status'], 'pending_confirmation')

    def test_old_browser_answer_on_question_seventeen_does_not_ask_eighteen(self):
        state = self.seed_legacy()
        done = self.call('/answer', self.answer_body(state))
        self.assertEqual(done['status'], 'pending_confirmation')
        self.assertEqual(done['asked_count'], 17)
        self.assertEqual(len(done['messages']), len(state['messages'])+1)
        self.assertEqual(self.runner.payloads[-1]['mode'], 'profile_only')

    def test_summary_failure_keeps_history_and_retry_saves_answer_once(self):
        state = self.call('/start', {})
        body = self.answer_body(state, '失败后仍然保留的虚构答案')
        self.runner.fail_summary = True
        self.call('/finish', body, status=504)
        self.assertEqual(self.call(), state)
        self.runner.fail_summary = False
        done = self.call('/finish', body)
        self.assertEqual(len([m for m in done['messages'] if m['role']=='user']), 1)
        self.assertEqual(done['messages'][-1]['text'], body['text'])

    def test_finish_rejects_invalid_or_stale_answer_without_calling_model(self):
        state = self.call('/start', {})
        body = self.answer_body(state)
        for change in ({'text': ''}, {'text': '字'*1001}, {'text': 'x\x00'}, {'question_id': None}):
            self.call('/finish', {**body, **change}, status=422)
        self.call('/finish', {**body, 'question_id': 'q-other'}, status=409)
        self.call('/finish', {**body, 'version': state['version']+1}, status=409)
        self.assertEqual(len(self.runner.payloads), 1)
        self.assertEqual(self.call(), state)

    def test_manual_three_question_flow_can_finish_early(self):
        state = self.call('/manual-start', {})
        done = self.call('/finish', self.answer_body(state))
        self.assertEqual(done['source']['kind'], 'manual')
        self.assertEqual(done['status'], 'pending_confirmation')
        self.assertEqual(self.runner.payloads, [])
