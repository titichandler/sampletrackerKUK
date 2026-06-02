"""SQLite engine, sessions, and persistence helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Generator

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sampletracker.db.models import Base, SampleRequest

# Project root: Sampletracker/ (parent of src/)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = _PROJECT_ROOT / "data" / "sampletracker.db"
REQUEST_NUMBER_PREFIX = "KUK-SR-"


def get_database_path() -> Path:
    """Return the default path to the SQLite database file."""
    return DEFAULT_DATABASE_PATH


def get_engine(db_path: Path | None = None) -> Engine:
    """Create a SQLAlchemy engine for the given SQLite file."""
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.resolve().as_posix()}"
    return create_engine(url, echo=False)


def migrate_schema(engine: Engine) -> None:
    """Apply lightweight schema updates for existing SQLite databases."""
    inspector = inspect(engine)
    if "sample_requests" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("sample_requests")}
    needs_email = "email" not in columns
    needs_request_number = "request_number" not in columns
    due_date_column = columns.get("due_date")
    needs_nullable_due_date = bool(
        due_date_column is not None and not due_date_column.get("nullable", True)
    )

    with engine.begin() as connection:
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
                        request_origin, email, created_at
                    )
                    SELECT
                        id, '', formula_code, formula_name, num_samples, due_date,
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


def create_database(db_path: Path | None = None) -> Path:
    """Create the SQLite file and all tables defined in models."""
    path = db_path or get_database_path()
    engine = get_engine(path)
    Base.metadata.create_all(engine)
    migrate_schema(engine)
    engine.dispose()
    return path.resolve()


# Reused session factory (one engine per process).
_session_factory: sessionmaker[Session] | None = None


def get_session_factory(db_path: Path | None = None) -> sessionmaker[Session]:
    """Return a configured SQLAlchemy sessionmaker bound to the SQLite engine."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine(db_path)
        _session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
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
        "request_origin": record.request_origin,
        "email": record.email,
        "created_at": record.created_at.isoformat(),
    }


def save_sample_request(
    formula_code: str,
    formula_name: str,
    num_samples: int,
    request_origin: str,
    email: str,
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
                request_origin=item["request_origin"],
                email=item["email"],
            )
            session.add(record)
            records.append(record)
        session.flush()
        for record in records:
            session.refresh(record)
        return [_record_to_dict(record) for record in records]
