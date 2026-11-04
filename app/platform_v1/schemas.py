"""Platform portfolio contract. No account credentials or publication writes."""
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.learning_v2.protocol import fail


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Identifier = Annotated[str, Field(min_length=1, max_length=150, pattern=r"^[A-Za-z0-9_.:@-]+$")]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]
Description = Annotated[str, Field(min_length=1, max_length=2000)]
Assistance = Literal["none_reported", "assisted", "generated", "unknown"]


def external_url(value: str) -> str:
    """Validate a displayed link only; portfolio never fetches this URL."""
    try:
        u = urlsplit(value)
        if (u.scheme not in ("http", "https") or not u.hostname or u.username is not None
                or u.password is not None or "\\" in value or any(ord(c) < 33 for c in value)):
            raise ValueError("invalid URL")
        _ = u.port
        value.encode("utf-8")
    except (ValueError, UnicodeError):
        raise ValueError("请填写不含账号凭据的 HTTP 或 HTTPS 作品链接。") from None
    return value


class Request(StrictModel):
    request_id: Identifier


class ExternalWorkInput(Request):
    title: ShortText
    summary: Description
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    tool_name: Annotated[str, Field(min_length=1, max_length=80)]
    contribution: Description
    ai_assistance: Assistance

    @field_validator("title", "summary", "tool_name", "contribution")
    @classmethod
    def text_present(cls, value):
        if not value.strip() or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("文字不能为空或含控制字符。")
        return value.strip()

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return external_url(value)


class ExternalWorkVersionInput(ExternalWorkInput):
    expected_revision: Annotated[int, Field(ge=1)]


class CompetitionLinkInput(Request):
    project_id: Identifier
    expected_source_revision: Annotated[int, Field(ge=1)]
    selected_refs: Annotated[list[Identifier], Field(min_length=1, max_length=12)]
    contribution: Description
    title: ShortText
    summary: Description

    @field_validator("title", "summary", "contribution")
    @classmethod
    def text_present(cls, value):
        return ExternalWorkInput.text_present(value)

    @field_validator("selected_refs")
    @classmethod
    def unique_refs(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("来源不能重复。")
        return value


class CompetitionDecisionInput(Request):
    expected_revision: Annotated[int, Field(ge=1)]
    decision: Literal["accept", "decline", "revoke"]


class SourceRef(StrictModel):
    domain: Literal["learning", "competition", "external"]
    id: str
    version: str


class Output(StrictModel):
    kind: Literal["text", "external_link"]
    label: str
    text: str | None = None
    url: str | None = None


class VersionRef(StrictModel):
    id: str
    number: int


class Provenance(StrictModel):
    kind: Literal["learning_record", "guardian_statement_learner_confirmed", "self_reported"]
    ai_assistance: Assistance
    source_label: str


class WorkSummary(StrictModel):
    id: str
    learner_id: str
    origin: Literal["learning", "competition", "external"]
    title: str
    summary: str
    revision: int
    source_ref: SourceRef
    current_version: VersionRef
    actual_outputs: list[Output]
    cover_asset_id: str | None
    contribution: str
    provenance: Provenance
    visibility: Literal["private"]
    updated_at: str
    available_actions: list[str]


class WorkVersion(StrictModel):
    id: str
    number: int
    actual_outputs: list[Output]
    created_at: str


class WorkDetail(WorkSummary):
    versions: list[WorkVersion]


class WorkList(StrictModel):
    items: list[WorkSummary]
    next_cursor: None


class SourcePreview(StrictModel):
    ref: str
    label: str
    text: str
    outputs: list[Output]


class CompetitionSource(StrictModel):
    project_id: str
    name: str
    source_revision: int
    available_refs: list[SourcePreview]


class CompetitionSources(StrictModel):
    items: list[CompetitionSource]


class CompetitionLink(StrictModel):
    id: str
    learner_id: str
    project_id: str
    source_revision: int
    revision: int
    state: Literal["offered", "accepted", "declined", "revoked"]
    title: str
    summary: str
    contribution: str
    selected_refs: list[str]
    sources: list[SourcePreview]
    source_label: str
    created_at: str
    updated_at: str


class CompetitionLinks(StrictModel):
    items: list[CompetitionLink]


REQUEST_SCHEMAS = {
    "createExternalWork": ExternalWorkInput,
    "versionExternalWork": ExternalWorkVersionInput,
    "createCompetitionLink": CompetitionLinkInput,
    "decideCompetitionLink": CompetitionDecisionInput,
}
RESPONSE_SCHEMAS = {
    "works": WorkList, "work": WorkDetail,
    "competitionSources": CompetitionSources, "competitionLinks": CompetitionLinks,
    "createExternalWork": WorkDetail, "versionExternalWork": WorkDetail,
    "createCompetitionLink": CompetitionLink, "decideCompetitionLink": CompetitionLink,
}
READ_OPS = frozenset(("works", "work", "competitionSources", "competitionLinks"))
WRITE_OPS = frozenset(REQUEST_SCHEMAS)
# Central registers these relative to /api/platform/v1 with its shared auth guard.
ROUTE_SPECS = (
    ("GET", "/learners/{learner_id}/works", "works", 200),
    ("GET", "/learners/{learner_id}/works/{work_id}", "work", 200),
    ("GET", "/learners/{learner_id}/competition-sources", "competitionSources", 200),
    ("GET", "/learners/{learner_id}/competition-source-links", "competitionLinks", 200),
    ("POST", "/learners/{learner_id}/external-works", "createExternalWork", 201),
    ("POST", "/learners/{learner_id}/external-works/{work_id}/versions", "versionExternalWork", 201),
    ("POST", "/learners/{learner_id}/competition-source-links", "createCompetitionLink", 201),
    ("POST", "/learners/{learner_id}/competition-source-links/{link_id}/decision", "decideCompetitionLink", 200),
)


def validate_request(op, body):
    try:
        return REQUEST_SCHEMAS[op].model_validate(body).model_dump()
    except (ValidationError, KeyError):
        fail(422, "invalid_input", "作品请求字段、长度或来源格式不正确。")
