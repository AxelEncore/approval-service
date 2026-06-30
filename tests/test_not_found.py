from tests.helpers import auth_headers, base_url


def test_get_missing_request_is_404(client):
    resp = client.get(f"{base_url()}/does-not-exist", headers=auth_headers())
    assert resp.status_code == 404


def test_approve_missing_request_is_404(client):
    resp = client.post(
        f"{base_url()}/does-not-exist/approve", json={"comment": "x"}, headers=auth_headers()
    )
    assert resp.status_code == 404


def test_reject_missing_request_is_404(client):
    resp = client.post(
        f"{base_url()}/does-not-exist/reject", json={"reason": "x"}, headers=auth_headers()
    )
    assert resp.status_code == 404
