from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageFilter
from .config import Config
from .html_parser import parse_cards
from .http_client import HttpClient
from .models import LotteryCard, LotteryResult, PrizeResult
from .ocr import CanvasGlyphDecoder, CanvasOCR, OCRUnavailableError
from .validator import _expected_digits, validate_record


class ScrapeError(RuntimeError):
    pass


def build_result_from_card(
    card: LotteryCard,
    values: dict[str, list[str]],
    *,
    scraped_at: datetime | None = None,
) -> LotteryResult:
    if card.status != "published":
        raise ScrapeError(f"{card.lottery_id} is {card.status}; no result is published")
    if card.result_date is None:
        raise ScrapeError(f"{card.lottery_id} has no verified result date")

    prizes: list[PrizeResult] = []
    for slot in card.prize_slots:
        numbers = values.get(slot.prize_name, [])
        if len(numbers) != slot.number_count:
            raise ScrapeError(
                f"{card.lottery_id}/{slot.prize_name}: expected {slot.number_count} numbers, got {len(numbers)}"
            )
        prizes.append(PrizeResult(slot.prize_name, list(numbers)))

    result = LotteryResult(
        source="huayapp.com",
        lottery_id=card.lottery_id,
        lottery_name=card.lottery_name,
        category=card.category,
        result_date=card.result_date,
        result_time=card.result_time,
        round=None,
        prizes=prizes,
        status="published",
        scraped_at=scraped_at or datetime.now(timezone.utc),
        source_url=card.source_url,
        source_item_id=card.lottery_id,
        country="TH",
    )
    validation = validate_record(result)
    if not validation.valid:
        raise ScrapeError("invalid OCR result: " + "; ".join(validation.errors))
    return result


class BrowserScraper:
    def __init__(
        self,
        config: Config,
        *,
        ocr: CanvasGlyphDecoder | None = None,
        fallback_ocr: CanvasOCR | bool | None = None,
        wait_ms: int = 2000,
    ):
        self.config = config
        self.ocr = ocr or CanvasGlyphDecoder(min_score=config.ocr_confidence_threshold)
        self.wait_ms = wait_ms
        if fallback_ocr is None:
            self.fallback_ocr = self._load_default_fallback_ocr()
        elif isinstance(fallback_ocr, bool):
            self.fallback_ocr = self._load_default_fallback_ocr() if fallback_ocr else None
        else:
            self.fallback_ocr = fallback_ocr

    def _load_default_fallback_ocr(self) -> CanvasOCR | None:
        """Load the RapidOCR-backed image reader.

        The fallback uses a *lower* confidence floor than the template
        decoder. Template matching against synthetic glyphs typically scores
        above 0.85 when it matches, so a 0.70 floor is safe. RapidOCR on
        stylized digits (red Kanit on white) commonly returns 0.55–0.75; a
        floor of 0.50 keeps the fallback useful without inviting junk."""
        threshold = max(0.0, self.config.ocr_confidence_threshold - 0.20)
        try:
            return CanvasOCR(min_confidence=threshold)
        except OCRUnavailableError:
            return None

    def _read_canvas(self, canvas_locator, expected_digits: int | None) -> str | None:
        """Decode a single canvas element. Returns the digit string, or ``None``
        when both the template decoder and the image-OCR fallback reject the
        canvas.

        Order:
        1. ``CanvasGlyphDecoder`` against the live canvas context (no
           screenshot, no font dependency) — fast, deterministic.
        2. ``CanvasOCR`` against the rendered PNG of the canvas's value
           container — robust against Huayapp canvas-rendering changes
           that defeat the template matcher (the actual digits are visible
           in the rendered output even when the backing-store pixels are
           not decodable).

        The fallback path screenshots the ``.lotto-cell-value`` (parent of
        the canvas) instead of the canvas itself. On Huayapp's foreign
        lottery pages the digit content overflows the canvas element's
        fixed width (the canvas is ~77 CSS px wide while the digit runs
        ~370 CSS px); capturing only the canvas loses the first and/or
        last digit. The screenshot is also thresholded + upscaled before
        OCR to neutralize the bleed/streak overlays Huayapp paints on
        top of the digits."""
        number = self.ocr.read(canvas_locator, expected_digits=expected_digits)
        if number is not None:
            return number
        if self.fallback_ocr is None:
            return None
        try:
            # ``lotto-cell-value`` clips at canvas width; ``lotto-cell`` is wider
            # and includes the digit overflow. Match the cell exactly to bypass the
            # value wrapper.
            cell_locator = canvas_locator.locator(
                "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' lotto-cell ')][1]"
            ).first
            png_bytes = cell_locator.screenshot()
        except Exception:  # noqa: BLE001 — fallback must not raise on capture errors
            try:
                png_bytes = canvas_locator.screenshot()
            except Exception:  # noqa: BLE001
                return None
        try:
            image = Image.open(BytesIO(png_bytes)).convert("RGB")
        except Exception:  # noqa: BLE001 — malformed PNG, browser-side guard
            return None
        preprocessed = _preprocess_canvas_screenshot(image)
        return self.fallback_ocr.read(preprocessed, expected_digits=expected_digits)

    def scrape_card(self, lottery_id: str) -> LotteryResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ScrapeError("Playwright is not installed") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.config.browser_headless)
            context = browser.new_context(device_scale_factor=3)
            try:
                page = context.new_page()
                page.goto(self.config.source_url, wait_until="domcontentloaded", timeout=int(self.config.request_timeout * 1000))
                page.wait_for_selector(f"#lotto-card-{lottery_id}", state="visible", timeout=int(self.config.request_timeout * 1000))
                page.wait_for_timeout(self.wait_ms)
                cards = parse_cards(page.content(), self.config.source_url)
                card = next((item for item in cards if item.lottery_id == lottery_id), None)
                if card is None:
                    raise ScrapeError(f"lottery card not found: {lottery_id}")

                card_locator = page.locator(f"#lotto-card-{lottery_id}")
                values: dict[str, list[str]] = {}
                for slot in card.prize_slots:
                    cell = card_locator.locator(".lotto-cell").filter(has_text=slot.prize_name).first
                    canvases = cell.locator("canvas.frontend-canvas-obf")
                    if canvases.count() != slot.number_count:
                        raise ScrapeError(f"canvas count changed for {lottery_id}/{slot.prize_name}")
                    numbers: list[str] = []
                    for index in range(canvases.count()):
                        expected = _expected_digits(slot.prize_name)
                        number = self._read_canvas(canvases.nth(index), expected_digits=expected)
                        if number is None:
                            raise ScrapeError(f"OCR rejected {lottery_id}/{slot.prize_name}[{index}]")
                        numbers.append(number)
                    values[slot.prize_name] = numbers
                return build_result_from_card(card, values)
            finally:
                context.close()
                browser.close()


def _preprocess_canvas_screenshot(image: Image.Image) -> Image.Image:
    """Neutralize Huayapp's CSS distortion overlays on foreign lottery cards.

    The rendered screenshot of ``canvas.frontend-canvas-obf`` for ฮานอย /
    ลาว / มาเลย์ cards contains vertical red streaks and chromatic bleed.
    A *lower* threshold (140) keeps more of the digit ink without
    amplifying the streak artifacts, and a 4× upscale gives RapidOCR
    enough edge detail to recover every digit in multi-region canvases
    like ``เลขบน`` (5 digits)."""
    gray = image.convert("L")
    thresholded = gray.point(lambda p: 0 if p < 140 else 255)
    upscaled = thresholded.resize(
        (thresholded.width * 4, thresholded.height * 4), Image.LANCZOS
    )
    sharpened = upscaled.filter(ImageFilter.SHARPEN)
    return sharpened.convert("RGB")


def debug_scrape_card(
        self,
        lottery_id: str,
        *,
        screenshot_path: str | None = None,
        canvas_dir: str | None = None,
    ) -> dict:
        """Open a single lottery card and dump full decoder diagnostics for
        every canvas. Does not raise on canvas decode failure; returns the
        raw payload so callers can see *why* a canvas was rejected.

        When ``screenshot_path`` is given, a full-page PNG is saved next to
        the payload so a human can compare what Huayapp actually paints vs
        what the decoder sees. When ``canvas_dir`` is given, each canvas is
        exported as ``{lottery_id}_{prize_name}_{index}.png`` for the same
        comparison."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ScrapeError("Playwright is not installed") from exc

        canvas_directory = Path(canvas_dir) if canvas_dir else None
        if canvas_directory:
            canvas_directory.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.config.browser_headless)
            context = browser.new_context(device_scale_factor=3)
            try:
                page = context.new_page()
                page.goto(self.config.source_url, wait_until="domcontentloaded", timeout=int(self.config.request_timeout * 1000))
                page.wait_for_selector(f"#lotto-card-{lottery_id}", state="visible", timeout=int(self.config.request_timeout * 1000))
                page.wait_for_timeout(self.wait_ms)
                if screenshot_path:
                    page.screenshot(path=screenshot_path, full_page=True)
                cards = parse_cards(page.content(), self.config.source_url)
                card = next((item for item in cards if item.lottery_id == lottery_id), None)
                if card is None:
                    raise ScrapeError(f"lottery card not found: {lottery_id}")

                card_locator = page.locator(f"#lotto-card-{lottery_id}")
                slot_data = []
                for slot in card.prize_slots:
                    cell = card_locator.locator(".lotto-cell").filter(has_text=slot.prize_name).first
                    canvases = cell.locator("canvas.frontend-canvas-obf")
                    actual = canvases.count()
                    canvas_payloads = []
                    for index in range(actual):
                        try:
                            payload = self.ocr.debug_read(canvases.nth(index))
                        except Exception as exc:  # noqa: BLE001 — debug must keep going
                            payload = {"error": "evaluate_failed", "message": str(exc)}
                        if canvas_directory and payload and "canvas_width" in payload:
                            png_path = canvas_directory / f"{lottery_id}_{slot.prize_name}_{index}.png"
                            try:
                                canvases.nth(index).screenshot(path=str(png_path))
                            except Exception as exc:  # noqa: BLE001
                                payload = {**payload, "screenshot_error": str(exc)}
                            else:
                                payload = {**payload, "screenshot_path": str(png_path)}
                        canvas_payloads.append(payload)
                    slot_data.append(
                        {
                            "prize_name": slot.prize_name,
                            "expected_count": slot.number_count,
                            "actual_count": actual,
                            "canvas_count_mismatch": actual != slot.number_count,
                            "canvases": canvas_payloads,
                        }
                    )
                return {
                    "lottery_id": lottery_id,
                    "lottery_name": card.lottery_name,
                    "result_date": card.result_date.isoformat() if card.result_date else None,
                    "result_time": card.result_time,
                    "card_status": card.status,
                    "device_scale_factor": 3,
                    "wait_ms": self.wait_ms,
                    "min_score": self.ocr.min_score,
                    "screenshot_path": screenshot_path,
                    "slots": slot_data,
                }
            finally:
                context.close()
                browser.close()


def scrape_latest(config: Config, lottery_id: str = "100") -> LotteryResult:
    html = HttpClient(
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        backoff_base=max(0.1, config.request_delay_seconds),
    ).get(config.source_url)
    cards = parse_cards(html, config.source_url)
    if not any(card.lottery_id == lottery_id for card in cards):
        raise ScrapeError(f"lottery card not found in HTTP HTML: {lottery_id}")
    return BrowserScraper(config).scrape_card(lottery_id)


def scrape_all(config: Config) -> tuple[list[LotteryResult], list[dict[str, str]]]:
    html = HttpClient(
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        backoff_base=max(0.1, config.request_delay_seconds),
    ).get(config.source_url)
    cards = parse_cards(html, config.source_url)
    browser = BrowserScraper(config)
    results: list[LotteryResult] = []
    errors: list[dict[str, str]] = []
    for card in cards:
        if card.status != "published":
            continue
        try:
            results.append(browser.scrape_card(card.lottery_id))
        except ScrapeError as exc:
            errors.append({"lottery_id": card.lottery_id, "error": str(exc)})
    return results, errors
