"""Outbox dispatcher: publishes unpublished outbox rows to the event bus.

Called best-effort right after a state-changing request commits. Because rows are
only marked published after a successful publish, an in-flight failure simply
leaves them for the next dispatch (at-least-once delivery). In production this
same routine would run on a background worker / poller.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.events.bus import EventPublisher, event_bus
from app.models.outbox import OutboxEvent

logger = logging.getLogger("app.events")


def dispatch_pending(db: Session, publisher: EventPublisher | None = None, limit: int = 100) -> int:
    publisher = publisher or event_bus
    rows = (
        db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        )
        .scalars()
        .all()
    )

    published = 0
    for row in rows:
        event = {
            "id": row.id,
            "event_type": row.event_type,
            "aggregate_type": row.aggregate_type,
            "aggregate_id": row.aggregate_id,
            "workspace_id": row.workspace_id,
            "occurred_at": row.created_at.isoformat() if row.created_at else None,
            "data": row.payload,
        }
        try:
            publisher.publish(event)
            row.published_at = datetime.now(timezone.utc)
            published += 1
        except Exception:  # pragma: no cover - defensive; keep request succeeding
            log_event(logger, "domain.event.publish_failed", event_id=row.id, event_type=row.event_type)
            db.rollback()
            return published

    if published:
        db.commit()
    return published
