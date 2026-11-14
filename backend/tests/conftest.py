import os
import tempfile
from pathlib import Path

# Set DB URL before app imports create the SQLAlchemy engine.
_TEST_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, Conversion, Exposure, Flag, EventOutbox, EventReceipt

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        with SessionLocal() as session:
            for model in (EventReceipt, EventOutbox, Conversion, Exposure, AuditLog, Flag):
                session.execute(delete(model))
            session.commit()
        yield test_client
