"""Pydantic request/response schemas (camelCase on the wire)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.enums import ApprovalStatus, SourceType


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class CreateApprovalRequest(CamelModel):
    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10_000)
    reviewer_user_ids: list[str] = Field(default_factory=list)


class ApproveDecision(CamelModel):
    comment: str | None = Field(default=None, max_length=2_000)


class RejectDecision(CamelModel):
    reason: str = Field(min_length=1, max_length=2_000)


class CancelDecision(CamelModel):
    reason: str = Field(min_length=1, max_length=2_000)


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #
class ApprovalRequestRead(CamelModel):
    id: str
    workspace_id: str
    source_type: SourceType
    source_id: str
    title: str
    description: str | None
    reviewer_user_ids: list[str]
    status: ApprovalStatus
    decision_comment: str | None
    decision_reason: str | None
    decided_by: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class ApprovalRequestList(CamelModel):
    items: list[ApprovalRequestRead]
    total: int
    limit: int
    offset: int


def serialize_request(obj) -> dict:
    """ORM -> JSON-safe dict with camelCase keys."""
    return ApprovalRequestRead.model_validate(obj).model_dump(by_alias=True, mode="json")
