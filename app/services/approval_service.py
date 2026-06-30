"""Approval business logic.

Service methods mutate the session and ``flush`` but never ``commit`` — the API
layer owns the unit-of-work boundary so that the state change, its audit record,
its outbox event and (optionally) the idempotency record all commit atomically.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.enums import FINAL_STATUSES, ApprovalAction, ApprovalStatus
from app.core.logging import log_event
from app.core.sanitization import sanitize
from app.models.approval import ApprovalEvent, ApprovalRequest
from app.models.outbox import OutboxEvent
from app.schemas.approval import CreateApprovalRequest

logger = logging.getLogger("app.approval")

_ACTION_TO_STATUS = {
    ApprovalAction.APPROVED: ApprovalStatus.APPROVED,
    ApprovalAction.REJECTED: ApprovalStatus.REJECTED,
    ApprovalAction.CANCELLED: ApprovalStatus.CANCELLED,
}

_EVENT_TYPE = {
    ApprovalAction.CREATED: "approval_request.created",
    ApprovalAction.APPROVED: "approval_request.approved",
    ApprovalAction.REJECTED: "approval_request.rejected",
    ApprovalAction.CANCELLED: "approval_request.cancelled",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_audit(
    db: Session,
    request: ApprovalRequest,
    *,
    action: ApprovalAction,
    actor: str,
    previous_status: ApprovalStatus | None,
    new_status: ApprovalStatus,
    metadata: dict | None,
) -> None:
    db.add(
        ApprovalEvent(
            workspace_id=request.workspace_id,
            request_id=request.id,
            action=action.value,
            actor_user_id=actor,
            previous_status=previous_status.value if previous_status else None,
            new_status=new_status.value,
            event_metadata=sanitize(metadata or {}),
        )
    )


def _emit_outbox(
    db: Session,
    request: ApprovalRequest,
    *,
    action: ApprovalAction,
    actor: str,
    extra: dict | None = None,
) -> None:
    data = {
        "request_id": request.id,
        "workspace_id": request.workspace_id,
        "source_type": request.source_type,
        "source_id": request.source_id,
        "status": request.status,
        "reviewer_user_ids": list(request.reviewer_user_ids or []),
        "action": action.value,
        "actor_user_id": actor,
        "occurred_at": _now().isoformat(),
    }
    if extra:
        data.update(extra)
    payload = sanitize(data)
    db.add(
        OutboxEvent(
            workspace_id=request.workspace_id,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type=_EVENT_TYPE[action],
            payload=payload,
        )
    )


def _log_state_change(request: ApprovalRequest, action: ApprovalAction, actor: str, result: str) -> None:
    log_event(
        logger,
        "approval.state_change",
        action=action.value,
        result=result,
        workspace_id=request.workspace_id,
        request_id=request.id,
        status=request.status,
        actor_user_id=actor,
    )


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def get_request(db: Session, workspace_id: str, request_id: str) -> ApprovalRequest:
    request = db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
    return request


def list_requests(
    db: Session,
    workspace_id: str,
    *,
    status_filter: ApprovalStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ApprovalRequest], int]:
    base = select(ApprovalRequest).where(ApprovalRequest.workspace_id == workspace_id)
    count_q = select(func.count()).select_from(ApprovalRequest).where(
        ApprovalRequest.workspace_id == workspace_id
    )
    if status_filter is not None:
        base = base.where(ApprovalRequest.status == status_filter.value)
        count_q = count_q.where(ApprovalRequest.status == status_filter.value)

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(base.order_by(ApprovalRequest.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(items), total


# --------------------------------------------------------------------------- #
# Writes (flush only; caller commits)
# --------------------------------------------------------------------------- #
def create_request(
    db: Session, workspace_id: str, principal: Principal, body: CreateApprovalRequest
) -> ApprovalRequest:
    request = ApprovalRequest(
        workspace_id=workspace_id,
        source_type=body.source_type.value,
        source_id=body.source_id,
        title=body.title,
        description=body.description,
        reviewer_user_ids=list(body.reviewer_user_ids),
        status=ApprovalStatus.PENDING.value,
        created_by=principal.user_id,
    )
    db.add(request)
    db.flush()

    _record_audit(
        db,
        request,
        action=ApprovalAction.CREATED,
        actor=principal.user_id,
        previous_status=None,
        new_status=ApprovalStatus.PENDING,
        metadata={"reviewer_count": len(request.reviewer_user_ids or [])},
    )
    _emit_outbox(db, request, action=ApprovalAction.CREATED, actor=principal.user_id)
    _log_state_change(request, ApprovalAction.CREATED, principal.user_id, "created")
    return request


def decide(
    db: Session,
    workspace_id: str,
    request_id: str,
    principal: Principal,
    *,
    action: ApprovalAction,
    comment: str | None = None,
    reason: str | None = None,
) -> ApprovalRequest:
    request = get_request(db, workspace_id, request_id)
    current = ApprovalStatus(request.status)

    if current in FINAL_STATUSES:
        _log_state_change(request, action, principal.user_id, "rejected_final_state")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is already in a final state ('{current.value}') and cannot be changed.",
        )

    new_status = _ACTION_TO_STATUS[action]
    request.status = new_status.value
    request.decided_by = principal.user_id
    request.decision_comment = comment
    request.decision_reason = reason
    request.updated_at = _now()
    db.flush()

    _record_audit(
        db,
        request,
        action=action,
        actor=principal.user_id,
        previous_status=current,
        new_status=new_status,
        metadata={"comment": comment, "reason": reason},
    )
    _emit_outbox(
        db,
        request,
        action=action,
        actor=principal.user_id,
        extra={"comment": comment, "reason": reason},
    )
    _log_state_change(request, action, principal.user_id, "applied")
    return request
