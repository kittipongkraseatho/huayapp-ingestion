import csv
import json
from datetime import date, datetime, timezone

from huayapp_scraper.models import LotteryResult, PrizeResult
from huayapp_scraper.storage import export_csv, export_json


def result():
    return LotteryResult(
        source="huayapp.com",
        lottery_id="100",
        lottery_name="รัฐบาลไทย",
        category="หวยทางการ",
        result_date=date(2026, 10, 1),
        result_time=None,
        round=None,
        prizes=[PrizeResult("2 ตัวล่าง", ["07"])],
        status="published",
        scraped_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
        source_url="https://huayapp.com/",
    )


def test_json_export_preserves_unicode_and_number_strings(tmp_path):
    output = tmp_path / "results.json"
    export_json([result()], output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload[0]["prizes"][0]["numbers"] == ["07"]
    assert payload[0]["lottery_name"] == "รัฐบาลไทย"


def test_csv_export_preserves_leading_zeroes_and_unicode(tmp_path):
    output = tmp_path / "results.csv"
    export_csv([result()], output)
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["number"] == "07"
    assert rows[0]["prize_name"] == "2 ตัวล่าง"
