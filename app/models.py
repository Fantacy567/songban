from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


Short = Annotated[str, Field(min_length=1, max_length=500)]


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(timezone.utc)


class MemberInput(Input):
    name: str = Field(min_length=1, max_length=40)
    role: str = Field(min_length=1, max_length=80)
    skills: str = Field(min_length=1, max_length=500)
    available_hours: float = Field(gt=0, le=168, strict=True)


class ProjectInput(Input):
    name: str = Field(min_length=1, max_length=100)
    deadline: datetime
    members: list[MemberInput] = Field(min_length=2, max_length=8)

    @field_validator("deadline")
    @classmethod
    def future(cls, value):
        value = aware(value)
        if value <= datetime.now(timezone.utc):
            raise ValueError("赛事截止时间必须晚于现在")
        return value

    @model_validator(mode="after")
    def distinct_names(self):
        names = [m.name.casefold() for m in self.members]
        if len(names) != len(set(names)):
            raise ValueError("成员姓名不可重复；首位成员是队长")
        return self


class SourceInput(Input):
    kind: Literal["rules", "discussion"]
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=20000)


class GenerateInput(Input):
    mode: Literal["local_rules", "model"]


class Evidence(Input):
    source_id: str = Field(min_length=1, max_length=50)
    quote: str = Field(min_length=1, max_length=300)


class TaskDraft(Input):
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,19}$")
    title: str = Field(min_length=1, max_length=120)
    owner_id: str = Field(min_length=1, max_length=50)
    acceptance: str = Field(min_length=1, max_length=1000)
    estimated_hours: float = Field(gt=0, le=48, strict=True)
    priority: Literal["must", "should"]
    due_at: datetime
    depends_on: list[str] = Field(default_factory=list, max_length=12)
    evidence: list[Evidence] = Field(min_length=1, max_length=4)

    @field_validator("due_at")
    @classmethod
    def timezone_required(cls, value):
        return aware(value)


class Draft(Input):
    goal: Short
    decisions: list[Short] = Field(default_factory=list, max_length=12)
    open_questions: list[Short] = Field(default_factory=list, max_length=12)
    risks: list[Short] = Field(default_factory=list, max_length=12)
    tasks: list[TaskDraft] = Field(min_length=1, max_length=12)


class DraftUpdate(Input):
    expected_version: int = Field(ge=1, strict=True)
    content: Draft


class VersionInput(Input):
    expected_version: int = Field(ge=1, strict=True)


class TaskAction(VersionInput):
    action: Literal["start", "block", "resume", "submit", "accept", "return"]
    note: str = Field(default="", max_length=5000)


class ModelDiscovery(Input):
    base_url: str = Field(min_length=1, max_length=500)
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def usable_key(cls, value):
        text = value.get_secret_value().strip()
        if not text or len(text) > 1000 or "\n" in text or "\r" in text:
            raise ValueError("请填写有效且不含换行的 API key")
        return SecretStr(text)


class ModelSelection(Input):
    mode: Literal["builtin", "custom"]
    expected_version: int = Field(ge=0, strict=True)
    discovery_id: str | None = Field(default=None, max_length=100)
    model_id: str | None = Field(default=None, max_length=200)
