"""Bounded browser programming files. No executable server configuration accepted."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator

Id = Annotated[str, Field(min_length=1, max_length=150, pattern=r'^[A-Za-z0-9_.:@-]+$')]
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class File(Strict):
    path: str
    content: Annotated[str, Field(max_length=18000)]
    @field_validator('path')
    @classmethod
    def filename(cls, value):
        if value not in ('index.html', 'style.css', 'script.js'):
            raise ValueError('Only three browser files are supported')
        return value

class Create(Strict):
    request_id: Id
    title: Annotated[str, Field(min_length=1, max_length=100)]
    idea: Annotated[str, Field(min_length=1, max_length=2000)]
    learner_id: Id | None = None
    @field_validator('title', 'idea')
    @classmethod
    def nonempty(cls, value):
        if not value.strip(): raise ValueError('Text required')
        return value.strip()

class Edit(Strict):
    request_id: Id
    expected_revision: Annotated[int, Field(ge=1)]
    files: Annotated[list[File], Field(min_length=1, max_length=3)]
    explanation: Annotated[str, Field(min_length=1, max_length=1500)]
    @field_validator('files')
    @classmethod
    def unique(cls, value):
        names = [v.path for v in value]
        if len(set(names)) != len(names) or 'index.html' not in names:
            raise ValueError('Unique files including index.html required')
        return value

class Message(Strict):
    request_id: Id
    expected_revision: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1, max_length=4000)]
    @field_validator('text')
    @classmethod
    def nonempty(cls, value):
        if not value.strip(): raise ValueError('Text required')
        return value.strip()

class Restore(Strict):
    request_id: Id
    expected_revision: Annotated[int, Field(ge=1)]
    version_id: Id

class Archive(Strict):
    request_id: Id
    expected_revision: Annotated[int, Field(ge=1)]
    contribution: Annotated[str, Field(min_length=1, max_length=3000)]

REQUEST_SCHEMAS = {'createStudio': Create, 'editStudio': Edit, 'messageStudio': Message, 'restoreStudio': Restore, 'archiveStudio': Archive}
ROUTE_SPECS = (
    ('GET', '/studio/projects', 'studios', 200),
    ('POST', '/studio/projects', 'createStudio', 201),
    ('GET', '/studio/projects/{project_id}', 'studio', 200),
    ('GET', '/studio/projects/{project_id}/preview', 'previewStudio', 200),
    ('POST', '/studio/projects/{project_id}/files', 'editStudio', 200),
    ('POST', '/studio/projects/{project_id}/messages', 'messageStudio', 200),
    ('POST', '/studio/projects/{project_id}/restore', 'restoreStudio', 200),
    ('POST', '/studio/projects/{project_id}/archive', 'archiveStudio', 200),
)
