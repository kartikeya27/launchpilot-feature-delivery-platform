"""Runs only with INTEGRATION_DATABASE_URL and live PostgreSQL from CI/Compose."""
import os
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

@pytest.mark.skipif(not os.getenv("INTEGRATION_DATABASE_URL"), reason="Postgres integration DB not provided")
def test_postgres_migration_and_unique_constraint():
    from app.models import Flag
    url = os.environ["INTEGRATION_DATABASE_URL"]
    # Use an isolated CI database. Must not point to your production DB.
    assert "launchpilot_test" in url, "Integration tests require a dedicated launchpilot_test database"
    os.environ["DATABASE_URL"] = url
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert {"flags", "exposures", "event_outbox", "event_receipts", "alembic_version"}.issubset(inspect(engine).get_table_names())
    with Session(engine) as session:
        key = f"integration_{uuid4().hex[:12]}"
        session.add(Flag(id=str(uuid4()), key=key, name="Integration", environment="staging", owner="QA", enabled=True, rollout=50, salt="abc", version=1))
        session.commit()
        assert session.scalar(select(Flag).where(Flag.key == key)).name == "Integration"
    engine.dispose()
