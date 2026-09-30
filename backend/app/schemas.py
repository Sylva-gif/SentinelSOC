from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=80)
    event_type: str = Field(min_length=2, max_length=80)
    occurred_at: datetime | None = None
    source_ip: str | None = Field(default=None, max_length=64)
    domain: str | None = Field(default=None, max_length=253)
    username: str | None = Field(default=None, max_length=120)
    asset: str | None = Field(default=None, max_length=120)
    outcome: str | None = Field(default=None, max_length=40)
    message: str = Field(default="", max_length=4000)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


    @field_validator("source_ip")
    @classmethod
    def valid_ip(cls, value):
        return str(ip_address(value)) if value else None

    @field_validator("occurred_at")
    @classmethod
    def utc_timestamp(cls, value):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(timezone.utc)


class EventBatch(BaseModel):
    events: list[EventInput] = Field(min_length=1, max_length=200)


class IncidentUpdate(BaseModel):
    severity: Literal["low", "medium", "high", "critical"] | None = None
    status: Literal["triage", "investigating", "contained", "resolved", "closed"] | None = None
    assignee: str | None = Field(default=None, max_length=80)


class EntryInput(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class AssistantInput(BaseModel):
    question: str = Field(default="Résume et propose les prochaines vérifications.", max_length=1000)


class PlaybookInput(BaseModel):
    playbook_key: Literal["collect_evidence", "isolate_host", "disable_account"]


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    threshold: int | None = Field(default=None, ge=2, le=100)
    window_minutes: int | None = Field(default=None, ge=1, le=1440)
    severity: Literal["low", "medium", "high", "critical"] | None = None


class IntegrationUpdate(BaseModel):
    enabled: bool


class UserInput(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "analyst", "soc_manager"]
