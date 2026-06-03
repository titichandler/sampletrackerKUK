"""SQLAlchemy ORM schema for the lab sample request tracker."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class FormulaLibrary(Base):
    """Formula codes and names available for sample requests."""

    __tablename__ = "formula_library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    formula_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    formula_name: Mapped[str] = mapped_column(String(255), nullable=False)


class SampleRequest(Base):
    """Submitted sample requests from the Streamlit form."""

    __tablename__ = "sample_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_number: Mapped[str] = mapped_column(String(12), nullable=False)
    formula_code: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_name: Mapped[str] = mapped_column(String(255), nullable=False)
    num_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    request_origin: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
