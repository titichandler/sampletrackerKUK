"""Database engine, sessions, and persistence (SQLite locally, Postgres on Streamlit Cloud)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Generator

from sampletracker.dates import format_display_date, format_display_datetime

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sampletracker.db.models import Base, SampleRequest

# Project root: Sampletracker/ (parent of src/)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = _PROJECT_ROOT / "data" / "sampletracker.db"
REQUEST_NUMBER_PREFIX = "KUK-SR-"

_session_factory: sessionmaker[Session] | None = None
_bound_engine_url: str | None = None


def resolve_database_url() -> str | None:
    """Read DATABASE_URL from environment or Streamlit secrets (cloud)."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url

    try:
        import streamlit as st

        if "DATABASE_URL" in st.secrets:
            secret_url = str(st.secrets["DATABASE_URL"]).strip()
            if secret_url:
                return secret_url
    except Exception:
        pass

    return None


def uses_cloud_database() -> bool:
    """True when DATABASE_URL is set (Neon / Postgres)."""
    return resolve_database_url() is not None


def get_database_path() -> Path:
    """Return the default path to the local SQLite database file."""
    return DEFAULT_DATABASE_PATH


def get_engine(db_path: Path | None = None) -> Engine:
    """Create a SQLAlchemy engine (Postgres if DATABASE_URL is set, else SQLite)."""
    database_url = resolve_database_url()
    if database_url:
        return create_engine(database_url, echo=False)

    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sqlite_url = f"sqlite:///{path.resolve().as_posix()}"
    return create_engine(sqlite_url, echo=False)


def _is_sqlite_engine(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


def _add_destination_column(connection: Any, dialect: str) -> None:
    if dialect == "postgresql":
        connection.execute(
            text(
                "ALTER TABLE sample_requests "
                "ADD COLUMN IF NOT EXISTS destination VARCHAR(255) NOT NULL DEFAULT ''"
            )
        )
    else:
        connection.execute(
            text(
                "ALTER TABLE sample_requests "
                "ADD COLUMN destination VARCHAR(255) NOT NULL DEFAULT ''"
            )
        )


def migrate_schema(engine: Engine) -> None:
    """Apply lightweight schema updates for existing databases."""
    inspector = inspect(engine)
    if "sample_requests" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("sample_requests")}
    needs_destination = "destination" not in columns

    if not _is_sqlite_engine(engine):
        if needs_destination:
            with engine.begin() as connection:
                _add_destination_column(connection, engine.dialect.name)
        return

    needs_email = "email" not in columns
    needs_request_number = "request_number" not in columns
    due_date_column = columns.get("due_date")
    needs_nullable_due_date = bool(
        due_date_column is not None and not due_date_column.get("nullable", True)
    )

    with engine.begin() as connection:
        if needs_destination:
            _add_destination_column(connection, "sqlite")

        if needs_email:
            connection.execute(
                text(
                    "ALTER TABLE sample_requests "
                    "ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT ''"
                )
            )

        if needs_request_number:
            connection.execute(
                text(
                    "ALTER TABLE sample_requests "
                    "ADD COLUMN request_number VARCHAR(12) NOT NULL DEFAULT ''"
                )
            )

        if needs_nullable_due_date:
            connection.execute(
                text(
                    """
                    CREATE TABLE sample_requests_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_number VARCHAR(12) NOT NULL DEFAULT '',
                        formula_code VARCHAR(64) NOT NULL,
                        formula_name VARCHAR(255) NOT NULL,
                        num_samples INTEGER NOT NULL,
                        due_date DATE,
                        destination VARCHAR(255) NOT NULL DEFAULT '',
                        request_origin VARCHAR(255) NOT NULL,
                        email VARCHAR(255) NOT NULL DEFAULT '',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO sample_requests_new (
                        id, request_number, formula_code, formula_name, num_samples, due_date,
                        destination, request_origin, email, created_at
                    )
                    SELECT
                        id, '', formula_code, formula_name, num_samples, due_date,
                        COALESCE(destination, ''),
                        request_origin,
                        COALESCE(email, ''),
                        created_at
                    FROM sample_requests
                    """
                )
            )
            connection.execute(text("DROP TABLE sample_requests"))
            connection.execute(
                text("ALTER TABLE sample_requests_new RENAME TO sample_requests")
            )


def ensure_schema(db_path: Path | None = None) -> None:
    """Create tables if missing; apply SQLite-only column migrations."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    migrate_schema(engine)


def create_database(db_path: Path | None = None) -> str:
    """Create tables. Returns DATABASE_URL or local SQLite path."""
    ensure_schema(db_path)
    engine = get_engine(db_path)
    engine.dispose()

    database_url = resolve_database_url()
    if database_url:
        return database_url
    return str((db_path or get_database_path()).resolve())


def get_session_factory(db_path: Path | None = None) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the active database engine."""
    global _session_factory, _bound_engine_url

    engine = get_engine(db_path)
    engine_url = str(engine.url)
    if _session_factory is None or _bound_engine_url != engine_url:
        _session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        _bound_engine_url = engine_url
    return _session_factory


@contextmanager
def get_session(db_path: Path | None = None) -> Generator[Session, None, None]:
    """Open a database session; commit on success, rollback on error, always close."""
    session = get_session_factory(db_path)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _parse_request_number_suffix(value: str) -> int | None:
    """Return the numeric suffix from KUK-SR-XXXX, or None if invalid."""
    if not value.startswith(REQUEST_NUMBER_PREFIX):
        return None
    suffix = value[len(REQUEST_NUMBER_PREFIX) :]
    if len(suffix) == 4 and suffix.isdigit():
        return int(suffix)
    return None


def allocate_next_request_number(session: Session) -> str:
    """Generate the next request number (KUK-SR-0001, KUK-SR-0002, ...)."""
    existing_numbers = session.scalars(
        select(SampleRequest.request_number).where(SampleRequest.request_number != "")
    ).all()
    highest = 0
    for number in existing_numbers:
        parsed = _parse_request_number_suffix(number)
        if parsed is not None:
            highest = max(highest, parsed)
    return f"{REQUEST_NUMBER_PREFIX}{highest + 1:04d}"


def _record_to_dict(record: SampleRequest) -> dict[str, Any]:
    """Convert a SampleRequest ORM row to a JSON-friendly dict."""
    return {
        "id": record.id,
        "request_number": record.request_number,
        "formula_code": record.formula_code,
        "formula_name": record.formula_name,
        "num_samples": record.num_samples,
        "due_date": record.due_date.isoformat() if record.due_date else None,
        "due_date_formatted": format_display_date(record.due_date),
        "due_date_display": format_display_date(record.due_date),
        "destination": record.destination,
        "request_origin": record.request_origin,
        "email": record.email,
        "created_at": record.created_at.isoformat(),
        "created_at_formatted": format_display_datetime(record.created_at),
    }


def save_sample_request(
    formula_code: str,
    formula_name: str,
    num_samples: int,
    request_origin: str,
    email: str,
    destination: str,
    due_date: date | None = None,
) -> dict[str, Any]:
    """Insert one row into sample_requests and return saved values."""
    return save_sample_requests(
        [
            {
                "formula_code": formula_code,
                "formula_name": formula_name,
                "num_samples": num_samples,
                "due_date": due_date,
                "destination": destination,
                "request_origin": request_origin,
                "email": email,
            }
        ]
    )[0]


def save_sample_requests(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Insert multiple rows in one transaction; return all saved records."""
    with get_session() as session:
        request_number = allocate_next_request_number(session)
        records: list[SampleRequest] = []
        for item in items:
            record = SampleRequest(
                request_number=request_number,
                formula_code=item["formula_code"],
                formula_name=item["formula_name"],
                num_samples=item["num_samples"],
                due_date=item.get("due_date"),
                destination=item["destination"],
                request_origin=item["request_origin"],
                email=item["email"],
            )
            session.add(record)
            records.append(record)
        session.flush()
        for record in records:
            session.refresh(record)
        return [_record_to_dict(record) for record in records]
