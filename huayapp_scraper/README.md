# Huayapp HTML scraper

This package reads public result cards from [huayapp.com](https://huayapp.com/),
renders the selected card in Chromium, and stores only validated results in
SQLite. It does not call Huayapp's internal API or decode `data-val` tokens.

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

The browser-rendered canvas reader is the primary decoder. `requirements-ocr.txt`
is optional and contains RapidOCR for experiments or a future fallback; OCR is
never allowed to save an ambiguous result.

## Commands

```powershell
python main.py inspect
python main.py scrape-latest --lottery-id 100
python main.py scrape --lottery-id 100 --lottery-id 155 --db lottery.db
python main.py scrape-all --db lottery.db
python main.py stats --db lottery.db
python main.py export --db lottery.db --format json --output output/results.json
python main.py export --db lottery.db --format csv --output output/results.csv
python main.py validate --db lottery.db
```

The default database is the existing application file `lottery.db`. The
scraper adds only `lottery_results` and `lottery_prizes`; legacy
`yiki_results` and `stocks_results` are left unchanged. The Bun server exposes
the stored records through:

```text
GET /api/huayapp-results
GET /api/huayapp-results?lottery_id=100&limit=20
GET /api/lottery-snapshot   # includes a huayapp array
```

The FastAPI ingestion service also exposes the normalized feed:

```text
GET /api/lottery-results?source=&country=&category=&date=&limit=500
GET /api/lottery-sources
POST /api/lottery-refresh
```

`scrape-all` discovers every published card on the Huayapp index. External
source adapters are registered by source group (Thai government, savings
lotteries, Lao, Hanoi, Malaysia, Thai stocks, and foreign stocks). Configure
their public URLs with the `*_SOURCE_URL` environment variables. Empty or
unverified sources stay `unavailable`; the service never guesses results or
bypasses CAPTCHA/access controls. The refresh loop defaults to 60 seconds and
keeps the last published result as `stale` when a source temporarily fails.

Numbers are stored as strings so leading zeroes are preserved. A pending,
suspended, incomplete, or low-confidence card is rejected and cannot overwrite
a previously published row. Re-running the same result is idempotent.

## Operational limits

- Use a modest polling interval and respect the site's terms, robots guidance,
  and available capacity.
- Do not bypass CAPTCHA, authentication, access controls, or anti-bot systems.
- The parser currently targets the verified latest-result card flow. Historical
  modal extraction and mapping into the existing Bun application's database are
  separate follow-up work because their storage contract is not defined here.
- The live probe is opt-in and requires Chromium. Offline tests use sanitized
  fixtures and do not contain live winning numbers.

## Integration boundary

The scraper writes normalized results directly to the existing application's
`lottery.db`, while keeping its tables separate from legacy data. The current
sync command is explicit (`scrape-latest` or `scrape`) so deployments can run it
from a scheduler after selecting the desired lottery IDs.
