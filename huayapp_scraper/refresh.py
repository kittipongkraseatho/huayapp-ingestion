"""Reusable refresh logic for both per-source state refresh and the
high-throughput Huayapp card refresh that powers periodic ingestion.

Two public entry points:

``refresh_all``
    Walks every source in the registry, fetches via its adapter, and
    records ``/health``/``stale``/``unavailable`` per-source state plus
    upserts any returned ``LotteryResult`` rows. Returns a
    ``RefreshReport`` used by the API layer and the ``refresh`` CLI.

``refresh_all_cards``
    Iterates every published card on the Huayapp index in a **single**
    browser session, decoding each canvas with the template decoder plus
    preprocessed RapidOCR fallback (see ``BrowserScraper._read_canvas``)
    and persisting results through the configured ``Store``. This is the
    fast path the FastAPI lifespan loop and the ``refresh-all`` CLI use
    when only the Huayapp source needs to be updated.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .config import Config
from .html_parser import parse_cards
from .http_client import HttpClient
from .ocr import CanvasGlyphDecoder, CanvasOCR
from .scraper import (
    ScrapeError,
    _preprocess_canvas_screenshot,
    build_result_from_card,
)
from .sources.registry import build_source_registry
from .storage import Store, open_store
from .validator import _expected_digits, validate_record


@dataclass
class RefreshReport:
    results: int = 0
    source_states: list[dict[str, str | int | bool | None]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def refresh_all(
    config: Config,
    *,
    registry: dict[str, Any] | None = None,
    source_ids: list[str] | None = None,
    store: Store | None = None,
) -> RefreshReport:
    """Walk every source in the registry, refresh its state, and upsert
    any returned ``LotteryResult`` rows. Used by ``refresh`` CLI and the
    ``POST /api/lottery-refresh`` endpoint.
    """
    adapters = registry or build_source_registry(config)
    if source_ids is not None:
        adapters = {sid: adapters[sid] for sid in source_ids if sid in adapters}
    own_store = store is None
    store = store or open_store(config)
    report = RefreshReport()
    try:
        for source_id, adapter in adapters.items():
            spec = adapter.spec
            attempted_at = datetime.now(timezone.utc)

            def belongs_to_source(item) -> bool:
                return item.source == source_id or (source_id == "huayapp" and item.source == "huayapp.com")

            prior = [item for item in store.list_results() if belongs_to_source(item) and item.status == "published"]
            try:
                fetched = adapter.fetch(config)
                inserted = 0
                for result in fetched.results:
                    if store.upsert(result):
                        inserted += 1
                report.results += len(fetched.results)
                status = fetched.status
                error = fetched.error
                if error:
                    report.errors.append({"source_id": source_id, "error": error})
                success_at = fetched.fetched_at if fetched.status == "published" else None
            except Exception as exc:  # noqa: BLE001
                status = "stale" if prior else "failed"
                error = str(exc)
                success_at = None
                report.errors.append({"source_id": source_id, "error": error})
                inserted = 0

            state = {
                "source_id": source_id,
                "name": spec.name,
                "country": spec.country,
                "category": spec.category,
                "url": spec.url,
                "enabled": spec.enabled,
                "status": status,
                "last_attempt_at": attempted_at.isoformat(),
                "last_success_at": success_at.isoformat() if success_at else None,
                "last_error": error,
                "result_count": len([item for item in store.list_results() if belongs_to_source(item)]),
            }
            store.upsert_source_state(
                source_id,
                name=spec.name,
                country=spec.country,
                category=spec.category,
                url=spec.url,
                enabled=spec.enabled,
                status=status,
                last_attempt_at=state["last_attempt_at"],
                last_success_at=state["last_success_at"],
                last_error=error,
                result_count=state["result_count"],
            )
            report.source_states.append(state)
    finally:
        if own_store:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
    return report


def _decode_value(
    canvas_locator,
    cell_locator,
    ocr: CanvasGlyphDecoder,
    fallback_ocr: CanvasOCR | None,
    expected: int | None,
) -> str | None:
    """Try the template decoder, then fall back to the preprocessed cell screenshot."""
    number = ocr.read(canvas_locator, expected_digits=expected)
    if number is not None:
        return number
    if fallback_ocr is None:
        return None
    try:
        png = cell_locator.screenshot()
    except Exception:  # noqa: BLE001 — capture failures are non-fatal
        return None
    try:
        image = Image.open(BytesIO(png)).convert("RGB")
    except Exception:  # noqa: BLE001 — malformed PNG, browser-side guard
        return None
    preprocessed = _preprocess_canvas_screenshot(image)
    return fallback_ocr.read(preprocessed, expected_digits=expected)


def refresh_all_cards(
    config: Config,
    *,
    store: Store | None = None,
    page: Any | None = None,
    progress_callback: Any | None = None,
) -> tuple[list[Any], list[tuple[str, str]]]:
    """Decode every published card and persist results.

    Parameters
    ----------
    config:
        Runtime configuration (``Config.from_env`` shape).
    store:
        Optional pre-opened :class:`Store`. When ``None`` a new store is
        opened via :func:`open_store` based on ``DATABASE_URL``.
    page:
        Optional Playwright page to re-use. When ``None`` the function
        opens its own headless Chromium and tears it down on completion.
    progress_callback:
        Optional callable invoked as ``progress_callback(idx, total, card_id, success, error)``
        after every card. Useful for the CLI / API to stream partial progress.
        """
    provided_store = store is not None
    if store is None:
        store = open_store(config)

    try:
        # Discover cards from the public HTML index.
        html = HttpClient(
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            backoff_base=max(0.1, config.request_delay_seconds),
        ).get(config.source_url)
        cards = parse_cards(html, config.source_url)
        published = [card for card in cards if card.status == "published"]

        ocr = CanvasGlyphDecoder(min_score=config.ocr_confidence_threshold)
        fallback_ocr: CanvasOCR | None = None
        try:
            fallback_ocr = CanvasOCR(
                min_confidence=max(0.0, config.ocr_confidence_threshold - 0.20)
            )
        except Exception:  # noqa: BLE001 — fallback is best-effort
            fallback_ocr = None

        successes: list[Any] = []
        failures: list[tuple[str, str]] = []
        now = datetime.now(timezone.utc)

        def _iter(page):
            from playwright.sync_api import sync_playwright

            ctx_page = page
            close_at_every: list[Any] = []
            try:
                if ctx_page is None:
                    pw = sync_playwright().start()
                    close_at_every.append(pw)
                    browser_engine = pw.chromium.launch(headless=config.browser_headless)
                    close_at_every.append(browser_engine)
                    context = browser_engine.new_context(device_scale_factor=3)
                    close_at_every.append(context)
                    ctx_page = context.new_page()
                    close_at_every.append(ctx_page)

                if not published:
                    return

                ctx_page.goto(
                    config.source_url,
                    wait_until="domcontentloaded",
                    timeout=int(config.request_timeout * 1000),
                )
                ctx_page.wait_for_selector(
                    f"#lotto-card-{published[0].lottery_id}",
                    state="visible",
                    timeout=int(config.request_timeout * 1000),
                )
                ctx_page.wait_for_timeout(2000)
                page_now = parse_cards(ctx_page.content(), config.source_url)
                cards_now = {card.lottery_id: card for card in page_now}

                for idx, card in enumerate(published):
                    lottery_id = card.lottery_id
                    try:
                        card_now = cards_now.get(lottery_id)
                        if card_now is None or card_now.status != "published":
                            raise ScrapeError(f"{lottery_id} not found or unpublished")

                        values: dict[str, list[str]] = {}
                        for slot in card_now.prize_slots:
                            cell = ctx_page.locator(
                                f"#lotto-card-{lottery_id} .lotto-cell"
                            ).filter(has_text=slot.prize_name).first
                            canvases = cell.locator("canvas.frontend-canvas-obf")
                            actual = canvases.count()
                            if actual != slot.number_count:
                                raise ScrapeError(
                                    f"canvas count changed for {lottery_id}/{slot.prize_name}"
                                )
                            expected = _expected_digits(slot.prize_name)
                            numbers: list[str] = []
                            for i in range(actual):
                                canvas = canvases.nth(i)
                                number = _decode_value(
                                    canvas, cell, ocr, fallback_ocr, expected
                                )
                                if number is None:
                                    raise ScrapeError(
                                        f"OCR rejected {lottery_id}/{slot.prize_name}[{i}]"
                                    )
                                numbers.append(number)
                            values[slot.prize_name] = numbers
                        result = build_result_from_card(card_now, values, scraped_at=now)
                        validation = validate_record(result)
                        if not validation.valid:
                            raise ScrapeError(
                                "validation failed: " + "; ".join(validation.errors)
                            )
                        store.upsert(result)
                        successes.append(result)
                        if progress_callback is not None:
                            progress_callback(idx + 1, len(published), lottery_id, True, None)
                    except ScrapeError as exc:
                        failures.append((lottery_id, str(exc)))
                        if progress_callback is not None:
                            progress_callback(idx + 1, len(published), lottery_id, False, str(exc))
                    except Exception as exc:  # noqa: BLE001 — keep the loop alive
                        failures.append((lottery_id, f"unexpected: {exc}"))
                        if progress_callback is not None:
                            progress_callback(idx + 1, len(published), lottery_id, False, f"unexpected: {exc}")
            finally:
                for handle in reversed(close_at_every):
                    try:
                        close = getattr(handle, "close", None)
                        if callable(close):
                            close()
                            continue
                        stop = getattr(handle, "stop", None)
                        if callable(stop):
                            stop()
                    except Exception:  # noqa: BLE001
                        pass

        _iter(page)
        return successes, failures
    finally:
        if not provided_store:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass


__all__ = ["refresh_all_cards"]
