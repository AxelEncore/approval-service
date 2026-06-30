"""Shared test helpers."""
from __future__ import annotations

ALL_PERMS = "approval:read,approval:create,approval:decide,approval:cancel"


def auth_headers(workspace="ws_1", user="usr_admin", perms=ALL_PERMS, idempotency_key=None):
    headers = {"X-Workspace-Id": workspace, "X-User-Id": user}
    if perms is not None:
        headers["X-Permissions"] = perms
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def sample_payload(**overrides):
    payload = {
        "sourceType": "publication",
        "sourceId": "pub_123",
        "title": "Instagram reel draft",
        "description": "Needs final approval",
        "reviewerUserIds": ["usr_1", "usr_2"],
    }
    payload.update(overrides)
    return payload


def base_url(workspace="ws_1"):
    return f"/api/v1/workspaces/{workspace}/approval-requests"


def create_request(client, *, workspace="ws_1", payload=None, headers=None, idempotency_key=None):
    headers = headers or auth_headers(workspace=workspace, idempotency_key=idempotency_key)
    return client.post(base_url(workspace), json=payload or sample_payload(), headers=headers)
