"""ORM models of ``assistant.sqlite`` (ARCHITECTURE §7.9).

Change the schema only through a new Alembic revision; a test fails when the models and the
migrations disagree.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Dialect,
    ForeignKey,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint names, so SQLite batch migrations can find and alter them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UUID_LENGTH = 36


class UtcDateTime(TypeDecorator[datetime]):
    """Aware UTC datetime. SQLite has no time zones: naive UTC is stored, aware UTC is returned."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Refuse naive datetimes and store UTC without the zone."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime refused: use an aware datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Mark the stored value as UTC."""
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    """Declarative base with the naming convention and the UTC datetime type."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: UtcDateTime()}  # noqa: RUF012  # read by SQLAlchemy


class SettingRow(Base):
    """One application setting; the value is any JSON value."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime]


class DocumentRow(Base):
    """An imported document; ``head_version_id`` is its current version (undo/redo move it)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    head_version_id: Mapped[str | None] = mapped_column(
        # use_alter: documents and versions reference each other.
        ForeignKey("versions.id", ondelete="SET NULL", use_alter=True)
    )


class VersionRow(Base):
    """One saved version ``vNNN.docx`` of a document, with the instruction that produced it."""

    __tablename__ = "versions"
    __table_args__ = (UniqueConstraint("document_id", "number"),)

    id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("versions.id", ondelete="SET NULL"))
    number: Mapped[int]
    instruction: Mapped[str | None] = mapped_column(Text)
    operations: Mapped[list[Any] | None] = mapped_column(JSON)
    model_used: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime]
