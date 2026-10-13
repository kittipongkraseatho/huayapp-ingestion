import json
from datetime import date, datetime, timezone

from huayapp_scraper import cli
from huayapp_scraper.models import LotteryResult, PrizeResult
from huayapp_scraper.storage import SQLiteStore


def make_result():
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


def test_inspect_reports_reachable_page_and_categories(monkeypatch, capsys):
    fixture = open("tests/fixtures/thai_gov_latest.html", encoding="utf-8").read()

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def get(self, url):
            return fixture

    monkeypatch.setattr(cli, "HttpClient", FakeClient)
    assert cli.main(["inspect"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["reachable"] is True
    assert output["card_count"] == 3
    assert "หวยทางการ" in output["categories"]


def test_export_command_writes_requested_format(tmp_path, capsys):
    database = tmp_path / "results.db"
    store = SQLiteStore(database)
    store.upsert(make_result())
    store.close()
    output = tmp_path / "results.json"

    assert cli.main(["export", "--db", str(database), "--format", "json", "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["prizes"][0]["numbers"] == ["07"]


def test_stats_command_reports_persisted_count(tmp_path, capsys):
    database = tmp_path / "results.db"
    store = SQLiteStore(database)
    store.upsert(make_result())
    store.close()

    assert cli.main(["stats", "--db", str(database)]) == 0
    assert json.loads(capsys.readouterr().out) == {"published": 1}


def test_scrape_all_command_persists_discovered_results(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "scrape_all", lambda config: ([make_result()], []))
    database = tmp_path / "results.db"

    assert cli.main(["scrape-all", "--db", str(database)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stored"] == 1
    assert payload["inserted"] == 1
    assert payload["errors"] == []
    store = SQLiteStore(database)
    try:
        assert len(store.list_results()) == 1
    finally:
        store.close()
