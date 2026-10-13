from datetime import date, datetime, timezone

from huayapp_scraper.config import Config
from huayapp_scraper.models import LotteryResult, PrizeResult
from huayapp_scraper.refresh import refresh_all
from huayapp_scraper.sources.base import SourceFetch, SourceSpec
from huayapp_scraper.storage import SQLiteStore


def make_result(source: str, source_item_id: str) -> LotteryResult:
    return LotteryResult(
        source=source,
        lottery_id=source_item_id,
        lottery_name="Test lottery",
        category="regional",
        result_date=date(2026, 10, 1),
        result_time="19:30",
        round="2026-10-01",
        prizes=[PrizeResult("1st Prize", ["0123"])],
        status="published",
        scraped_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        source_url="https://example.test/results",
        source_item_id=source_item_id,
        country="TH",
    )


class GoodAdapter:
    spec = SourceSpec("good", "Good", "TH", "regional", "https://good.test", True)

    def fetch(self, config):
        return SourceFetch(results=[make_result("good", "good-1")], status="published", fetched_at=datetime.now(timezone.utc))


class FailingAdapter:
    spec = SourceSpec("bad", "Bad", "TH", "regional", "https://bad.test", True)

    def fetch(self, config):
        raise TimeoutError("source timed out")


def test_refresh_isolates_source_failure_and_persists_success(tmp_path):
    config = Config(database_path=tmp_path / "results.db")
    report = refresh_all(config, registry={"good": GoodAdapter(), "bad": FailingAdapter()})

    assert report.results == 1
    assert report.errors == [{"source_id": "bad", "error": "source timed out"}]
    assert {item["source_id"] for item in report.source_states} == {"good", "bad"}
    store = SQLiteStore(config.database_path)
    try:
        assert [item.source_item_id for item in store.list_results()] == ["good-1"]
    finally:
        store.close()


def test_refresh_keeps_published_result_and_marks_source_stale_after_failure(tmp_path):
    config = Config(database_path=tmp_path / "results.db")
    registry = {"good": GoodAdapter()}

    refresh_all(config, registry=registry)

    class NowFailingAdapter(GoodAdapter):
        def fetch(self, config):
            raise TimeoutError("temporary outage")

    report = refresh_all(config, registry={"good": NowFailingAdapter()})

    assert report.results == 0
    assert report.source_states[0]["status"] == "stale"
    store = SQLiteStore(config.database_path)
    try:
        assert store.list_results()[0].status == "published"
    finally:
        store.close()


def test_generic_public_cards_parser_preserves_number_strings():
    from pathlib import Path
    from huayapp_scraper.sources.external import parse_public_result_cards

    html = Path("tests/fixtures/external/generic_cards.html").read_text(encoding="utf-8")
    spec = SourceSpec("lao", "Lao Lottery", "LA", "regional", "https://example.test", True)

    results = parse_public_result_cards(html, spec)

    assert len(results) == 1
    assert results[0].source_item_id == "lao-2026-10-01"
    assert results[0].country == "LA"
    assert results[0].prizes[0].numbers == ["0123"]


def test_huayapp_registry_adapter_calls_dynamic_scrape(monkeypatch):
    from huayapp_scraper.sources import huayapp as huayapp_module
    from huayapp_scraper.sources.huayapp import HuayappAdapter

    expected = make_result("huayapp.com", "100")
    monkeypatch.setattr(huayapp_module, "scrape_all", lambda config: ([expected], []))
    adapter = HuayappAdapter(SourceSpec("huayapp", "Huayapp", "TH", "huayapp", "https://huayapp.com/", True))

    fetched = adapter.fetch(Config())

    assert fetched.status == "published"
    assert fetched.results == [expected]
