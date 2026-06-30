"""Approval-request HTTP endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Permissions, Principal, require_permissions
from app.core.database import get_db
from app.core.enums import ApprovalAction, ApprovalStatus
from app.events import dispatcher
from app.schemas.approval import (
    ApproveDecision,
    CancelDecision,
    CreateApprovalRequest,
    RejectDecision,
    serialize_request,
)
from app.services import approval_service, idempotency

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/approval-requests", tags=["approval-requests"])


def _decision_response(db: Session, request) -> JSONResponse:
    """Commit, dispatch outbox, and return the serialized request (HTTP 200)."""
    body = serialize_request(request)
    db.commit()
    dispatcher.dispatch_pending(db)
    return JSONResponse(status_code=status.HTTP_200_OK, content=body)


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
@router.post("", status_code=status.HTTP_201_CREATED)
def create_approval_request(
    workspace_id: str,
    body: CreateApprovalRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permissions(Permissions.CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    request_hash = idempotency.hash_payload(body.model_dump(mode="json"))

    if idempotency_key:
        existing = idempotency.find(db, workspace_id, idempotency_key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key already used with a different request body.",
                )
            return JSONResponse(
                status_code=existing.response_status,
                content=existing.response_body,
                headers={"Idempotency-Replayed": "true"},
            )

    request = approval_service.create_request(db, workspace_id, principal, body)
    response_body = serialize_request(request)

    if idempotency_key:
        db.add(
            idempotency.build_record(
                workspace_id=workspace_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=status.HTTP_201_CREATED,
                response_body=response_body,
                request_id=request.id,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        # Concurrent request with the same Idempotency-Key won the race.
        db.rollback()
        if idempotency_key:
            existing = idempotency.find(db, workspace_id, idempotency_key)
            if existing is not None:
                return JSONResponse(
                    status_code=existing.response_status,
                    content=existing.response_body,
                    headers={"Idempotency-Replayed": "true"},
                )
        raise

    dispatcher.dispatch_pending(db)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=response_body)


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #
@router.get("")
def list_approval_requests(
    workspace_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permissions(Permissions.READ)),
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    items, total = approval_service.list_requests(
        db, workspace_id, status_filter=status_filter, limit=limit, offset=offset
    )
    return {
        "items": [serialize_request(item) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{request_id}")
def get_approval_request(
    workspace_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permissions(Permissions.READ)),
) -> dict:
    request = approval_service.get_request(db, workspace_id, request_id)
    return serialize_request(request)


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
@router.post("/{request_id}/approve")
def approve_approval_request(
    workspace_id: str,
    request_id: str,
    body: ApproveDecision | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permissions(Permissions.DECIDE)),
) -> Response:
    comment = body.comment if body else None
    request = approval_service.decide(
        db, workspace_id, request_id, principal, action=ApprovalAction.APPROVED, comment=comment
    )
    return _decision_response(db, request)


@router.post("/{request_id}/reject")
def reject_approval_request(
    workspace_id: str,
    request_id: str,
    body: RejectDecision,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permissions(Permissions.DECIDE)),
) -> Response:
    request = approval_service.decide(
        db, workspace_id, request_id, principal, action=ApprovalAction.REJECTED, reason=body.reason
    )
    return _decision_response(db, request)


@router.post("/{request_id}/cancel")
def cancel_approval_request(
    workspace_id: str,
    request_id: str,
    body: CancelDecision,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permissions(Permissions.CANCEL)),
) -> Response:
    request = approval_service.decide(
        db, workspace_id, request_id, principal, action=ApprovalAction.CANCELLED, reason=body.reason
    )
    return _decision_response(db, request)
