from tests.helpers import auth_headers, base_url, create_request, sample_payload


def test_same_key_same_body_returns_same_request(client):
    first = create_request(client, idempotency_key="key-1")
    second = create_request(client, idempotency_key="key-1")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.headers.get("Idempotency-Replayed") == "true"

    # Only one row actually persisted.
    listing = client.get(base_url(), headers=auth_headers()).json()
    assert listing["total"] == 1


def test_same_key_different_body_conflicts(client):
    create_request(client, idempotency_key="key-2")
    resp = create_request(
        client, idempotency_key="key-2", payload=sample_payload(title="A different title")
    )
    assert resp.status_code == 409


def test_without_key_creates_duplicates(client):
    create_request(client)
    create_request(client)
    listing = client.get(base_url(), headers=auth_headers()).json()
    assert listing["total"] == 2


def test_key_is_scoped_per_workspace(client):
    r1 = create_request(client, workspace="ws_1", idempotency_key="shared")
    r2 = create_request(client, workspace="ws_2", idempotency_key="shared")
    # Same key string, different workspaces -> two independent requests.
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
