"""Idempotency-key handling for unsafe (create) operations."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey


def hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find(db: Session, workspace_id: str, key: str) -> IdempotencyKey | None:
    return db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.workspace_id == workspace_id,
            IdempotencyKey.idempotency_key == key,
        )
    ).scalar_one_or_none()


def build_record(
    workspace_id: str,
    key: str,
    request_hash: str,
    response_status: int,
    response_body: dict,
    request_id: str | None,
) -> IdempotencyKey:
    return IdempotencyKey(
        workspace_id=workspace_id,
        idempotency_key=key,
        request_hash=request_hash,
        response_status=response_status,
        response_body=response_body,
        request_id=request_id,
    )
