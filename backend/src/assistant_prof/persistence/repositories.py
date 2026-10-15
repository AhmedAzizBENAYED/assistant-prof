"""Repositories over ``assistant.sqlite`` (ADR-040).

A repository works inside the caller's session (``Database.session()``, the unit of work) and
never commits. It returns frozen records, never ORM objects, so results stay usable once the
session is closed. Timestamps come from the injected clock.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from assistant_prof.core.clock import Clock
from assistant_prof.core.ids import new_uuid
from assistant_prof.persistence.models import DocumentRow, SettingRow, VersionRow

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """An imported document."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    head_version_id: str | None


@dataclass(frozen=True, slots=True)
class VersionRecord:
    """One saved version of a document."""

    id: str
    document_id: str
    parent_id: str | None
    number: int
    instruction: str | None
    operations: list[Any] | None
    model_used: str | None
    created_at: datetime


def _document(row: DocumentRow) -> DocumentRecord:
    return DocumentRecord(row.id, row.name, row.created_at, row.updated_at, row.head_version_id)


def _version(row: VersionRow) -> VersionRecord:
    return VersionRecord(
        row.id,
        row.document_id,
        row.parent_id,
        row.number,
        row.instruction,
        row.operations,
        row.model_used,
        row.created_at,
    )


class SettingsRepository:
    """Application settings as JSON values keyed by name."""

    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def get(self, key: str, default: JsonValue = None) -> JsonValue:
        """Return the value of ``key``, or ``default`` when it is not set."""
        row = self._session.get(SettingRow, key)
        return default if row is None else row.value

    def set(self, key: str, value: JsonValue) -> None:
        """Create or replace ``key``."""
        row = self._session.get(SettingRow, key)
        if row is None:
            self._session.add(SettingRow(key=key, value=value, updated_at=self._clock.now()))
        else:
            row.value = value
            row.updated_at = self._clock.now()
        self._session.flush()

    def all(self) -> dict[str, JsonValue]:
        """Return every setting."""
        rows = self._session.scalars(select(SettingRow).order_by(SettingRow.key))
        return {row.key: row.value for row in rows}


class DocumentRepository:
    """Imported documents and their head version."""

    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def add(self, name: str) -> DocumentRecord:
        """Create a document without any version yet."""
        now = self._clock.now()
        row = DocumentRow(id=new_uuid(), name=name, created_at=now, updated_at=now)
        self._session.add(row)
        self._session.flush()
        return _document(row)

    def get(self, document_id: str) -> DocumentRecord | None:
        """Return the document, or ``None`` if unknown."""
        row = self._session.get(DocumentRow, document_id)
        return None if row is None else _document(row)

    def list_recent(self, limit: int = 20) -> list[DocumentRecord]:
        """Return documents, most recently updated first."""
        rows = self._session.scalars(
            select(DocumentRow).order_by(DocumentRow.updated_at.desc(), DocumentRow.id).limit(limit)
        )
        return [_document(row) for row in rows]

    def set_head(self, document_id: str, version_id: str | None) -> DocumentRecord:
        """Point the document at one of its own versions (or at none).

        Raises ``LookupError`` for an unknown document and ``ValueError`` for a version that
        belongs to another document.
        """
        row = self._session.get(DocumentRow, document_id)
        if row is None:
            raise LookupError(f"unknown document {document_id}")
        if version_id is not None:
            version = self._session.get(VersionRow, version_id)
            if version is None or version.document_id != document_id:
                raise ValueError(f"version {version_id} does not belong to {document_id}")
        row.head_version_id = version_id
        row.updated_at = self._clock.now()
        self._session.flush()
        return _document(row)

    def delete(self, document_id: str) -> bool:
        """Delete the document and, by cascade, its versions. Return whether it existed."""
        result = self._session.execute(delete(DocumentRow).where(DocumentRow.id == document_id))
        return bool(result.rowcount)  # type: ignore[attr-defined]


class VersionRepository:
    """Versions of documents, numbered 1, 2, 3… per document."""

    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def add(
        self,
        document_id: str,
        *,
        parent_id: str | None = None,
        instruction: str | None = None,
        operations: list[Any] | None = None,
        model_used: str | None = None,
    ) -> VersionRecord:
        """Record the next version of ``document_id``; does not move the head.

        An unknown document raises ``sqlalchemy.exc.IntegrityError`` (foreign key).
        """
        last = self._session.scalar(
            select(func.max(VersionRow.number)).where(VersionRow.document_id == document_id)
        )
        now = self._clock.now()
        row = VersionRow(
            id=new_uuid(),
            document_id=document_id,
            parent_id=parent_id,
            number=(last or 0) + 1,
            instruction=instruction,
            operations=operations,
            model_used=model_used,
            created_at=now,
        )
        self._session.add(row)
        self._session.flush()
        self._session.execute(
            update(DocumentRow).where(DocumentRow.id == document_id).values(updated_at=now)
        )
        return _version(row)

    def get(self, version_id: str) -> VersionRecord | None:
        """Return the version, or ``None`` if unknown."""
        row = self._session.get(VersionRow, version_id)
        return None if row is None else _version(row)

    def list_for_document(self, document_id: str) -> list[VersionRecord]:
        """Return the document's versions, oldest first."""
        rows = self._session.scalars(
            select(VersionRow)
            .where(VersionRow.document_id == document_id)
            .order_by(VersionRow.number)
        )
        return [_version(row) for row in rows]
