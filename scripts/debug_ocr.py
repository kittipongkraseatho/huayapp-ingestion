#!/usr/bin/env python3
"""Debug the template-based canvas OCR against a live Huayapp card.

The production ``scrape_card`` path fails fast on a low similarity. This
script dumps the full decoder payload (font, transform, per-digit scores)
so we can decide whether to lower the threshold, fix the decoder, or add
a RapidOCR fallback.

Usage:
  python scripts/debug_ocr.py --lottery-id 110
  python scripts/debug_ocr.py --lottery-id 110 --output debug-110.json
  python scripts/debug_ocr.py --list   # show recently published card ids
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from anywhere; resolve to the project root regardless of CWD.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 on Windows where the default console codepage (cp874/cp1252)
# cannot encode Thai characters or the arrow glyph used in the listing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

from huayapp_scraper.config import Config
from huayapp_scraper.html_parser import parse_cards
from huayapp_scraper.http_client import HttpClient
from huayapp_scraper.scraper import BrowserScraper, ScrapeError


def list_recent_cards(config: Config, limit: int = 20) -> int:
    """Print a small table of the most recent published cards (useful for
    choosing a lottery id to debug when the user does not know one)."""
    html = HttpClient(
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        backoff_base=max(0.1, config.request_delay_seconds),
    ).get(config.source_url)
    cards = parse_cards(html, config.source_url)
    published = [c for c in cards if c.status == "published"][:limit]
    for card in published:
        date = card.result_date.isoformat() if card.result_date else "?"
        label = ", ".join(f"{s.prize_name}x{s.number_count}" for s in card.prize_slots) or "(no slots)"
        print(f"  {card.lottery_id:>4}  {date}  {card.lottery_name}  ->  {label}")
    print(f"total discovered: {len(cards)} (published shown: {len(published)})")
    return 0


def debug_one(config: Config, lottery_id: str, output: str | None, screenshot: str | None, canvas_dir: str | None, wait_ms: int) -> int:
    try:
        debug = BrowserScraper(config, wait_ms=wait_ms).debug_scrape_card(
            lottery_id,
            screenshot_path=screenshot,
            canvas_dir=canvas_dir,
        )
    except ScrapeError as exc:
        print(f"debug failed: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(debug, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(payload, encoding="utf-8")
        print(f"saved {len(payload):,} bytes to {output}", file=sys.stderr)
    if screenshot:
        print(f"page screenshot saved to {screenshot}", file=sys.stderr)
    if canvas_dir:
        print(f"canvas PNGs saved under {canvas_dir}/", file=sys.stderr)
    print(payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lottery-id", help="Huayapp lottery id to debug (e.g. 110)")
    parser.add_argument("--output", help="Write the JSON payload to this path instead of stdout only")
    parser.add_argument("--screenshot", help="Save a full-page PNG screenshot for visual verification")
    parser.add_argument("--canvas-dir", help="Save each canvas as a PNG inside this directory")
    parser.add_argument("--wait-ms", type=int, default=2000, help="Time to wait after the card appears (default 2000ms)")
    parser.add_argument("--list", action="store_true", help="List recently published cards and exit")
    args = parser.parse_args()

    config = Config.from_env()
    if args.list:
        return list_recent_cards(config)
    if not args.lottery_id:
        parser.error("either --lottery-id or --list is required")
    return debug_one(
        config,
        args.lottery_id,
        args.output,
        args.screenshot,
        args.canvas_dir,
        args.wait_ms,
    )


if __name__ == "__main__":
    raise SystemExit(main())