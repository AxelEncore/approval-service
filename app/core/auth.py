"""Local auth stub.

A real deployment would validate a signed JWT issued by the platform's identity
service. For local/dev/test we trust three request headers:

    X-User-Id        e.g. usr_1
    X-Workspace-Id   e.g. ws_1
    X-Permissions    comma-separated, e.g. "approval:read,approval:create"

The principal's workspace must match the workspace in the URL path, which is the
first line of defence for workspace isolation (the DB query filter is the second).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Header, HTTPException, Path, status


class Permissions:
    READ = "approval:read"
    CREATE = "approval:create"
    DECIDE = "approval:decide"
    CANCEL = "approval:cancel"


@dataclass
class Principal:
    user_id: str
    workspace_id: str
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission: str) -> bool:
        return permission in self.permissions


def get_principal(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_permissions: str | None = Header(default=None, alias="X-Permissions"),
) -> Principal:
    if not x_user_id or not x_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication headers (X-User-Id / X-Workspace-Id).",
        )
    perms = frozenset(p.strip() for p in (x_permissions or "").split(",") if p.strip())
    return Principal(user_id=x_user_id, workspace_id=x_workspace_id, permissions=perms)


def require_permissions(*required: str):
    """Dependency factory enforcing auth + workspace scope + permissions."""

    from fastapi import Depends

    def dependency(
        workspace_id: str = Path(...),
        principal: Principal = Depends(get_principal),
    ) -> Principal:
        if principal.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace mismatch: token is not scoped to this workspace.",
            )
        missing = [p for p in required if not principal.has(p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission(s): {', '.join(missing)}",
            )
        return principal

    return dependency
