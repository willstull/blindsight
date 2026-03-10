"""Tests for case store lifecycle and CRUD."""
import pytest

from tests.conftest import get_test_logger
from src.services.case.store import open_case_db, ensure_schema, create_case, get_case, CURRENT_SCHEMA_VERSION, _verified_paths


@pytest.fixture
def bare_case_db(tmp_path):
    """Open a fresh case DB without creating a case record."""
    logger = get_test_logger()
    result = open_case_db(logger, tmp_path / "test.duckdb")
    assert result.is_ok()
    conn = result.ok()
    yield conn
    conn.close()


class TestEnsureSchema:
    def test_creates_all_tables(self, bare_case_db):
        tables = bare_case_db.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY table_name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        expected = [
            "assumptions", "cases", "claims", "coverage_reports",
            "entities", "evidence_items", "events", "hypotheses",
            "relationships", "schema_migrations", "tool_calls",
        ]
        for name in expected:
            assert name in table_names, f"Missing table: {name}"

    def test_records_migration_version(self, bare_case_db):
        row = bare_case_db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        assert row[0] == CURRENT_SCHEMA_VERSION

    def test_idempotent_on_reopen(self, tmp_path):
        logger = get_test_logger()
        db_path = tmp_path / "reopen.duckdb"
        # First open
        r1 = open_case_db(logger, db_path)
        assert r1.is_ok()
        r1.ok().close()
        # Second open -- should not fail
        r2 = open_case_db(logger, db_path)
        assert r2.is_ok()
        version = r2.ok().execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION
        r2.ok().close()

    def test_ensure_schema_returns_version(self, tmp_path):
        import duckdb
        logger = get_test_logger()
        conn = duckdb.connect(str(tmp_path / "version.duckdb"))
        result = ensure_schema(logger, conn)
        assert result.is_ok()
        assert result.ok() == CURRENT_SCHEMA_VERSION
        conn.close()

    def test_schema_cache_skips_migration_on_reopen(self, tmp_path, monkeypatch):
        """Second open_case_db on same path should skip ensure_schema."""
        logger = get_test_logger()
        db_path = tmp_path / "cached.duckdb"

        # Clear cache to ensure clean state
        _verified_paths.discard(str(db_path))

        call_count = 0
        original_ensure = ensure_schema

        def counting_ensure(log, conn):
            nonlocal call_count
            call_count += 1
            return original_ensure(log, conn)

        monkeypatch.setattr("src.services.case.store.ensure_schema", counting_ensure)

        # First open -- should call ensure_schema
        r1 = open_case_db(logger, db_path)
        assert r1.is_ok()
        r1.ok().close()
        assert call_count == 1

        # Second open -- should skip ensure_schema (cached)
        r2 = open_case_db(logger, db_path)
        assert r2.is_ok()
        r2.ok().close()
        assert call_count == 1  # no additional call


class TestCreateCase:
    def test_create_and_get_case(self, bare_case_db):
        logger = get_test_logger()
        result = create_case(logger, bare_case_db, "case-001", "Test incident", tlp="AMBER", severity="sev1")
        assert result.is_ok()
        case = result.ok()
        assert case["id"] == "case-001"
        assert case["title"] == "Test incident"
        assert case["status"] == "new"
        assert case["severity"] == "sev1"
        assert case["tlp"] == "AMBER"

    def test_create_case_with_tags(self, bare_case_db):
        logger = get_test_logger()
        result = create_case(logger, bare_case_db, "case-002", "Tagged", tags=["phishing", "priority"])
        assert result.is_ok()
        case = result.ok()
        assert case["tags"] == ["phishing", "priority"]

    def test_create_case_defaults(self, bare_case_db):
        logger = get_test_logger()
        result = create_case(logger, bare_case_db, "case-003", "Defaults")
        assert result.is_ok()
        case = result.ok()
        assert case["tlp"] == "GREEN"
        assert case["severity"] == "sev3"
        assert case["tags"] == []

    def test_duplicate_case_id_fails(self, bare_case_db):
        logger = get_test_logger()
        create_case(logger, bare_case_db, "case-dup", "First")
        result = create_case(logger, bare_case_db, "case-dup", "Second")
        assert result.is_err()

    def test_get_case_not_found(self, bare_case_db):
        logger = get_test_logger()
        result = get_case(logger, bare_case_db, "nonexistent")
        assert result.is_ok()
        assert result.ok() is None

    def test_case_timestamps_are_strings(self, bare_case_db):
        logger = get_test_logger()
        create_case(logger, bare_case_db, "case-ts", "Timestamps")
        result = get_case(logger, bare_case_db, "case-ts")
        case = result.ok()
        assert isinstance(case["created_at"], str)
        assert isinstance(case["updated_at"], str)
