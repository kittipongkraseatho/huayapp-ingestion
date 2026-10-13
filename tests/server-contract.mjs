import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../server.ts', import.meta.url), 'utf8');

assert.match(source, /lottery_sources/, 'source health table is preserved');
assert.match(source, /\/api\/lottery-results/, 'unified results route exists');
assert.match(source, /\/api\/lottery-sources/, 'source status route exists');
assert.match(source, /lottery-snapshot/, 'legacy snapshot route remains');
assert.match(source, /yiki/, 'legacy yiki snapshot key remains');
assert.match(source, /stocks/, 'legacy stocks snapshot key remains');
assert.match(source, /huayapp/, 'legacy huayapp snapshot key remains');

console.log('Server API contract: PASS');
