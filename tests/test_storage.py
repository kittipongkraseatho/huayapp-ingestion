from datetime import date, datetime, timezone
import sqlite3

import pytest

from huayapp_scraper.config import Config
from huayapp_scraper.models import LotteryResult, PrizeResult
from huayapp_scraper.storage import SQLiteStore, open_store


def make_result(first="012345", *, prize_count=True):
    prizes = [PrizeResult("รางวัลที่ 1", [first]), PrizeResult("2 ตัวล่าง", ["07"])]
    if not prize_count:
        prizes = prizes[:1]
    return LotteryResult(
        source="huayapp.com",
        lottery_id="100",
        lottery_name="รัฐบาลไทย",
        category="หวยทางการ",
        result_date=date(2026, 10, 1),
        result_time=None,
        round=None,
        prizes=prizes,
        status="published",
        scraped_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
        source_url="https://huayapp.com/",
    )


def test_sqlite_store_is_idempotent_and_reconstructs_results(tmp_path):
    store = SQLiteStore(tmp_path / "results.db")

    assert store.upsert(make_result()) is True
    assert store.upsert(make_result()) is False
    rows = store.list_results()

    assert len(rows) == 1
    assert rows[0].prizes[0].numbers == ["012345"]
    assert rows[0].prizes[1].numbers == ["07"]


def test_published_result_is_not_overwritten_by_incomplete_result(tmp_path):
    store = SQLiteStore(tmp_path / "results.db")
    store.upsert(make_result())

    with pytest.raises(ValueError, match="incomplete"):
        store.upsert(make_result("999999", prize_count=False))

    assert store.list_results()[0].prizes[0].numbers == ["012345"]


def test_normalized_source_fields_round_trip_through_storage(tmp_path):
    store = SQLiteStore(tmp_path / "results.db")
    result = make_result()
    result = LotteryResult(
        **{
            **result.__dict__,
            "source_item_id": "thai-gov-1",
            "country": "TH",
            "metadata": {"open": "1432.50"},
        }
    )

    assert store.upsert(result) is True
    stored = store.list_results()[0]

    assert stored.source_item_id == "thai-gov-1"
    assert stored.country == "TH"
    assert stored.metadata == {"open": "1432.50"}


def test_old_schema_is_migrated_without_touching_legacy_tables(tmp_path):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE yiki_results (round TEXT PRIMARY KEY, time TEXT, top3 TEXT, bot2 TEXT);
        CREATE TABLE stocks_results (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, date TEXT, top3 TEXT, bot2 TEXT, open TEXT, close TEXT);
        CREATE TABLE lottery_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            lottery_id TEXT NOT NULL,
            lottery_name TEXT NOT NULL,
            category TEXT NOT NULL,
            result_date TEXT NOT NULL,
            result_time TEXT,
            round TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_text TEXT,
            UNIQUE(source, lottery_id, result_date, round)
        );
        CREATE TABLE lottery_prizes (
            result_id INTEGER NOT NULL,
            prize_name TEXT NOT NULL,
            numbers_json TEXT NOT NULL,
            PRIMARY KEY(result_id, prize_name)
        );
        """
    )
    connection.close()

    store = SQLiteStore(database)
    columns = {row[1] for row in store.connection.execute("PRAGMA table_info(lottery_results)")}
    tables = {
        row[0]
        for row in store.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert {"source_item_id", "country", "metadata_json"}.issubset(columns)
    assert "lottery_sources" in tables
    assert {"yiki_results", "stocks_results"}.issubset(tables)


def test_open_store_defaults_to_sqlite(tmp_path):
    db_path = tmp_path / "test.db"
    config = Config(database_path=db_path)

    store = open_store(config)
    try:
        assert isinstance(store, SQLiteStore)
        assert store.path == db_path
    finally:
        store.close()


def test_open_store_picks_postgres_when_database_url_set(tmp_path):
    config = Config(
        database_path=tmp_path / "ignored.db",
        database_url="postgres://user:pass@localhost:5432/dbname",
    )

    # PostgresStore would try to open a real connection in its ctor
    # (which would fail without a running PostgreSQL). Patch the
    # import path used inside ``open_store`` so the test only verifies
    # the factory's class selection.
    import huayapp_scraper.postgres_store as pg_module

    class FakePostgresStore:
        def __init__(self, url):
            self.url = url

        def upsert(self, result):  # pragma: no cover - not exercised
            return False

        def list_results(self, lottery_id=None):  # pragma: no cover
            return []

        def upsert_source_state(self, source_id, **kwargs):  # pragma: no cover
            pass

        def list_source_states(self):  # pragma: no cover
            return []

        def stats(self):  # pragma: no cover
            return {}

        def close(self):  # pragma: no cover
            pass

    import pytest

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(pg_module, "PostgresStore", FakePostgresStore)

        store = open_store(config)
        try:
            assert isinstance(store, FakePostgresStore)
            assert store.url == "postgres://user:pass@localhost:5432/dbname"
        finally:
            store.close()
    finally:
        monkey.undo()
