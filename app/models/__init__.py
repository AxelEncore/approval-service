"""SQLAlchemy models.

Importing this package ensures every model is registered on ``Base.metadata``
(used by Alembic's autogenerate / migrations and by the test-suite's
``create_all``).
"""
from app.core.database import Base
from app.models.approval import ApprovalEvent, ApprovalRequest
from app.models.idempotency import IdempotencyKey
from app.models.outbox import OutboxEvent

__all__ = [
    "Base",
    "ApprovalRequest",
    "ApprovalEvent",
    "OutboxEvent",
    "IdempotencyKey",
]
