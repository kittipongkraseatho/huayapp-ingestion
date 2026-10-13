"""PostgreSQL implementation of :class:`~huayapp_scraper.storage.Store`.

Used when ``DATABASE_URL`` is set to a ``postgres://`` (or
``postgresql://``) URL — typically on Railway, Render, Fly.io or any
managed Postgres host. The schema matches ``SQLiteStore`` so callers
get the same upsert / query semantics.

Differences vs SQLite
---------------------
* Placeholder style — ``%s`` everywhere (no ``?``).
* ``RETURNING id`` on INSERT, ``SERIAL`` primary key instead of
  ``INTEGER PRIMARY KEY AUTOINCREMENT``.
* Booleans serialised as real ``BOOLEAN`` rather than ``INTEGER``.
* ``PRAGMA`` calls (foreign keys, row factory) don't apply — Postgres
  enforces referential integrity by default.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Iterable

try:
    import psycopg2
    import psycopg2.extras
except ImportError as exc:  # pragma: no cover - the dependency is documented
    raise ImportError(
        "PostgresStore requires psycopg2-binary. Install with "
        "`pip install psycopg2-binary` or set DATABASE_URL to a SQLite path."
    ) from exc

from .models import LotteryResult, PrizeResult
from .validator import validate_record


class PostgresStore:
    """Persist lottery results to a PostgreSQL database.

    Use :func:`huayapp_scraper.storage.open_store` to pick the right backend.
    """

    def __init__(self, database_url: str):
        # Railway-style URLs (postgres://) are not supported by libpq —
        # normalise to psycopg2's expected scheme.
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        self.database_url = database_url
        self.connection = psycopg2.connect(database_url)
        self.connection.autocommit = False
        self._create_schema()

    def _create_schema(self) -> None:
        with self.connection.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS lottery_results (
                    id SERIAL PRIMARY KEY,
                    source TEXT NOT NULL,
                    lottery_id TEXT NOT NULL,
                    lottery_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    result_date DATE NOT NULL,
                    result_time TEXT,
                    round TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    scraped_at TIMESTAMPTZ NOT NULL,
                    source_url TEXT NOT NULL,
                    source_text TEXT,
                    source_item_id TEXT NOT NULL DEFAULT '',
                    country TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(source, source_item_id, result_date, round)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS lottery_prizes (
                    result_id INTEGER NOT NULL REFERENCES lottery_results(id) ON DELETE CASCADE,
                    prize_name TEXT NOT NULL,
                    numbers_json TEXT NOT NULL,
                    PRIMARY KEY(result_id, prize_name)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS lottery_sources (
                    source_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    country TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    status TEXT NOT NULL DEFAULT 'unavailable',
                    last_attempt_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT,
                    result_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_lottery_results_lookup "
                "ON lottery_results(lottery_id, result_date, status)"
            )
        self.connection.commit()

    def upsert(self, result: LotteryResult) -> bool:
        validation = validate_record(result)
        if not validation.valid:
            raise ValueError("invalid result: " + "; ".join(validation.errors))

        source_item_id = result.source_item_id or result.lottery_id
        round_value = result.round or ""
        with self.connection.cursor() as cur:
            cur.execute(
                "SELECT id, status FROM lottery_results "
                "WHERE source=%s AND (source_item_id=%s OR (source_item_id='' AND lottery_id=%s)) "
                "AND result_date=%s AND round=%s",
                (
                    result.source,
                    source_item_id,
                    source_item_id,
                    result.result_date,
                    round_value,
                ),
            )
            existing = cur.fetchone()
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO lottery_results (
                        source, lottery_id, lottery_name, category, result_date, result_time,
                        round, status, scraped_at, source_url, source_text,
                        source_item_id, country, metadata_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        result.source,
                        result.lottery_id,
                        result.lottery_name,
                        result.category,
                        result.result_date,
                        result.result_time,
                        round_value,
                        result.status,
                        result.scraped_at,
                        result.source_url,
                        result.source_text,
                        source_item_id,
                        result.country,
                        json.dumps(result.metadata, ensure_ascii=False, sort_keys=True),
                    ),
                )
                result_id = cur.fetchone()[0]
                inserted = True
            else:
                result_id, existing_status = existing
                cur.execute(
                    "SELECT COUNT(*) AS count FROM lottery_prizes WHERE result_id=%s",
                    (result_id,),
                )
                current_count = cur.fetchone()[0]
                if existing_status == "published" and len(result.prizes) < current_count:
                    raise ValueError("incomplete result cannot replace a published result")
                cur.execute(
                    """
                    UPDATE lottery_results
                    SET lottery_id=%s, lottery_name=%s, category=%s, result_time=%s,
                        status=%s, scraped_at=%s, source_url=%s, source_text=%s,
                        source_item_id=%s, country=%s, metadata_json=%s
                    WHERE id=%s
                    """,
                    (
                        result.lottery_id,
                        result.lottery_name,
                        result.category,
                        result.result_time,
                        result.status,
                        result.scraped_at,
                        result.source_url,
                        result.source_text,
                        source_item_id,
                        result.country,
                        json.dumps(result.metadata, ensure_ascii=False, sort_keys=True),
                        result_id,
                    ),
                )
                cur.execute("DELETE FROM lottery_prizes WHERE result_id=%s", (result_id,))
                inserted = False
            psycopg2.extras.execute_batch(
                cur,
                "INSERT INTO lottery_prizes(result_id, prize_name, numbers_json) VALUES (%s, %s, %s)",
                [
                    (
                        result_id,
                        prize.prize_name,
                        json.dumps(prize.numbers, ensure_ascii=False),
                    )
                    for prize in result.prizes
                ],
            )
        self.connection.commit()
        return inserted

    def list_results(self, lottery_id: str | None = None) -> list[LotteryResult]:
        with self.connection.cursor() as cur:
            if lottery_id is not None:
                cur.execute(
                    "SELECT * FROM lottery_results WHERE lottery_id=%s ORDER BY result_date DESC, id DESC",
                    (lottery_id,),
                )
            else:
                cur.execute("SELECT * FROM lottery_results ORDER BY result_date DESC, id DESC")
            rows = cur.fetchall()
            if not rows:
                return []
            ids = [r[0] for r in rows]
            cur.execute(
                "SELECT result_id, prize_name, numbers_json FROM lottery_prizes "
                "WHERE result_id = ANY(%s) ORDER BY result_id, prize_name",
                (ids,),
            )
            prize_map: dict[int, list[PrizeResult]] = {}
            for result_id, prize_name, numbers_json in cur.fetchall():
                prize_map.setdefault(result_id, []).append(
                    PrizeResult(prize_name, json.loads(numbers_json))
                )
        results: list[LotteryResult] = []
        for row in rows:
            (
                result_id,
                source,
                lottery_id,
                lottery_name,
                category,
                result_date,
                result_time,
                round_value,
                status,
                scraped_at,
                source_url,
                source_text,
                source_item_id,
                country,
                metadata_json,
            ) = row
            results.append(
                LotteryResult(
                    source=source,
                    lottery_id=lottery_id,
                    lottery_name=lottery_name,
                    category=category,
                    result_date=result_date,
                    result_time=result_time,
                    round=round_value or None,
                    prizes=prize_map.get(result_id, []),
                    status=status,
                    scraped_at=scraped_at,
                    source_url=source_url,
                    source_text=source_text,
                    source_item_id=source_item_id or lottery_id,
                    country=country or "",
                    metadata=json.loads(metadata_json or "{}"),
                )
            )
        return results

    def stats(self) -> dict[str, int]:
        with self.connection.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) AS count FROM lottery_results GROUP BY status")
            return {row[0]: row[1] for row in cur.fetchall()}

    def upsert_source_state(self, source_id: str, **kwargs) -> None:
        def iso_value(value):
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lottery_sources (
                    source_id, name, country, category, url, enabled, status,
                    last_attempt_at, last_success_at, last_error, result_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    name=EXCLUDED.name,
                    country=EXCLUDED.country,
                    category=EXCLUDED.category,
                    url=EXCLUDED.url,
                    enabled=EXCLUDED.enabled,
                    status=EXCLUDED.status,
                    last_attempt_at=EXCLUDED.last_attempt_at,
                    last_success_at=EXCLUDED.last_success_at,
                    last_error=EXCLUDED.last_error,
                    result_count=EXCLUDED.result_count
                """,
                (
                    source_id,
                    kwargs["name"],
                    kwargs.get("country", ""),
                    kwargs.get("category", ""),
                    kwargs.get("url", ""),
                    bool(kwargs.get("enabled", True)),
                    kwargs.get("status", "unavailable"),
                    iso_value(kwargs.get("last_attempt_at")),
                    iso_value(kwargs.get("last_success_at")),
                    kwargs.get("last_error"),
                    int(kwargs.get("result_count", 0)),
                ),
            )
        self.connection.commit()

    def list_source_states(self) -> list[dict]:
        with self.connection.cursor() as cur:
            cur.execute("SELECT * FROM lottery_sources ORDER BY category, name, source_id")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception:  # noqa: BLE001
            pass