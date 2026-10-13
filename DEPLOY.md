# Deploy

Production layout for the Huayapp ingestion stack:

```
Firebase Hosting (lotto-89ad0.web.app)        Railway (Postgres + FastAPI)
┌───────────────────────────────┐         ┌─────────────────────────────────┐
│  index.html  (SPA, public)    │         │  uvicorn huayapp_api.app:app    │
│  huayApiUrl ────────────────▶ │ ───────▶│  Postgres lottery_results      │
│  (config.huayApiUrl)         │         │  periodic refresh loop        │
└───────────────────────────────┘         └─────────────────────────────────┘
```

## Frontend — Firebase Hosting (already deployed ✅)

```
Hosting URL:   https://lotto-89ad0.web.app
Firebase Console: https://console.firebase.google.com/project/lotto-89ad0/overview
```

Files under `firebase-hosting.json`'s ``ignore`` block are excluded; everything
else in the project root is uploaded (after `firebase-hosting.json` is copied over
`firebase.json`).

Redeploy after editing `index.html`:

```bash
Copy-Item firebase-hosting.json firebase.json -Force
firebase deploy --only hosting --project lotto-89ad0
```

If the SPA's hard-coded `huayApiUrl` no longer matches the Railway service,
edit `index.html` (the line that starts with `huayApiUrl: 'https://...'`),
redeploy, and the SPA will pick up the new endpoint on next page load.

## Backend — Railway (config prepared, deploy manual)

### Files written by this change

| Path | Purpose |
|---|---|
| `Dockerfile.api` | Slim Python 3.11 image; installs `huayapp-api/requirements.txt`, copies `huayapp_scraper/` and `huayapp-api/`; runs `uvicorn` against `$PORT`. |
| `.dockerignore.api` | Excludes frontend bundle, OCR workspace, tests, dev artifacts from the API image. |
| `railway.toml` | Build/deploy config: builds from `Dockerfile.api`, runs the API, exposes `/health` as the healthcheck, sets sensible defaults for `REFRESH_INTERVAL_SECONDS` and `PYTHONUNBUFFERED`. |

### One-time Railway setup (operator, in a browser)

1. Go to <https://railway.app/dashboard> and create (or open) the project
   you want this service in.
2. **Add a Postgres plugin** to the project. Railway will provision a
   database and inject `DATABASE_URL` into every service in the same
   project.
3. **Add a new service → "Deploy from GitHub repo"** (or "Empty service"
   + `railway up` from your workstation).
4. After Railway detects the repo, point the build at the project
   root and select **Dockerfile** as the builder. Override the
   Dockerfile path to `Dockerfile.api` (Railway reads `railway.toml` and
   picks it up automatically when set).
5. Set the service variables (Railway → service → Variables):

   | Name | Value | Notes |
   |---|---|---|
   | `DATABASE_URL` | _(from Postgres plugin)_ | Auto-injected by Railway once the plugin is linked. |
   | `SCRAPE_API_KEY` | `<32+ random bytes>` | Required by the API for protected routes. Use `openssl rand -hex 32`. |
   | `ALLOWED_DOMAINS` | `https://lotto-89ad0.web.app` | Whitelist for the SPA. Comma-separate for multiple origins. |
   | `CORS_ORIGINS` | `https://lotto-89ad0.web.app` | What the SPA presents in the Origin header. |
   | `REFRESH_INTERVAL_SECONDS` | `900` | 15 min between full Huayapp refreshes. |

6. Deploy. Railway builds the image and starts the service.
7. After the first successful deploy, copy the public URL Railway
   assigned (e.g. `https://lotto-api-production.up.railway.app`).
8. Edit `index.html`, set `huayApiUrl` to that URL, then re-run the
   Firebase hosting deploy command from the previous section.

### Verifying

After both deploys, hit these URLs:

* `https://lotto-89ad0.web.app` — the SPA, public.
* `https://<your-railway-url>/health` — should return `{"status": "ok"}`.
* `https://<your-railway-url>/api/lottery-sources` — requires the
  `X-API-Key` header. From the SPA the same value is stored under
  `huayApiKey`.

### Local smoke-test before pushing

```bash
py -3.11 -m venv .venv-api
.venv-api\Scripts\Activate.ps1
pip install -r huayapp-api/requirements.txt
docker build -f Dockerfile.api -t lotto-api:local .
docker run --rm -p 8080:8080 \
    -e DATABASE_PATH=/tmp/lottery.db \
    -e SCRAPE_API_KEY=test-key \
    -e CORS_ORIGINS=http://localhost:8000 \
    lotto-api:local
# → http://localhost:8080/health
```

## Operational notes

* The lifespan loop in `huayapp_api.app` runs `refresh_all_cards` every
  `REFRESH_INTERVAL_SECONDS` (default 900s). With ~140 published Huayapp
  cards, a full pass takes ~15 minutes — keep the interval ≥ 900s so
  successive refreshes don't overlap.
* SQLite fallback: if `DATABASE_URL` is unset, the API writes to
  `lottery.db` on the local filesystem — fine for development, do not
  use in production (no cross-replica state).
* `Config.database_url` is read once at startup. Restart the deploy
  after rotating credentials.