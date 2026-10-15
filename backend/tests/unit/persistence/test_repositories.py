from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, StatementError

from assistant_prof.core.clock import FakeClock
from assistant_prof.persistence.db import Database
from assistant_prof.persistence.models import SettingRow, UtcDateTime, VersionRow
from assistant_prof.persistence.repositories import (
    DocumentRepository,
    JsonValue,
    SettingsRepository,
    VersionRepository,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


# Settings


def test_unknown_setting_returns_the_default(database: Database, clock: FakeClock) -> None:
    with database.session() as session:
        settings = SettingsRepository(session, clock)
        assert settings.get("missing") is None
        assert settings.get("missing", default=7) == 7


def test_settings_round_trip_json_values(database: Database, clock: FakeClock) -> None:
    values: dict[str, JsonValue] = {
        "chain": ["a", "b"],
        "limits": {"jour": 1200, "ratio": 0.5},
        "voice": True,
        "name": "Mme Dupont",
    }
    with database.session() as session:
        settings = SettingsRepository(session, clock)
        for key, value in values.items():
            settings.set(key, value)
    with database.session() as session:
        assert SettingsRepository(session, clock).all() == dict(sorted(values.items()))


def test_setting_overwrite_replaces_value_and_time(database: Database, clock: FakeClock) -> None:
    with database.session() as session:
        SettingsRepository(session, clock).set("retention_days", 30)
    clock.advance(60)
    with database.session() as session:
        SettingsRepository(session, clock).set("retention_days", 45)
    with database.session() as session:
        row = session.get(SettingRow, "retention_days")
        assert row is not None
        assert row.value == 45
        assert row.updated_at == START + timedelta(seconds=60)


# Documents


def test_document_add_and_get(database: Database, clock: FakeClock) -> None:
    with database.session() as session:
        added = DocumentRepository(session, clock).add("Contrôle 3e.docx")
    with database.session() as session:
        documents = DocumentRepository(session, clock)
        assert documents.get(added.id) == added
        assert documents.get("unknown") is None
    assert added.name == "Contrôle 3e.docx"
    assert added.created_at == added.updated_at == START
    assert added.head_version_id is None


def test_list_recent_orders_by_last_update(database: Database, clock: FakeClock) -> None:
    with database.session() as session:
        documents = DocumentRepository(session, clock)
        first = documents.add("a")
        clock.advance(1)
        second = documents.add("b")
        clock.advance(1)
        VersionRepository(session, clock).add(first.id)  # a new version touches the document
    with database.session() as session:
        recent = DocumentRepository(session, clock).list_recent()
        assert [document.id for document in recent] == [first.id, second.id]
        assert DocumentRepository(session, clock).list_recent(limit=1)[0].id == first.id


def test_set_head_to_own_version_and_back_to_none(database: Database, clock: FakeClock) -> None:
    with database.session() as session:
        documents = DocumentRepository(session, clock)
        document = documents.add("a")
        version = VersionRepository(session, clock).add(document.id)
        assert documents.set_head(document.id, version.id).head_version_id == version.id
        assert documents.set_head(document.id, None).head_version_id is None


def test_set_head_refuses_a_foreign_version_and_unknown_document(
    database: Database, clock: FakeClock
) -> None:
    with database.session() as session:
        documents = DocumentRepository(session, clock)
        mine, other = documents.add("a"), documents.add("b")
        foreign = VersionRepository(session, clock).add(other.id)
        with pytest.raises(ValueError, match="does not belong"):
            documents.set_head(mine.id, foreign.id)
        with pytest.raises(ValueError, match="does not belong"):
            documents.set_head(mine.id, "unknown")
        with pytest.raises(LookupError):
            documents.set_head("unknown", None)


def test_deleting_a_document_with_a_head_removes_its_versions(
    database: Database, clock: FakeClock
) -> None:
    with database.session() as session:
        documents = DocumentRepository(session, clock)
        versions = VersionRepository(session, clock)
        document = documents.add("a")
        v1 = versions.add(document.id)
        v2 = versions.add(document.id, parent_id=v1.id)
        documents.set_head(document.id, v2.id)
        kept = documents.add("b")
        versions.add(kept.id)
    with database.session() as session:  # commits: no foreign key error
        assert DocumentRepository(session, clock).delete(document.id) is True
    with database.session() as session:
        assert DocumentRepository(session, clock).get(document.id) is None
        assert VersionRepository(session, clock).list_for_document(document.id) == []
        assert len(VersionRepository(session, clock).list_for_document(kept.id)) == 1
        assert DocumentRepository(session, clock).delete(document.id) is False


def test_deleting_a_version_clears_the_head_and_child_parent_links(
    database: Database, clock: FakeClock
) -> None:
    with database.session() as session:
        documents = DocumentRepository(session, clock)
        versions = VersionRepository(session, clock)
        document = documents.add("a")
        v1 = versions.add(document.id)
        v2 = versions.add(document.id, parent_id=v1.id)
        documents.set_head(document.id, v1.id)
    with database.session() as session:
        session.execute(delete(VersionRow).where(VersionRow.id == v1.id))
    with database.session() as session:
        assert DocumentRepository(session, clock).get(document.id) == document  # head cleared
        child = VersionRepository(session, clock).get(v2.id)
        assert child is not None
        assert child.parent_id is None


# Versions


def test_versions_are_numbered_per_document(database: Database, clock: FakeClock) -> None:
    with database.session() as session:
        documents = DocumentRepository(session, clock)
        versions = VersionRepository(session, clock)
        a, b = documents.add("a"), documents.add("b")
        numbers = [versions.add(a.id).number for _ in range(3)]
        assert numbers == [1, 2, 3]
        assert versions.add(b.id).number == 1


def test_version_fields_round_trip(database: Database, clock: FakeClock) -> None:
    operations = [{"op": "set_bold", "ids": ["p1"], "value": True}]
    with database.session() as session:
        document = DocumentRepository(session, clock).add("a")
        versions = VersionRepository(session, clock)
        first = versions.add(document.id)
        clock.advance(5)
        second = versions.add(
            document.id,
            parent_id=first.id,
            instruction="Mets le titre en gras",
            operations=operations,
            model_used="fake",
        )
    with database.session() as session:
        versions = VersionRepository(session, clock)
        assert versions.get(second.id) == second
        assert versions.get("unknown") is None
        assert versions.list_for_document(document.id) == [first, second]
    assert second.parent_id == first.id
    assert second.operations == operations
    assert second.created_at == START + timedelta(seconds=5)
    assert second.created_at.tzinfo is UTC


def test_version_of_unknown_document_violates_the_foreign_key(
    database: Database, clock: FakeClock
) -> None:
    with pytest.raises(IntegrityError), database.session() as session:
        VersionRepository(session, clock).add("unknown")


# Time stamps


def test_times_are_stored_in_utc_and_returned_aware(database: Database) -> None:
    paris = timezone(timedelta(hours=2))
    clock = FakeClock(datetime(2026, 6, 1, 14, 0, tzinfo=paris))
    with database.session() as session:
        SettingsRepository(session, clock).set("k", 1)
    with database.session() as session:
        stored = session.get(SettingRow, "k")
        assert stored is not None
        assert stored.updated_at == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
        assert stored.updated_at.tzinfo is UTC


def test_naive_datetimes_are_refused(database: Database) -> None:
    def add_naive() -> None:
        with database.session() as session:
            session.add(SettingRow(key="k", value=1, updated_at=datetime(2026, 1, 1)))

    with pytest.raises(StatementError, match="naive datetime"):
        add_naive()
    with database.session() as session:
        assert session.scalars(select(SettingRow)).all() == []


def test_null_datetimes_pass_through(database: Database) -> None:
    column_type = UtcDateTime()
    dialect = database.engine.dialect
    assert column_type.process_bind_param(None, dialect) is None
    assert column_type.process_result_value(None, dialect) is None
