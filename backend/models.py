"""SQLAlchemy ORM models for FireScope application and workflow metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MatchingJob(Base):
    """Tracks asynchronous or scheduled sensor matching jobs."""

    __tablename__ = "matching_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    profile_id: Mapped[str] = mapped_column(String(16), default="A")

    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)

    modis_rows_processed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    viirs_rows_processed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    candidate_edges_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    output_dir: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ReviewAnnotation(Base):
    """Expert annotations for review sample candidate pairs."""

    __tablename__ = "review_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_pair_id: Mapped[str] = mapped_column(String(128), index=True)
    modis_row_id: Mapped[str] = mapped_column(String(64), index=True)
    viirs_row_id: Mapped[str] = mapped_column(String(64), index=True)

    adjudication: Mapped[str] = mapped_column(String(32))  # MATCH, NON_MATCH, UNCERTAIN
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SavedSetting(Base):
    """Key-value store for mutable user/app settings."""

    __tablename__ = "saved_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
