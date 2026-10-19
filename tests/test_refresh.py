from datetime import date, datetime, timezone
import re

from huayapp_scraper.config import Config
from huayapp_scraper.models import LotteryCard, LotteryResult, PrizeResult, PrizeSlot
from huayapp_scraper.refresh import refresh_all, refresh_all_cards
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


class FakeLocator:
    def __init__(self, count=1):
        self._count = count

    @property
    def first(self):
        return self

    def filter(self, **_kwargs):
        return self

    def locator(self, _selector):
        return self

    def count(self):
        return self._count

    def nth(self, _index):
        return self


class FakePage:
    def __init__(self, cards):
        self.cards = {card.lottery_id: card for card in cards}
        self.goto_calls = 0
        self.wait_for_selector_calls = 0
        self.wait_for_timeout_calls = 0

    def goto(self, *_args, **_kwargs):
        self.goto_calls += 1

    def wait_for_selector(self, *_args, **_kwargs):
        self.wait_for_selector_calls += 1

    def wait_for_timeout(self, _milliseconds):
        self.wait_for_timeout_calls += 1

    def content(self):
        return "<html>live page</html>"

    def locator(self, selector):
        match = re.search(r"#lotto-card-([^ ]+)", selector)
        if match:
            return FakeLocator(len(self.cards[match.group(1)].prize_slots))
        return FakeLocator()


class FakeStore:
    def __init__(self):
        self.results = []
        self.close_calls = 0

    def upsert(self, result):
        self.results.append(result)
        return True

    def close(self):
        self.close_calls += 1


def make_refresh_card(lottery_id):
    return LotteryCard(
        lottery_id=lottery_id,
        lottery_name=f"Lottery {lottery_id}",
        category="regional",
        result_date=date(2026, 10, 1),
        result_date_display="1/10/2026",
        result_time="19:30",
        status="published",
        prize_slots=(PrizeSlot("เลขบน", 1, "published"),),
        source_url="https://huayapp.test/",
    )


def patch_refresh_dependencies(monkeypatch, cards):
    from huayapp_scraper import refresh as refresh_module

    class FakeHttpClient:
        def __init__(self, **_kwargs):
            pass

        def get(self, _url):
            return "<html>index page</html>"

    class FakeDecoder:
        def __init__(self, **_kwargs):
            pass

    class FakeOCR:
        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(refresh_module, "HttpClient", FakeHttpClient)
    monkeypatch.setattr(refresh_module, "parse_cards", lambda _html, _url: cards)
    monkeypatch.setattr(refresh_module, "CanvasGlyphDecoder", FakeDecoder)
    monkeypatch.setattr(refresh_module, "CanvasOCR", FakeOCR)
    monkeypatch.setattr(refresh_module, "_decode_value", lambda *_args: "0123")


def test_refresh_all_cards_reuses_one_loaded_page(monkeypatch):
    cards = [make_refresh_card("100"), make_refresh_card("101")]
    patch_refresh_dependencies(monkeypatch, cards)
    page = FakePage(cards)
    store = FakeStore()

    successes, failures = refresh_all_cards(Config(), store=store, page=page)

    assert len(successes) == 2
    assert failures == []
    assert len(store.results) == 2
    assert page.goto_calls == 1
    assert page.wait_for_selector_calls == 1
    assert page.wait_for_timeout_calls == 1


def test_refresh_all_cards_does_not_close_caller_owned_store(monkeypatch):
    cards = [make_refresh_card("100")]
    patch_refresh_dependencies(monkeypatch, cards)
    page = FakePage(cards)
    store = FakeStore()

    refresh_all_cards(Config(), store=store, page=page)

    assert store.close_calls == 0


def test_refresh_all_cards_closes_store_it_opens(monkeypatch):
    cards = [make_refresh_card("100")]
    patch_refresh_dependencies(monkeypatch, cards)
    page = FakePage(cards)
    store = FakeStore()

    from huayapp_scraper import refresh as refresh_module

    monkeypatch.setattr(refresh_module, "open_store", lambda _config: store)
    refresh_all_cards(Config(), page=page)

    assert store.close_calls == 1
