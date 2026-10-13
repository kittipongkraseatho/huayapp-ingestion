from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..config import Config
from ..http_client import HttpClient, HttpClientError
from ..validator import validate_record
from ..validator import normalize_thai_date
from .base import Parser, SourceFetch, SourceSpec


class ConfiguredPublicAdapter:
    def __init__(self, spec: SourceSpec, parser: Parser | None = None):
        self.spec = spec
        self.parser = parser

    def fetch(self, config: Config) -> SourceFetch:
        fetched_at = datetime.now(timezone.utc)
        if not self.spec.enabled:
            return SourceFetch(status="unavailable", fetched_at=fetched_at, error="source is disabled")
        if not self.spec.url:
            return SourceFetch(status="unavailable", fetched_at=fetched_at, error="no public source URL configured")
        if self.parser is None:
            return SourceFetch(status="unavailable", fetched_at=fetched_at, error="source parser is not configured")

        try:
            payload = HttpClient(
                timeout=config.request_timeout,
                max_retries=config.max_retries,
                backoff_base=max(0.1, config.request_delay_seconds),
            ).get(self.spec.url)
            results = self.parser(payload, self.spec)
            errors = [
                error
                for result in results
                for error in validate_record(result).errors
            ]
            if errors:
                return SourceFetch(status="failed", fetched_at=fetched_at, error="; ".join(errors))
            return SourceFetch(results=results, status="published", fetched_at=fetched_at)
        except (HttpClientError, ValueError, RuntimeError) as exc:
            return SourceFetch(status="failed", fetched_at=fetched_at, error=str(exc))


def parse_public_result_cards(html: str, spec: SourceSpec):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("[data-lottery-result]"):
        source_item_id = (card.get("data-source-item-id") or "").strip()
        name = (card.get("data-name") or "").strip() or spec.name
        date_text = (card.get("data-date") or "").strip()
        if not source_item_id or not date_text:
            continue
        result_date = normalize_thai_date(date_text)
        prizes = []
        for prize in card.select("[data-prize]"):
            prize_name = (prize.get("data-prize-name") or "").strip()
            numbers = (prize.get("data-number") or "").strip()
            if prize_name and numbers:
                prizes.append((prize_name, [item.strip() for item in numbers.split(",") if item.strip()]))
        if not prizes:
            continue
        from ..models import LotteryResult, PrizeResult

        results.append(
            LotteryResult(
                source=spec.source_id,
                lottery_id=source_item_id,
                lottery_name=name,
                category=spec.category,
                result_date=result_date,
                result_time=(card.get("data-time") or "").strip() or None,
                round=(card.get("data-round") or "").strip() or None,
                prizes=[PrizeResult(name, numbers) for name, numbers in prizes],
                status="published",
                scraped_at=datetime.now(timezone.utc),
                source_url=spec.url,
                source_item_id=source_item_id,
                country=spec.country,
            )
        )
    return results
