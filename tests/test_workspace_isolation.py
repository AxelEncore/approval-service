from tests.helpers import auth_headers, base_url, create_request


def test_other_workspace_cannot_read_request(client):
    created = create_request(client, workspace="ws_1").json()

    # Same path workspace as the caller's token (ws_2) — request belongs to ws_1.
    resp = client.get(f"{base_url('ws_2')}/{created['id']}", headers=auth_headers(workspace="ws_2"))
    assert resp.status_code == 404


def test_token_workspace_must_match_path(client):
    # Token scoped to ws_2 but hitting ws_1's path -> forbidden.
    resp = client.get(base_url("ws_1"), headers=auth_headers(workspace="ws_2"))
    assert resp.status_code == 403


def test_list_is_scoped_to_workspace(client):
    create_request(client, workspace="ws_1")
    create_request(client, workspace="ws_2")

    ws1 = client.get(base_url("ws_1"), headers=auth_headers(workspace="ws_1")).json()
    ws2 = client.get(base_url("ws_2"), headers=auth_headers(workspace="ws_2")).json()
    assert ws1["total"] == 1
    assert ws2["total"] == 1
    assert ws1["items"][0]["workspaceId"] == "ws_1"
    assert ws2["items"][0]["workspaceId"] == "ws_2"


def test_other_workspace_cannot_decide(client):
    created = create_request(client, workspace="ws_1").json()
    # Path ws_1 but token ws_2 -> 403 (mismatch) before any data access.
    resp = client.post(
        f"{base_url('ws_1')}/{created['id']}/approve",
        json={"comment": "x"},
        headers=auth_headers(workspace="ws_2"),
    )
    assert resp.status_code == 403
