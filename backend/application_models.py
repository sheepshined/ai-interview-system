"""Shared validation for application APIs and assistant tools."""
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

Stage = Literal["saved", "applied", "screening", "interview", "offer", "rejected", "withdrawn"]


class ApplicationBody(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    company: str = Field(min_length=1, max_length=160)
    role_title: str = Field(min_length=1, max_length=160)
    job_url: str = Field(default="", max_length=2000)
    jd_text: str = Field(default="", max_length=20000)
    stage: Stage = "saved"
    resume_id: int | None = Field(default=None, gt=0)

    @field_validator("job_url")
    @classmethod
    def safe_url(cls, value):
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in ("https", "http") or not parsed.hostname:
                raise ValueError("JD 链接必须是有效的 HTTP 或 HTTPS 地址")
        return value


class ApplicationUpdateBody(ApplicationBody):
    expected_jd_version: int | None = Field(default=None, ge=0)


class JdVersionBody(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    jd_text: str = Field(max_length=20000)
    source_url: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=0)

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        return ApplicationBody.safe_url(value)


class JdRestoreBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    expected_version: int = Field(ge=0)


class ApplicationOutcomeBody(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    result: str = Field(default="", max_length=80)
    feedback: str = Field(default="", max_length=10000)
    reflection: str = Field(default="", max_length=10000)
    next_steps: str = Field(default="", max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values):
        return list(dict.fromkeys(tag.strip()[:60] for tag in values if tag.strip()))


class ApplicationEventBody(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    note: str = Field(min_length=1, max_length=4000)
