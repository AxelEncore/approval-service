from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.approval import ApprovalEvent
from app.models.outbox import OutboxEvent
from tests.helpers import auth_headers, base_url, create_request


def _events_for(request_id):
    with SessionLocal() as db:
        return db.execute(
            select(ApprovalEvent)
            .where(ApprovalEvent.request_id == request_id)
            .order_by(ApprovalEvent.created_at)
        ).scalars().all()


def _outbox_for(request_id):
    with SessionLocal() as db:
        return db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_id == request_id)
            .order_by(OutboxEvent.created_at)
        ).scalars().all()


def test_create_writes_audit_and_outbox(client):
    req = create_request(client).json()

    events = _events_for(req["id"])
    assert len(events) == 1
    assert events[0].action == "created"
    assert events[0].previous_status is None
    assert events[0].new_status == "pending"
    assert events[0].actor_user_id == "usr_admin"

    outbox = _outbox_for(req["id"])
    assert len(outbox) == 1
    assert outbox[0].event_type == "approval_request.created"


def test_decision_appends_audit_with_before_after(client):
    req = create_request(client).json()
    client.post(f"{base_url()}/{req['id']}/approve", json={"comment": "ok"}, headers=auth_headers())

    events = _events_for(req["id"])
    assert [e.action for e in events] == ["created", "approved"]
    decision = events[-1]
    assert decision.previous_status == "pending"
    assert decision.new_status == "approved"


def test_outbox_events_are_published(client):
    req = create_request(client).json()
    client.post(f"{base_url()}/{req['id']}/reject", json={"reason": "no"}, headers=auth_headers())

    outbox = _outbox_for(req["id"])
    assert {o.event_type for o in outbox} == {
        "approval_request.created",
        "approval_request.rejected",
    }
    # The dispatcher ran after each commit and marked rows published.
    assert all(o.published_at is not None for o in outbox)


def test_failed_decision_writes_no_audit(client):
    req = create_request(client).json()
    client.post(f"{base_url()}/{req['id']}/approve", json={"comment": "ok"}, headers=auth_headers())
    client.post(f"{base_url()}/{req['id']}/reject", json={"reason": "no"}, headers=auth_headers())

    # created + approved only; the rejected attempt 409'd and left no trace.
    events = _events_for(req["id"])
    assert [e.action for e in events] == ["created", "approved"]
