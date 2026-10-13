from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Protocol

from .models import LotteryResult, PrizeResult
from .validator import validate_record


class Store(Protocol):
    """Storage interface implemented by both :class:`SQLiteStore` and
    :class:`PostgresStore`. The factory :func:`open_store` picks one based
    on ``config.database_url`` (preferred) or falls back to the SQLite path
    in ``config.database_path``.
    """

    def upsert(self, result: LotteryResult) -> bool: ...
    def list_results(self, lottery_id: str | None = None) -> list[LotteryResult]: ...
    def upsert_source_state(self, source_id: str, **kwargs) -> None: ...
    def list_source_states(self) -> list[dict]: ...
    def stats(self) -> dict[str, int]: ...
    def close(self) -> None: ...


def open_store(config) -> Store:
    """Open the configured store. ``config.database_url`` selects
    :class:`PostgresStore` when it is a ``postgres://`` (or
    ``postgresql://``) URL; otherwise the local SQLite path from
    ``config.database_path`` is used.
    """
    database_url = getattr(config, "database_url", None)
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        # Import here to keep ``psycopg2`` an optional dependency.
        from .postgres_store import PostgresStore

        return PostgresStore(database_url)
    return SQLiteStore(config.database_path)


# Re-export ``PostgresStore`` lazily via module attribute so tests can
# monkeypatch it without poking the private ``postgres_store`` submodule.
_lazy_postgres = None


def __getattr__(name: str):
    global _lazy_postgres
    if name == "PostgresStore":
        from .postgres_store import PostgresStore

        _lazy_postgres = PostgresStore
        return PostgresStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Store", "SQLiteStore", "PostgresStore", "open_store", "export_csv", "export_json"]


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def result_to_dict(result: LotteryResult) -> dict:
    return asdict(result)


class SQLiteStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS lottery_results (
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
                source_item_id TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(source, lottery_id, result_date, round)
            );
            CREATE TABLE IF NOT EXISTS lottery_prizes (
                result_id INTEGER NOT NULL REFERENCES lottery_results(id) ON DELETE CASCADE,
                prize_name TEXT NOT NULL,
                numbers_json TEXT NOT NULL,
                PRIMARY KEY(result_id, prize_name)
            );
            CREATE TABLE IF NOT EXISTS lottery_sources (
                source_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                country TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unavailable',
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_error TEXT,
                result_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_lottery_results_lookup
                ON lottery_results(lottery_id, result_date, status);
            """
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(lottery_results)")}
        migrations = {
            "source_item_id": "ALTER TABLE lottery_results ADD COLUMN source_item_id TEXT NOT NULL DEFAULT ''",
            "country": "ALTER TABLE lottery_results ADD COLUMN country TEXT NOT NULL DEFAULT ''",
            "metadata_json": "ALTER TABLE lottery_results ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'",
        }
        for column, statement in migrations.items():
            if column not in columns:
                self.connection.execute(statement)
        self.connection.commit()

    def upsert(self, result: LotteryResult) -> bool:
        validation = validate_record(result)
        if not validation.valid:
            raise ValueError("invalid result: " + "; ".join(validation.errors))

        source_item_id = result.source_item_id or result.lottery_id
        key = (result.source, source_item_id, result.result_date.isoformat(), result.round or "")
        existing = self.connection.execute(
            "SELECT id, status FROM lottery_results WHERE source=? AND (source_item_id=? OR (source_item_id='' AND lottery_id=?)) AND result_date=? AND round=?",
            (key[0], key[1], key[1], key[2], key[3]),
        ).fetchone()
        if existing:
            current_count = self.connection.execute(
                "SELECT COUNT(*) AS count FROM lottery_prizes WHERE result_id=?", (existing["id"],)
            ).fetchone()["count"]
            if existing["status"] == "published" and len(result.prizes) < current_count:
                raise ValueError("incomplete result cannot replace a published result")

        values = (
            result.source,
            result.lottery_id,
            result.lottery_name,
            result.category,
            result.result_date.isoformat(),
            result.result_time,
            result.round or "",
            result.status,
            result.scraped_at.isoformat(),
            result.source_url,
            result.source_text,
            source_item_id,
            result.country,
            json.dumps(result.metadata, ensure_ascii=False, sort_keys=True),
        )
        with self.connection:
            if existing:
                self.connection.execute(
                    """UPDATE lottery_results SET lottery_id=?, lottery_name=?, category=?, result_time=?, status=?,
                       scraped_at=?, source_url=?, source_text=?, source_item_id=?, country=?, metadata_json=? WHERE id=?""",
                    (result.lottery_id, result.lottery_name, result.category, result.result_time, result.status,
                     result.scraped_at.isoformat(), result.source_url, result.source_text, source_item_id,
                     result.country, json.dumps(result.metadata, ensure_ascii=False, sort_keys=True), existing["id"]),
                )
                result_id = existing["id"]
                self.connection.execute("DELETE FROM lottery_prizes WHERE result_id=?", (result_id,))
                inserted = False
            else:
                cursor = self.connection.execute(
                    """INSERT INTO lottery_results
                       (source, lottery_id, lottery_name, category, result_date, result_time, round,
                        status, scraped_at, source_url, source_text, source_item_id, country, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                result_id = cursor.lastrowid
                inserted = True

            self.connection.executemany(
                "INSERT INTO lottery_prizes(result_id, prize_name, numbers_json) VALUES (?, ?, ?)",
                [(result_id, prize.prize_name, json.dumps(prize.numbers, ensure_ascii=False)) for prize in result.prizes],
            )
        return inserted

    def list_results(self, lottery_id: str | None = None) -> list[LotteryResult]:
        query = "SELECT * FROM lottery_results"
        args: tuple[str, ...] = ()
        if lottery_id is not None:
            query += " WHERE lottery_id=?"
            args = (lottery_id,)
        query += " ORDER BY result_date DESC, id DESC"
        rows = self.connection.execute(query, args).fetchall()
        results: list[LotteryResult] = []
        for row in rows:
            prize_rows = self.connection.execute(
                "SELECT prize_name, numbers_json FROM lottery_prizes WHERE result_id=? ORDER BY rowid",
                (row["id"],),
            ).fetchall()
            results.append(
                LotteryResult(
                    source=row["source"],
                    lottery_id=row["lottery_id"],
                    lottery_name=row["lottery_name"],
                    category=row["category"],
                    result_date=date.fromisoformat(row["result_date"]),
                    result_time=row["result_time"],
                    round=row["round"] or None,
                    prizes=[PrizeResult(item["prize_name"], json.loads(item["numbers_json"])) for item in prize_rows],
                    status=row["status"],
                    scraped_at=datetime.fromisoformat(row["scraped_at"]),
                    source_url=row["source_url"],
                    source_text=row["source_text"],
                    source_item_id=row["source_item_id"] or row["lottery_id"],
                    country=row["country"] or "",
                    metadata=json.loads(row["metadata_json"] or "{}"),
                )
            )
        return results

    def stats(self) -> dict[str, int]:
        rows = self.connection.execute("SELECT status, COUNT(*) AS count FROM lottery_results GROUP BY status").fetchall()
        return {row["status"]: row["count"] for row in rows}

    def upsert_source_state(
        self,
        source_id: str,
        *,
        name: str,
        country: str,
        category: str,
        url: str,
        enabled: bool,
        status: str,
        last_attempt_at: datetime | str | None = None,
        last_success_at: datetime | str | None = None,
        last_error: str | None = None,
        result_count: int = 0,
    ) -> None:
        def iso(value: datetime | str | None) -> str | None:
            return value.isoformat() if isinstance(value, datetime) else value

        with self.connection:
            self.connection.execute(
                """INSERT INTO lottery_sources
                   (source_id, name, country, category, url, enabled, status,
                    last_attempt_at, last_success_at, last_error, result_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                     name=excluded.name, country=excluded.country, category=excluded.category,
                     url=excluded.url, enabled=excluded.enabled, status=excluded.status,
                     last_attempt_at=excluded.last_attempt_at, last_success_at=excluded.last_success_at,
                     last_error=excluded.last_error, result_count=excluded.result_count""",
                (source_id, name, country, category, url, int(enabled), status,
                 iso(last_attempt_at), iso(last_success_at), last_error, result_count),
            )

    def list_source_states(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM lottery_sources ORDER BY category, name, source_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()


def export_json(results: Iterable[LotteryResult], path: Path | str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([result_to_dict(item) for item in results], ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def export_csv(results: Iterable[LotteryResult], path: Path | str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["source", "lottery_id", "lottery_name", "category", "result_date", "result_time", "round", "status", "scraped_at", "source_url", "prize_name", "number"]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            for prize in result.prizes:
                for number in prize.numbers:
                    writer.writerow({
                        "source": result.source,
                        "lottery_id": result.lottery_id,
                        "lottery_name": result.lottery_name,
                        "category": result.category,
                        "result_date": result.result_date.isoformat(),
                        "result_time": result.result_time or "",
                        "round": result.round or "",
                        "status": result.status,
                        "scraped_at": result.scraped_at.isoformat(),
                        "source_url": result.source_url,
                        "prize_name": prize.prize_name,
                        "number": number,
                    })
