# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Frozen, bounded course inputs. Empty work is a valid saved draft."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Id = Annotated[str, Field(min_length=1, max_length=150, pattern=r'^[A-Za-z0-9_.:@-]+$')]
Text500 = Annotated[str, Field(max_length=500)]
Text1000 = Annotated[str, Field(max_length=1000)]
Answer = Annotated[str, Field(max_length=2000)]


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class Answers(Strict):
    understand: Answer
    try_: Answer = Field(alias='try')
    reflect: Answer


class SaveProgress(Strict):
    request_id: Id
    expected_revision: Annotated[int, Field(ge=0)]
    # Keep wire keys intact through register_domain's model_dump().
    answers: dict[str, str]
    activity: dict
    project_id: Id | None

    @field_validator('answers')
    @classmethod
    def answers_contract(cls, value):
        return Answers.model_validate(value).model_dump(by_alias=True)


class ToolSort(Strict):
    sequence: Annotated[list[Literal['describe', 'generate', 'run', 'check', 'improve']], Field(max_length=5)]

    @field_validator('sequence')
    @classmethod
    def unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Sequence must be unique')
        return value


class Imagination(Strict):
    audience: Text500
    problem: Text500
    feature: Text500
    check: Text500


class FirstProject(Strict):
    change: Text1000
    observation: Text1000


class Plugins(Strict):
    enabled: bool
    before: Text1000
    after: Text1000


class Models(Strict):
    choice: Literal['sample-a', 'sample-b', 'undecided']
    reason: Text1000


class ApiActivity(Strict):
    name: Annotated[str, Field(max_length=40)]
    message: Annotated[str, Field(max_length=200)]


class ModelApp(Strict):
    input: Text500
    role: Text500
    output: Text500
    fallback: Text500


ACTIVITY_SCHEMAS = {
    'ai-tools': ToolSort, 'imagination': Imagination, 'first-project': FirstProject,
    'plugins': Plugins, 'models': Models, 'api': ApiActivity, 'model-powered-app': ModelApp,
}


class Experiment(Strict):
    request_id: Id
    operation: Literal['greet']
    name: Annotated[str, Field(min_length=1, max_length=40)]

    @field_validator('name', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class Progress(Strict):
    course_id: str
    course_version: str
    learner_id: str
    revision: Annotated[int, Field(ge=0)]
    answers: dict[str, str]
    activity: dict
    project_id: str | None
    updated_at: str | None
    status: Literal['not_started', 'saved']


ROUTE_SPECS = (
    ('GET', '/learning-courses/{course_id}/progress', 'courseProgress', 200),
    ('POST', '/learning-courses/{course_id}/progress', 'saveCourseProgress', 200),
)
REQUEST_SCHEMAS = {'saveCourseProgress': SaveProgress}
RESPONSE_SCHEMAS = {'courseProgress': Progress, 'saveCourseProgress': Progress}
