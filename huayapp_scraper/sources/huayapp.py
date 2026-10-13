from __future__ import annotations

from datetime import datetime, timezone

from ..config import Config
from ..scraper import scrape_all
from .base import SourceFetch, SourceSpec


class HuayappAdapter:
    def __init__(self, spec: SourceSpec):
        self.spec = spec

    def fetch(self, config: Config) -> SourceFetch:
        fetched_at = datetime.now(timezone.utc)
        results, errors = scrape_all(config)
        error = "; ".join(f"{item['lottery_id']}: {item['error']}" for item in errors) or None
        return SourceFetch(
            results=results,
            status="published" if results else "failed",
            fetched_at=fetched_at if results else None,
            error=error,
        )
