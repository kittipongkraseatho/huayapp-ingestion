from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .config import Config
from .scraper import ScrapeError, scrape_latest
from .storage import SQLiteStore


def schedule_latest(
    config: Config,
    interval_seconds: int,
    *,
    lottery_id: str = "100",
    run_once: Callable[[], None] | None = None,
) -> None:
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be positive")
    while True:
        try:
            if run_once:
                run_once()
            else:
                result = scrape_latest(config, lottery_id)
                store = SQLiteStore(config.database_path)
                try:
                    store.upsert(result)
                finally:
                    store.close()
        except ScrapeError:
            logging.exception("scheduled scrape failed")
        time.sleep(interval_seconds)
