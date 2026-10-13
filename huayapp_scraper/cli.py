from __future__ import annotations

import argparse
import json
import logging
from dataclasses import replace
from pathlib import Path

from .config import Config
from .html_parser import parse_cards
from .http_client import HttpClient
from .scraper import ScrapeError, scrape_all, scrape_latest
from .storage import SQLiteStore, export_csv, export_json
from .validator import validate_record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Huayapp public HTML scraper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inspect", help="inspect the reachable HTML and verified selectors")

    latest = sub.add_parser("scrape-latest", help="scrape one latest lottery card")
    latest.add_argument("--lottery-id", default="100")
    latest.add_argument("--db", default=None)

    all_cards = sub.add_parser("scrape-all", help="scrape every published lottery card")
    all_cards.add_argument("--db", default=None)

    scrape = sub.add_parser("scrape", help="scrape selected lottery cards")
    scrape.add_argument("--lottery-id", dest="lottery_ids", action="append")
    scrape.add_argument("--category")
    scrape.add_argument("--db", default=None)

    export = sub.add_parser("export", help="export stored results")
    export.add_argument("--db", default=None)
    export.add_argument("--format", choices=("json", "csv"), required=True)
    export.add_argument("--output", required=True)

    stats = sub.add_parser("stats", help="show stored result counts")
    stats.add_argument("--db", default=None)

    validate = sub.add_parser("validate", help="revalidate stored results")
    validate.add_argument("--db", default=None)
    return parser


def _config(args: argparse.Namespace) -> Config:
    config = Config.from_env()
    return replace(config, database_path=Path(args.db) if getattr(args, "db", None) else config.database_path)


def _inspect(config: Config) -> int:
    try:
        html = HttpClient(
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            backoff_base=max(0.1, config.request_delay_seconds),
        ).get(config.source_url)
        cards = parse_cards(html, config.source_url)
        categories: dict[str, int] = {}
        for card in cards:
            categories[card.category] = categories.get(card.category, 0) + 1
        payload = {
            "reachable": True,
            "source_url": config.source_url,
            "card_count": len(cards),
            "categories": categories,
            "selectors": {
                "cards": ".lotto-card[data-lotto-id]",
                "prize_labels": ".lotto-cell-label",
                "canvas_values": "canvas.frontend-canvas-obf",
                "historical": "button.button-after-result",
            },
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"reachable": False, "error": str(exc)}, ensure_ascii=True))
        return 1


def _scrape_ids(config: Config, lottery_ids: list[str]) -> int:
    store = SQLiteStore(config.database_path)
    inserted = 0
    try:
        for lottery_id in lottery_ids:
            result = scrape_latest(config, lottery_id)
            if store.upsert(result):
                inserted += 1
            print(json.dumps({"lottery_id": lottery_id, "status": "stored", "inserted": inserted}, ensure_ascii=False))
    finally:
        store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, Config.from_env().log_level.upper(), logging.INFO))
    config = _config(args)

    if args.command == "inspect":
        return _inspect(config)
    if args.command == "scrape-latest":
        try:
            return _scrape_ids(config, [args.lottery_id])
        except ScrapeError as exc:
            logging.error("scrape failed: %s", exc)
            return 1
    if args.command == "scrape-all":
        results, errors = scrape_all(config)
        store = SQLiteStore(config.database_path)
        try:
            inserted = sum(1 for result in results if store.upsert(result))
        finally:
            store.close()
        print(json.dumps({"stored": len(results), "inserted": inserted, "errors": errors}, ensure_ascii=False))
        return 0 if results else 1
    if args.command == "scrape":
        if args.lottery_ids:
            ids = args.lottery_ids
        elif args.category:
            html = HttpClient(timeout=config.request_timeout, max_retries=config.max_retries).get(config.source_url)
            ids = [card.lottery_id for card in parse_cards(html, config.source_url) if card.category == args.category]
        else:
            raise SystemExit("scrape requires --lottery-id or --category")
        try:
            return _scrape_ids(config, ids)
        except ScrapeError as exc:
            logging.error("scrape failed: %s", exc)
            return 1
    if args.command == "export":
        store = SQLiteStore(config.database_path)
        try:
            results = store.list_results()
        finally:
            store.close()
        if args.format == "json":
            export_json(results, args.output)
        else:
            export_csv(results, args.output)
        print(json.dumps({"exported": len(results), "path": args.output}, ensure_ascii=False))
        return 0
    if args.command == "stats":
        store = SQLiteStore(config.database_path)
        try:
            print(json.dumps(store.stats(), ensure_ascii=False, sort_keys=True))
        finally:
            store.close()
        return 0
    if args.command == "validate":
        store = SQLiteStore(config.database_path)
        try:
            results = store.list_results()
        finally:
            store.close()
        errors = [error for result in results for error in validate_record(result).errors]
        print(json.dumps({"records": len(results), "valid": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 1
    return 2
