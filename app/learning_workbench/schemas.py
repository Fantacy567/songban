# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Identifier = Annotated[str, Field(min_length=1, max_length=150, pattern=r'^[A-Za-z0-9_.:@-]+$')]
CourseId = Literal['ai-tools', 'imagination', 'first-project', 'plugins', 'models', 'api', 'model-powered-app']
COURSES = ('ai-tools', 'imagination', 'first-project', 'plugins', 'models', 'api', 'model-powered-app')
Title = Annotated[str, Field(min_length=1, max_length=160)]
Content = Annotated[str, Field(min_length=1, max_length=16000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @field_validator('*')
    @classmethod
    def text_is_present(cls, value):
        if isinstance(value, str):
            if not value.strip() or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
                raise ValueError('Nonempty text required')
            value.encode('utf-8')
        return value


class OpenSession(Strict):
    request_id: Identifier
    course_id: CourseId


class Versioned(Strict):
    request_id: Identifier
    expected_revision: Annotated[int, Field(ge=1)]


class SendMessage(Versioned):
    content: Annotated[str, Field(min_length=1, max_length=4000)]
    mode: Literal['mock', 'live']


class SaveArtifact(Versioned):
    title: Title
    content: Content
    source_message_id: Identifier | None = None


class SelectArtifact(Versioned):
    version_id: Identifier


class ConfirmRecord(Versioned):
    title: Title
    summary: Annotated[str, Field(min_length=1, max_length=6000)]
    next_step: Annotated[str, Field(max_length=2000)]

    @field_validator('next_step', mode='wrap')
    @classmethod
    def optional_next_step(cls, value, handler):
        return '' if value == '' else handler(value)


class Candidate(Strict):
    title: Title
    content: Content


class ModelOutput(Strict):
    reply: Annotated[str, Field(min_length=1, max_length=8000)]
    artifact: Candidate | None = None
    actual_model: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    usage: dict | None = None
    provider_request_id: Annotated[str, Field(max_length=200)] | None = None


REQUEST_SCHEMAS = {
    'openWorkbench': OpenSession, 'messageWorkbench': SendMessage,
    'artifactWorkbench': SaveArtifact, 'selectWorkbenchArtifact': SelectArtifact,
    'draftWorkbenchRecord': Versioned, 'confirmWorkbenchRecord': ConfirmRecord,
}
ROUTE_SPECS = (
    ('GET', '/learning-workbench/sessions', 'workbenchSessions', 200),
    ('POST', '/learning-workbench/sessions', 'openWorkbench', 200),
    ('GET', '/learning-workbench/sessions/{session_id}', 'workbenchSession', 200),
    ('POST', '/learning-workbench/sessions/{session_id}/messages', 'messageWorkbench', 200),
    ('POST', '/learning-workbench/sessions/{session_id}/artifacts', 'artifactWorkbench', 200),
    ('POST', '/learning-workbench/sessions/{session_id}/select-artifact', 'selectWorkbenchArtifact', 200),
    ('POST', '/learning-workbench/sessions/{session_id}/record-draft', 'draftWorkbenchRecord', 200),
    ('POST', '/learning-workbench/sessions/{session_id}/record-confirm', 'confirmWorkbenchRecord', 200),
    ('GET', '/learning-workbench/records', 'workbenchRecords', 200),
)
