from tests.helpers import auth_headers, base_url, create_request, sample_payload


def test_create_returns_201_and_pending(client):
    resp = create_request(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]
    assert body["workspaceId"] == "ws_1"
    assert body["status"] == "pending"
    assert body["sourceType"] == "publication"
    assert body["sourceId"] == "pub_123"
    assert body["reviewerUserIds"] == ["usr_1", "usr_2"]
    assert body["createdBy"] == "usr_admin"
    assert body["decidedBy"] is None


def test_create_invalid_source_type_is_422(client):
    resp = create_request(client, payload=sample_payload(sourceType="banana"))
    assert resp.status_code == 422


def test_create_missing_title_is_422(client):
    payload = sample_payload()
    del payload["title"]
    resp = create_request(client, payload=payload)
    assert resp.status_code == 422


def test_get_by_id(client):
    created = create_request(client).json()
    resp = client.get(f"{base_url()}/{created['id']}", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_list_returns_created_requests(client):
    create_request(client, payload=sample_payload(sourceId="pub_a"))
    create_request(client, payload=sample_payload(sourceId="pub_b"))
    resp = client.get(base_url(), headers=auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_filter_by_status(client):
    first = create_request(client).json()
    create_request(client)
    client.post(f"{base_url()}/{first['id']}/approve", json={"comment": "ok"}, headers=auth_headers())

    resp = client.get(f"{base_url()}?status=approved", headers=auth_headers())
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "approved"

    resp = client.get(f"{base_url()}?status=pending", headers=auth_headers())
    assert resp.json()["total"] == 1
