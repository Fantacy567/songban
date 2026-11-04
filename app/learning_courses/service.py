# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Learner-owned drafts, with no automatic mastery or external provider calls."""
import json

from pydantic import ValidationError

from app.learning_v2.protocol import canonical, fail, revision
from .catalog import known_course, load_course
from .schemas import ACTIVITY_SCHEMAS
from .storage import migrate

NOTICE = '这是固定规则的教学接口，没有调用大模型。'


def experiment_response(body):
    return {'kind': 'teaching-api', 'request': {'operation': body['operation'], 'name': body['name']},
            'response': {'message': f"你好，{body['name']}！"}, 'notice': NOTICE}


class CoursesService:
    def __init__(self, platform):
        self.platform, self.learning, self.store = platform, platform.learning, platform.store

    def migrate(self):
        migrate(self.store, self.learning.stamp())

    def project(self, con, session, project_id):
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='creative_projects'").fetchone()
        row = con.execute('SELECT 1 FROM creative_projects WHERE id=? AND owner=? AND learner_id=?',
                          (project_id, 'learner:'+session['learner_id'], session['learner_id'])).fetchone() if exists else None
        if not row:
            fail(404, 'course_project_not_found', '找不到当前学习身份的创作项目。')

    def authorize(self, con, op, session, params, body):
        self.learning.role(session, 'learner')
        self.learning.learner(con, session, session['learner_id'])
        self.learning.learning_access(con, session['learner_id'])
        course_id = params.get('course_id', 'api')
        known_course(course_id)
        if op != 'courseProgress' and not self.learning.settings.enabled:
            fail(423, 'learning_paused', '学习新写入暂未开放，已保存记录仍可读取。')
        if op == 'saveCourseProgress':
            if body['activity']:
                try:
                    ACTIVITY_SCHEMAS[course_id].model_validate(body['activity'])
                except ValidationError:
                    fail(422, 'invalid_activity', '练习字段或内容不符合这门课程，请核对后重试。')
            if body['project_id'] is not None:
                if course_id != 'first-project':
                    fail(422, 'invalid_project_binding', '只有小项目课程可以关联创作项目。')
                self.project(con, session, body['project_id'])

    def read(self, con, op, session, params, query):
        course_id, learner_id = params['course_id'], session['learner_id']
        row = con.execute('SELECT * FROM learning_course_progress WHERE learner_id=? AND course_id=?',
                          (learner_id, course_id)).fetchone()
        if row:
            result = dict(row)
            result.update(answers=json.loads(row['answers']), activity=json.loads(row['activity']), status='saved')
            return result
        return {'course_id': course_id, 'course_version': load_course(course_id)['version'], 'learner_id': learner_id,
                'revision': 0, 'answers': {'understand': '', 'try': '', 'reflect': ''}, 'activity': {},
                'project_id': None, 'updated_at': None, 'status': 'not_started'}

    def write(self, con, op, session, params, body):
        if op == 'courseApiExperiment':
            # Platform persists only this receipt and an HMAC of the input.
            # The deterministic response is constructed after final identity
            # validation, from this request's validated body, even on replay.
            return {'kind': 'teaching-api', 'notice': NOTICE}
        course_id, learner_id = params['course_id'], session['learner_id']
        course = load_course(course_id)
        row = con.execute('SELECT revision FROM learning_course_progress WHERE learner_id=? AND course_id=?',
                          (learner_id, course_id)).fetchone()
        current_revision = row[0] if row else 0
        revision(body['expected_revision'], current_revision)
        con.execute('''INSERT INTO learning_course_progress VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(learner_id,course_id) DO UPDATE SET course_version=excluded.course_version,
            revision=excluded.revision,answers=excluded.answers,activity=excluded.activity,
            project_id=excluded.project_id,updated_at=excluded.updated_at''',
            (learner_id, course_id, course['version'], current_revision+1, canonical(body['answers']),
             canonical(body['activity']), body['project_id'], self.learning.stamp()))
        return self.read(con, 'courseProgress', session, params, {})
