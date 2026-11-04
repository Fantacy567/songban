# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Read and validate C01's content without inventing fallback lessons."""
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.learning_v2.protocol import fail, strict_json, Problem

CATALOG_PATH = Path(__file__).resolve().parents[2] / 'curriculum' / 'ai-courses' / 'catalog.json'
COURSE_KINDS = {
    'ai-tools': 'tool-sort', 'imagination': 'idea-builder', 'first-project': 'project',
    'plugins': 'plugin-lab', 'models': 'model-compare', 'api': 'api-lab',
    'model-powered-app': 'model-app',
}
Nonempty = Annotated[str, Field(min_length=1)]


class Content(BaseModel):
    # Content may carry original-source/copyright metadata in addition to the
    # frozen required fields. This is trusted repository content, not user input.
    model_config = ConfigDict(strict=True, extra='allow')


class Chapter(Content):
    id: Literal['tools', 'advanced']
    title: Nonempty
    order: int


class Cover(Content):
    src: Nonempty
    alt: Nonempty


class Step(Content):
    id: Literal['understand', 'try', 'reflect']
    title: Nonempty
    instruction: Nonempty
    example: Nonempty
    prompt: Nonempty


class Activity(Content):
    kind: Nonempty
    title: Nonempty
    instruction: Nonempty


class Source(Content):
    title: Nonempty
    url: Nonempty
    supports: Nonempty

    @field_validator('url')
    @classmethod
    def web_source(cls, value):
        url = urlsplit(value)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or any(ord(c) < 32 for c in value):
            raise ValueError('HTTPS source required')
        return value


class Review(Content):
    technical: Literal['draft']
    education: Literal['pending']
    pilot: Literal['pending']


class Course(Content):
    id: str
    version: Literal['1']
    title: Nonempty
    chapter: Chapter
    order: int
    status: Literal['trial']
    goal: Nonempty
    preparation: Nonempty
    duration: Nonempty
    cover: Cover
    intro: Nonempty
    steps: Annotated[list[Step], Field(min_length=3, max_length=3)]
    activity: Activity
    sources: Annotated[list[Source], Field(min_length=1)]
    review: Review

    @model_validator(mode='after')
    def frozen_mapping(self):
        if self.id not in COURSE_KINDS:
            raise ValueError('Unknown course')
        order = list(COURSE_KINDS).index(self.id) + 1
        chapter = ('tools', 'AI 工具篇', 1) if order <= 4 else ('advanced', '进阶篇', 2)
        if self.order != order or (self.chapter.id, self.chapter.title, self.chapter.order) != chapter:
            raise ValueError('Chapter/order mismatch')
        if self.activity.kind != COURSE_KINDS[self.id] or self.cover.src != f'/static/platform/illustrations/course-{self.id}.svg':
            raise ValueError('Activity/cover mismatch')
        if [step.id for step in self.steps] != ['understand', 'try', 'reflect']:
            raise ValueError('Step mismatch')
        return self


class Catalog(Content):
    version: Literal['1']
    courses: Annotated[list[Course], Field(min_length=7, max_length=7)]

    @model_validator(mode='after')
    def seven_unique_courses(self):
        if {course.id for course in self.courses} != set(COURSE_KINDS):
            raise ValueError('Seven distinct courses required')
        return self


def known_course(course_id):
    if course_id not in COURSE_KINDS:
        fail(404, 'course_not_found', '找不到这门课程。')


def load_catalog():
    try:
        # UTF-8 BOM is tolerated for repository-authored Windows content.
        value = strict_json(CATALOG_PATH.read_text(encoding='utf-8-sig'))
        return Catalog.model_validate(value).model_dump()
    except (OSError, UnicodeError, ValueError, ValidationError, Problem):
        fail(503, 'course_catalog_unavailable', '课程内容暂时无法读取，请稍后重试。', 'reload')


def load_course(course_id):
    known_course(course_id)
    return next(course for course in load_catalog()['courses'] if course['id'] == course_id)
