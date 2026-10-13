from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from huayapp_scraper.html_parser import parse_cards
from huayapp_scraper.models import PrizeResult
from huayapp_scraper.config import Config
from huayapp_scraper.ocr import CanvasGlyphDecoder
from huayapp_scraper.scraper import BrowserScraper, ScrapeError, build_result_from_card, scrape_all
from huayapp_scraper.validator import _expected_digits


FIXTURE = Path(__file__).parent / "fixtures" / "thai_gov_latest.html"


def test_build_result_from_verified_card_keeps_number_strings():
    card = next(card for card in parse_cards(FIXTURE.read_text(encoding="utf-8"), "https://huayapp.com/") if card.lottery_id == "100")
    result = build_result_from_card(
        card,
        {
            "รางวัลที่ 1": ["012345"],
            "3 ตัวบน": ["345"],
            "2 ตัวล่าง": ["07"],
            "3 ตัวหน้า": ["123", "456"],
            "3 ตัวหลัง": ["789", "000"],
        },
        scraped_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )

    assert result.result_date == date(2026, 10, 1)
    assert result.prizes[0].numbers == ["012345"]
    assert result.status == "published"


@pytest.mark.parametrize("lottery_id", ["155", "158"])
def test_build_result_rejects_unpublished_card_states(lottery_id):
    card = next(card for card in parse_cards(FIXTURE.read_text(encoding="utf-8"), "https://huayapp.com/") if card.lottery_id == lottery_id)
    with pytest.raises(ScrapeError):
        build_result_from_card(card, {slot.prize_name: ["1"] for slot in card.prize_slots})


def test_scrape_all_discovers_every_published_card(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    cards = parse_cards(html, "https://huayapp.com/")
    attempted: list[str] = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def get(self, url):
            return html

    class FakeBrowser:
        def __init__(self, config):
            pass

        def scrape_card(self, lottery_id):
            attempted.append(lottery_id)
            card = next(item for item in cards if item.lottery_id == lottery_id)
            values = {}
            for slot in card.prize_slots:
                width = _expected_digits(slot.prize_name) or 1
                values[slot.prize_name] = ["0" * width for _ in range(slot.number_count)]
            return build_result_from_card(card, values)

    monkeypatch.setattr("huayapp_scraper.scraper.HttpClient", FakeClient)
    monkeypatch.setattr("huayapp_scraper.scraper.BrowserScraper", FakeBrowser)

    results, errors = scrape_all(Config())

    expected_ids = [card.lottery_id for card in cards if card.status == "published"]
    assert attempted == expected_ids
    assert [result.lottery_id for result in results] == expected_ids
    assert errors == []


class _FakeLocator:
    def __init__(self, *, evaluate_return=None, screenshot_bytes=None):
        self._evaluate_return = evaluate_return
        self._screenshot_bytes = screenshot_bytes
        self.evaluate_calls = 0
        self.screenshot_calls = 0

    def evaluate(self, _script):
        self.evaluate_calls += 1
        return self._evaluate_return

    def screenshot(self):
        self.screenshot_calls += 1
        if self._screenshot_bytes is None:
            raise RuntimeError("screenshot failed")
        return self._screenshot_bytes


def _png_bytes():
    """A valid 1x1 RGB PNG so ``Image.open`` roundtrips without errors."""
    buf = BytesIO()
    Image.new("RGB", (1, 1), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


class _ScriptedFallback:
    def __init__(self, return_value):
        self._return = return_value
        self.calls: list = []

    def read(self, image, *, expected_digits=None):
        self.calls.append((image, expected_digits))
        return self._return


def test_read_canvas_uses_template_when_it_succeeds():
    decoder = CanvasGlyphDecoder(min_score=0.5)
    decoder.read = lambda locator, expected_digits=None: "582"
    fallback = _ScriptedFallback(return_value="999")

    scraper = BrowserScraper(Config(), ocr=decoder, fallback_ocr=fallback)
    locator = _FakeLocator(evaluate_return={"text": "582"})

    result = scraper._read_canvas(locator, expected_digits=3)

    assert result == "582"
    assert locator.evaluate_calls == 0  # lambda short-circuited; no evaluate call needed
    assert locator.screenshot_calls == 0  # fallback never triggered
    assert fallback.calls == []


def test_read_canvas_falls_back_to_image_ocr_when_template_fails():
    decoder = CanvasGlyphDecoder(min_score=0.5)
    decoder.read = lambda locator, expected_digits=None: None
    fallback = _ScriptedFallback(return_value="752")

    scraper = BrowserScraper(Config(), ocr=decoder, fallback_ocr=fallback)
    locator = _FakeLocator(evaluate_return={}, screenshot_bytes=_png_bytes())

    result = scraper._read_canvas(locator, expected_digits=3)

    assert result == "752"
    assert locator.screenshot_calls == 1
    assert len(fallback.calls) == 1
    assert fallback.calls[0][1] == 3  # expected_digits forwarded


def test_read_canvas_returns_none_when_both_decoders_fail():
    decoder = CanvasGlyphDecoder(min_score=0.5)
    decoder.read = lambda locator, expected_digits=None: None
    fallback = _ScriptedFallback(return_value=None)

    scraper = BrowserScraper(Config(), ocr=decoder, fallback_ocr=fallback)
    locator = _FakeLocator(evaluate_return={}, screenshot_bytes=_png_bytes())

    assert scraper._read_canvas(locator, expected_digits=3) is None


def test_read_canvas_returns_none_when_fallback_unavailable():
    decoder = CanvasGlyphDecoder(min_score=0.5)
    decoder.read = lambda locator, expected_digits=None: None

    scraper = BrowserScraper(Config(), ocr=decoder, fallback_ocr=False)
    locator = _FakeLocator(evaluate_return={})

    assert scraper._read_canvas(locator, expected_digits=3) is None
    assert locator.screenshot_calls == 0


def test_read_canvas_handles_screenshot_failure():
    decoder = CanvasGlyphDecoder(min_score=0.5)
    decoder.read = lambda locator, expected_digits=None: None
    fallback = _ScriptedFallback(return_value="should-not-be-called")

    scraper = BrowserScraper(Config(), ocr=decoder, fallback_ocr=fallback)
    locator = _FakeLocator(evaluate_return={}, screenshot_bytes=None)

    assert scraper._read_canvas(locator, expected_digits=3) is None
    assert fallback.calls == []
