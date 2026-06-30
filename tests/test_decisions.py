import pytest

from tests.helpers import auth_headers, base_url, create_request


def _create(client):
    return create_request(client).json()


def test_approve(client):
    req = _create(client)
    resp = client.post(
        f"{base_url()}/{req['id']}/approve", json={"comment": "Approved"}, headers=auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decisionComment"] == "Approved"
    assert body["decidedBy"] == "usr_admin"


def test_approve_without_body(client):
    req = _create(client)
    resp = client.post(f"{base_url()}/{req['id']}/approve", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_reject(client):
    req = _create(client)
    resp = client.post(
        f"{base_url()}/{req['id']}/reject", json={"reason": "Brand tone is wrong"}, headers=auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["decisionReason"] == "Brand tone is wrong"


def test_reject_requires_reason(client):
    req = _create(client)
    resp = client.post(f"{base_url()}/{req['id']}/reject", json={}, headers=auth_headers())
    assert resp.status_code == 422


def test_cancel(client):
    req = _create(client)
    resp = client.post(
        f"{base_url()}/{req['id']}/cancel", json={"reason": "Draft was removed"}, headers=auth_headers()
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.parametrize("second", ["approve", "reject", "cancel"])
def test_double_final_decision_conflicts(client, second):
    req = _create(client)
    client.post(f"{base_url()}/{req['id']}/approve", json={"comment": "ok"}, headers=auth_headers())

    payload = {"comment": "x"} if second == "approve" else {"reason": "x"}
    resp = client.post(f"{base_url()}/{req['id']}/{second}", json=payload, headers=auth_headers())
    assert resp.status_code == 409


def test_rejected_then_cancel_conflicts(client):
    req = _create(client)
    client.post(f"{base_url()}/{req['id']}/reject", json={"reason": "no"}, headers=auth_headers())
    resp = client.post(f"{base_url()}/{req['id']}/cancel", json={"reason": "late"}, headers=auth_headers())
    assert resp.status_code == 409


def test_state_unchanged_after_conflict(client):
    req = _create(client)
    client.post(f"{base_url()}/{req['id']}/approve", json={"comment": "ok"}, headers=auth_headers())
    client.post(f"{base_url()}/{req['id']}/reject", json={"reason": "no"}, headers=auth_headers())
    current = client.get(f"{base_url()}/{req['id']}", headers=auth_headers()).json()
    assert current["status"] == "approved"
    assert current["decisionReason"] is None
