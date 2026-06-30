"""In-process event bus.

This is the seam for asynchronous integrations. Business logic only ever calls
``event_bus.publish(event)``; replacing :class:`InProcessEventBus` with a Kafka /
RabbitMQ producer requires no changes to the service layer or the outbox.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from app.core.logging import log_event

logger = logging.getLogger("app.events")

EventHandler = Callable[[dict[str, Any]], None]


class EventPublisher(Protocol):
    def publish(self, event: dict[str, Any]) -> None: ...


class InProcessEventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def publish(self, event: dict[str, Any]) -> None:
        for handler in self._handlers:
            handler(event)


def _logging_handler(event: dict[str, Any]) -> None:
    log_event(
        logger,
        "domain.event.published",
        event_type=event.get("event_type"),
        aggregate_type=event.get("aggregate_type"),
        aggregate_id=event.get("aggregate_id"),
        workspace_id=event.get("workspace_id"),
    )


# Default singleton bus with a logging subscriber. Add real consumers here.
event_bus = InProcessEventBus()
event_bus.subscribe(_logging_handler)
