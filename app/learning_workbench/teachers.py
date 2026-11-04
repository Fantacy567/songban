# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Server-owned teacher materials. Private prompts never enter the public projection."""
import json
from pathlib import Path

from app.learning_v2.protocol import fail
from .schemas import COURSES

MANIFEST = Path(__file__).resolve().parents[2] / 'curriculum' / 'ai-courses' / 'teachers.json'
PUBLIC_FIELDS = ('course_id', 'name', 'opening', 'suggestions', 'goal', 'sources', 'tools')


def load_teachers(path=None):
    try:
        value = json.loads(Path(path or MANIFEST).read_text(encoding='utf-8-sig'))
        teachers = value['teachers']
        if not isinstance(value['version'], str) or not value['version'] or len(teachers) != 7:
            raise ValueError('Invalid teacher manifest')
        if {t['course_id'] for t in teachers} != set(COURSES):
            raise ValueError('Seven original courses required')
        for teacher in teachers:
            for key in ('name', 'opening', 'goal', 'system_prompt'):
                if not isinstance(teacher[key], str) or not teacher[key].strip():
                    raise ValueError('Missing teacher text')
            for key in ('suggestions', 'sources', 'tools'):
                if not isinstance(teacher[key], list):
                    raise ValueError('Invalid teacher collection')
            for key in ('help_strategy', 'artifact_instruction', 'knowledge_points', 'misconceptions', 'review'):
                if key not in teacher:
                    raise ValueError('Missing teaching context')
        return value
    except (OSError, ValueError, KeyError, TypeError):
        fail(503, 'teachers_unavailable', '课程老师资料暂未就绪，已保存内容仍保留，请稍后再打开。', 'reload')


def public_teacher(teacher):
    return {key: teacher[key] for key in PUBLIC_FIELDS}


def teacher_for(course_id):
    if course_id not in COURSES:
        fail(404, 'course_not_found', '找不到这门课程。')
    return next(t for t in load_teachers()['teachers'] if t['course_id'] == course_id)
