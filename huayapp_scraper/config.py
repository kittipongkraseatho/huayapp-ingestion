from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Config:
    source_url: str = "https://huayapp.com/"
    request_timeout: float = 20.0
    request_delay_seconds: float = 2.0
    max_retries: int = 3
    # Share the application's SQLite file; the scraper creates its own
    # lottery_results/lottery_prizes tables without touching legacy tables.
    database_path: Path = Path("lottery.db")
    # When set, ``open_store`` picks Postgres over SQLite. ``None``
    # falls back to the SQLite path above.
    database_url: str | None = None
    output_directory: Path = Path("output")
    log_level: str = "INFO"
    browser_headless: bool = True
    ocr_confidence_threshold: float = 0.70
    # Periodic ingestion needs >= 60s and ideally larger than the time it
    # takes to scrape every published card (~15 min for the 142-card
    # Huayapp index). 900s is the production default.
    refresh_interval_seconds: int = 900
    enabled_sources: tuple[str, ...] = ()
    source_urls: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Config":
        headless = os.getenv("BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        enabled_raw = os.getenv("ENABLED_LOTTERY_SOURCES", "").strip()
        enabled_sources = tuple(item.strip() for item in enabled_raw.split(",") if item.strip())
        source_urls = {
            "thai-government": os.getenv("THAI_GOV_SOURCE_URL", ""),
            "savings-lottery": os.getenv("SAVINGS_LOTTERY_SOURCE_URL", ""),
            "lao": os.getenv("LAO_SOURCE_URL", ""),
            "hanoi": os.getenv("HANOI_SOURCE_URL", ""),
            "malaysia": os.getenv("MALAYSIA_SOURCE_URL", ""),
            "thai-stocks": os.getenv("THAI_STOCKS_SOURCE_URL", ""),
            "foreign-stocks": os.getenv("FOREIGN_STOCKS_SOURCE_URL", ""),
        }
        return cls(
            source_url=os.getenv("SOURCE_URL", cls.source_url),
            request_timeout=_float_env("REQUEST_TIMEOUT", cls.request_timeout),
            request_delay_seconds=_float_env("REQUEST_DELAY_SECONDS", cls.request_delay_seconds),
            max_retries=_int_env("MAX_RETRIES", cls.max_retries),
            database_path=Path(os.getenv("DATABASE_PATH", str(cls.database_path))),
            database_url=os.getenv("DATABASE_URL") or None,
            output_directory=Path(os.getenv("OUTPUT_DIRECTORY", str(cls.output_directory))),
            log_level=os.getenv("LOG_LEVEL", cls.log_level),
            browser_headless=headless,
            ocr_confidence_threshold=_float_env("OCR_CONFIDENCE_THRESHOLD", cls.ocr_confidence_threshold),
            refresh_interval_seconds=max(60, _int_env("REFRESH_INTERVAL_SECONDS", cls.refresh_interval_seconds)),
            enabled_sources=enabled_sources,
            source_urls=source_urls,
        )
