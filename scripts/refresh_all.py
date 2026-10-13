"""Refresh the entire Huayapp page in one browser session and persist results to lottery.db.

This is the production ingestion path used by operators and by the
``POST /api/lottery-refresh`` endpoint. It wraps
:func:`huayapp_scraper.refresh.refresh_all_cards` so the CLI and the API
share the same code path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from huayapp_scraper.config import Config
from huayapp_scraper.refresh import refresh_all_cards


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print one JSON line per card as it is processed.",
    )
    args = parser.parse_args()

    config = Config.from_env()

    def progress(idx, total, card_id, success, error):
        print(
            json.dumps(
                {"index": idx, "total": total, "card_id": card_id, "ok": success, "error": error},
                ensure_ascii=False,
            ),
            flush=True,
        )

    successes, failures = refresh_all_cards(
        config,
        progress_callback=progress if args.progress else None,
    )
    print(
        json.dumps(
            {"succeeded": len(successes), "failed": len(failures), "failures": failures},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())