# Cost Optimization for Huayapp Ingestion

## Goal

Reduce CPU and memory usage of the Railway ingestion service while keeping the
existing API response shapes and lottery-result correctness intact. The
accepted freshness target is a maximum refresh interval of approximately 30
minutes for the in-process refresh loop.

## Scope

This change covers the current FastAPI service and the frontend polling that
reads it. It does not move deployment to Railway Cron, change database
providers, or alter authentication in this pass.

## Design

### Refresh execution

`refresh_all_cards` will create one browser session and navigate to the source
page once per refresh. It will wait for the page once, parse the current card
list, and then decode the published cards from that already-loaded page. The
existing per-card navigation and two-second delay will be removed. A caller
that supplies a page will continue to work.

The refresh interval default will change from 900 seconds to 1800 seconds.
The Railway config default will match the application default, while an
explicit `REFRESH_INTERVAL_SECONDS` environment variable remains authoritative.

### Resource ownership

The refresh function will track whether the store was supplied by the caller.
Stores opened internally will be closed in a `finally` block; externally-owned
stores will remain open for the caller to manage.

### Frontend polling

The frontend's default remote polling interval will change from 60 seconds to
300 seconds. Existing manual refresh buttons and API payload shapes remain
unchanged.

## Error handling

Per-card decode failures remain isolated and are reported in the existing
failure list. A page-load failure still aborts the refresh as before. Browser,
context, page, and internally-created store resources must be released even
when a card or refresh raises an exception.

## Testing

Add or update tests at public seams to verify:

1. The refresh interval defaults to 1800 seconds and an environment override
   still works.
2. A refresh using a fake page navigates to the source once, not once per card,
   while preserving successful result persistence and failure reporting.
3. A caller-owned store is not closed by the refresh function, while an
   internally-created store is closed.
4. The frontend polling default is 300 seconds and the existing API calls are
   still present.

Existing unrelated working-tree changes will be preserved.
