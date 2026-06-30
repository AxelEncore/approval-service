"""Verify the Alembic migrations build the full schema from scratch on SQLite."""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

EXPECTED_TABLES = {
    "approval_requests",
    "approval_events",
    "outbox_events",
    "idempotency_keys",
}


def test_alembic_upgrade_head_creates_all_tables(tmp_path):
    db_path = tmp_path / "migrated.db"
    url = f"sqlite:///{db_path.as_posix()}"

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert EXPECTED_TABLES.issubset(tables)
    assert "alembic_version" in tables


def test_alembic_downgrade_base(tmp_path):
    db_path = tmp_path / "migrated.db"
    url = f"sqlite:///{db_path.as_posix()}"

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert EXPECTED_TABLES.isdisjoint(tables)
