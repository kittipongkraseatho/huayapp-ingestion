# Huayapp API for Railway

This is the deployable API service for Huayapp results. It reuses the verified
`huayapp_scraper` package from the repository root and is independent from the
Bun/Firebase frontend API.

## Endpoints

```text
GET  /health
GET  /api/huayapp-results?lottery_id=100&limit=20
GET  /api/stats
POST /api/scrape/latest       JSON: {"lottery_id":"100"}
```

Every `/api/*` request requires both a valid `X-API-Key` header and an allowed
client. A request is accepted when its IP matches `ALLOWED_IPS` or its browser
`Origin` host matches `ALLOWED_DOMAINS`. If neither allowlist is configured,
the API fails closed with `503`. The `/health` endpoint is intentionally public
so Railway can perform its health check.

## Local Docker test

Run these commands from the repository root, because the Dockerfile copies the
shared scraper package:

```powershell
docker build -f huayapp-api/Dockerfile -t huayapp-api .
docker run --rm -p 8080:8080 -e SCRAPE_API_KEY=change-me huayapp-api
```

Then open `http://localhost:8080/health`.

## Railway deployment

Create a new Railway service from this repository and set the Dockerfile path
to `huayapp-api/Dockerfile`. Railway injects `PORT`; the container listens on
that port. Attach a Railway Volume mounted at `/data` so SQLite survives
restarts and redeployments. Set these variables:

```text
DATABASE_PATH=/data/lottery.db
SOURCE_URL=https://huayapp.com/
SCRAPE_API_KEY=<long-random-secret>
CORS_ORIGINS=https://your-frontend-domain.web.app
ALLOWED_DOMAINS=your-frontend-domain.web.app
ALLOWED_IPS=203.0.113.10,198.51.100.0/24
TRUST_PROXY_HEADERS=true
```

Configure the service health check path as `/health`, then generate a public
domain. Deploying with the Railway CLI from the repository root is also
possible after linking a project:

```powershell
railway link
railway up
```

The scraper is intentionally not run on every GET request. Trigger
`POST /api/scrape/latest` from a scheduler or a protected admin job, then read
the stored data using `GET /api/huayapp-results`.

For browser calls, send the frontend's exact origin in `ALLOWED_DOMAINS`. For
server-to-server calls, there is normally no `Origin` header, so add the
caller's fixed public IP or CIDR to `ALLOWED_IPS`. The API uses Railway's
forwarded client IP when `TRUST_PROXY_HEADERS=true`; only enable that when the
service is reached through the trusted Railway proxy.
