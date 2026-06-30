from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.sanitization import sanitize, sanitize_string
from app.models.approval import ApprovalEvent
from app.models.outbox import OutboxEvent
from tests.helpers import auth_headers, base_url, create_request


def test_sanitize_string_redacts_secrets():
    raw = "ping me at admin@example.com or https://signed.example.com/f?sig=abc123"
    out = sanitize_string(raw)
    assert "admin@example.com" not in out
    assert "https://signed.example.com" not in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_URL]" in out


def test_sanitize_redacts_sensitive_keys():
    out = sanitize({"token": "super-secret", "nested": {"password": "p"}, "ok": "value"})
    assert out["token"] == "[REDACTED]"
    assert out["nested"]["password"] == "[REDACTED]"
    assert out["ok"] == "value"


def test_sanitize_redacts_jwt_and_bearer():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signaturepart"
    out = sanitize_string(f"Authorization: Bearer {jwt}")
    assert jwt not in out
    assert "[REDACTED_TOKEN]" in out


def test_decision_reason_is_sanitized_in_events(client):
    req = create_request(client).json()
    leak = "Contact admin@example.com see https://provider.example.com/blob?token=xyz"
    client.post(f"{base_url()}/{req['id']}/reject", json={"reason": leak}, headers=auth_headers())

    with SessionLocal() as db:
        audit = db.execute(
            select(ApprovalEvent).where(
                ApprovalEvent.request_id == req["id"], ApprovalEvent.action == "rejected"
            )
        ).scalar_one()
        outbox = db.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == req["id"],
                OutboxEvent.event_type == "approval_request.rejected",
            )
        ).scalar_one()

    stored_reason = audit.event_metadata["reason"]
    assert "admin@example.com" not in stored_reason
    assert "https://provider.example.com" not in stored_reason

    event_reason = outbox.payload["reason"]
    assert "admin@example.com" not in event_reason
    assert "https://provider.example.com" not in event_reason
