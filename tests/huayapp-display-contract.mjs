import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

assert.match(html, /fetchIntervalSec:\s*300/, 'remote polling defaults to five minutes');
assert.match(html, /id="huayapp-round-filter"/, 'Huayapp round filter is present');
assert.match(html, /huayapp-results\?limit=500/, 'Huayapp fetch requests all available results');
assert.match(html, /selectedHuayappRound/, 'Huayapp selection state is present');
assert.match(html, /id="stockMarketFlag"/, 'selected market flag is visible');
assert.match(html, /function updateStockMarketIndicator/, 'selected market flag updates with the dropdown');
assert.match(html, /🇭🇰 HSI/, 'admin market options include country flags');
assert.match(html, /payload\.huayapp/, 'Huayapp response is rendered from API payload');
assert.match(html, /id="lottery-results-panel"/, 'unified lottery results panel is present');
assert.match(html, /id="lottery-source-filter"/, 'source filter is present');
assert.match(html, /id="lottery-country-filter"/, 'country filter is present');
assert.match(html, /id="lottery-category-filter"/, 'category filter is present');
assert.match(html, /id="lottery-date-filter"/, 'date filter is present');
assert.match(html, /id="btn-lottery-refresh"/, 'unified refresh button is present');
assert.match(html, /id="lottery-source-status"/, 'source status panel is present');
assert.match(html, /\/api\/lottery-results/, 'unified results API is fetched');
assert.match(html, /\/api\/lottery-sources/, 'source status API is fetched');
assert.match(html, /source_url/, 'source URL is rendered');

console.log('Huayapp display contract: PASS');
