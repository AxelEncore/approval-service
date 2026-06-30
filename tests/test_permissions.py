from tests.helpers import auth_headers, base_url, create_request, sample_payload


def test_missing_auth_headers_is_401(client):
    resp = client.get(base_url(), headers={})
    assert resp.status_code == 401


def test_create_requires_create_permission(client):
    resp = client.post(
        base_url(), json=sample_payload(), headers=auth_headers(perms="approval:read")
    )
    assert resp.status_code == 403


def test_read_requires_read_permission(client):
    resp = client.get(base_url(), headers=auth_headers(perms="approval:create"))
    assert resp.status_code == 403


def test_decide_requires_decide_permission(client):
    created = create_request(client).json()
    resp = client.post(
        f"{base_url()}/{created['id']}/approve",
        json={"comment": "x"},
        headers=auth_headers(perms="approval:read"),
    )
    assert resp.status_code == 403


def test_cancel_requires_cancel_permission(client):
    created = create_request(client).json()
    # Has decide but not cancel.
    resp = client.post(
        f"{base_url()}/{created['id']}/cancel",
        json={"reason": "x"},
        headers=auth_headers(perms="approval:read,approval:decide"),
    )
    assert resp.status_code == 403


def test_decide_permission_is_not_cancel(client):
    """approve/reject use approval:decide; cancel needs approval:cancel."""
    created = create_request(client).json()
    resp = client.post(
        f"{base_url()}/{created['id']}/approve",
        json={"comment": "x"},
        headers=auth_headers(perms="approval:decide"),
    )
    assert resp.status_code == 200
