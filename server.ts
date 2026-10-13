// =========================================================
// Lottery Snapshot API (Bun + SQLite)
// รัน: bun run server.ts
// Endpoint: GET /api/lottery-snapshot
// =========================================================

import { Database } from "bun:sqlite";

// 1. Init SQLite (auto create on first run)
const db = new Database("lottery.db", { create: true });

db.run(`
  CREATE TABLE IF NOT EXISTS yiki_results (
    round   TEXT PRIMARY KEY,
    time    TEXT,
    top3    TEXT,
    bot2    TEXT
  )
`);

db.run(`
  CREATE TABLE IF NOT EXISTS stocks_results (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol  TEXT,
    date    TEXT,
    top3    TEXT,
    bot2    TEXT,
    open    TEXT,
    close   TEXT
  )
`);

// Huayapp scraper tables. These are deliberately separate from the legacy
// yiki/stocks tables so existing screens and data remain unchanged.
db.run(`
  CREATE TABLE IF NOT EXISTS lottery_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    lottery_id TEXT NOT NULL,
    lottery_name TEXT NOT NULL,
    category TEXT NOT NULL,
    result_date TEXT NOT NULL,
    result_time TEXT,
    round TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    scraped_at TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_text TEXT,
    UNIQUE(source, lottery_id, result_date, round)
  )
`);

db.run(`
  CREATE TABLE IF NOT EXISTS lottery_prizes (
    result_id INTEGER NOT NULL REFERENCES lottery_results(id) ON DELETE CASCADE,
    prize_name TEXT NOT NULL,
    numbers_json TEXT NOT NULL,
    PRIMARY KEY(result_id, prize_name)
  )
`);

function ensureColumn(table: string, column: string, definition: string) {
  const columns = db.query(`PRAGMA table_info(${table})`).all() as Array<{ name: string }>;
  if (!columns.some((item) => item.name === column)) {
    db.run(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }
}

ensureColumn("lottery_results", "source_item_id", "TEXT NOT NULL DEFAULT ''");
ensureColumn("lottery_results", "country", "TEXT NOT NULL DEFAULT ''");
ensureColumn("lottery_results", "metadata_json", "TEXT NOT NULL DEFAULT '{}'");

db.run(`
  CREATE TABLE IF NOT EXISTS lottery_sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'unavailable',
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_error TEXT,
    result_count INTEGER NOT NULL DEFAULT 0
  )
`);

// 2. Seed mock data (only if empty)
const yikiCount = db.query("SELECT COUNT(*) as c FROM yiki_results").get() as { c: number };
if (yikiCount.c === 0) {
  const seeds = [
    ["882401","14:32:11","582","47"],["882400","14:28:31","193","06"],
    ["882399","14:24:51","720","88"],["882398","14:21:11","416","23"],
    ["882397","14:17:31","037","59"],["882396","14:13:51","654","71"],
    ["882395","14:10:11","289","12"],["882394","14:06:31","905","44"],
    ["882393","14:02:51","178","30"],["882392","13:59:11","523","67"],
  ];
  const stmt = db.prepare("INSERT INTO yiki_results (round, time, top3, bot2) VALUES (?,?,?,?)");
  for (const r of seeds) stmt.run(...(r as [string,string,string,string]));
}

const stockCount = db.query("SELECT COUNT(*) as c FROM stocks_results").get() as { c: number };
if (stockCount.c === 0) {
  const stmt = db.prepare("INSERT INTO stocks_results (symbol, date, top3, bot2, open, close) VALUES (?,?,?,?,?,?)");
  const stocks = [
    ["SET","01/10","582","47","1,432.50","1,438.20"],
    ["SET","30/09","193","06","1,425.10","1,432.50"],
    ["HSI","01/10","720","88","21,540","21,650"],
    ["HSI","30/09","416","23","21,420","21,540"],
    ["N225","01/10","037","59","38,200","38,400"],
    ["SSE","01/10","654","71","3,250","3,272"],
    ["KOSPI","01/10","289","12","2,580","2,594"],
    ["DJI","30/09","905","44","39,200","39,127"],
  ];
  for (const r of stocks) stmt.run(...(r as [string,string,string,string,string,string]));
}

// 3. Try to fetch live data (best effort, fall back to DB)
async function fetchYiki(): Promise<any[]> {
  // TODO: replace with real yiki API when available
  // For now, generate a "live" round from current time
  const now = Date.now();
  const roundBase = 882400;
  const offset = Math.floor((now / 90000) % 10);
  const baseRound = roundBase + 1 - offset;
  const rows = db.query("SELECT * FROM yiki_results ORDER BY round DESC LIMIT 20").all() as any[];
  // mark rows newer than baseRound as "fresh"
  return rows.map((r, i) => ({ ...r, _fresh: i < 3 }));
}

async function fetchStocks(): Promise<any[]> {
  // Optional: real Yahoo Finance call
  // const symbols = ['^SET', '^HSI', '^N225'];
  // const r = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbols.join(',')}`);
  // ... map to { symbol, date, top3, bot2, open, close }
  return db.query("SELECT * FROM stocks_results ORDER BY id DESC LIMIT 20").all() as any[];
}

function fetchHuayapp(lotteryId?: string, limit = 100): any[] {
  const safeLimit = Math.max(1, Math.min(Math.trunc(limit) || 100, 500));
  const rows = lotteryId
    ? db.query(`SELECT * FROM lottery_results WHERE source = 'huayapp.com' AND lottery_id = ? ORDER BY result_date DESC, id DESC LIMIT ${safeLimit}`).all(lotteryId) as any[]
    : db.query(`SELECT * FROM lottery_results WHERE source = 'huayapp.com' ORDER BY result_date DESC, id DESC LIMIT ${safeLimit}`).all() as any[];

  return rows.map((row) => ({
    source: row.source,
    lottery_id: row.lottery_id,
    lottery_name: row.lottery_name,
    category: row.category,
    result_date: row.result_date,
    result_time: row.result_time,
    round: row.round || null,
    status: row.status,
    scraped_at: row.scraped_at,
    source_url: row.source_url,
    source_item_id: row.source_item_id || row.lottery_id,
    country: row.country || "",
    metadata: JSON.parse(row.metadata_json || "{}"),
    prizes: (db.query("SELECT prize_name, numbers_json FROM lottery_prizes WHERE result_id = ? ORDER BY rowid").all(row.id) as any[])
      .map((prize) => ({ prize_name: prize.prize_name, numbers: JSON.parse(prize.numbers_json) })),
  }));
}

function safeLimit(value: string | null, fallback = 100): number {
  return Math.max(1, Math.min(Math.trunc(Number(value || fallback)) || fallback, 500));
}

function fetchLotteryResults(url: URL): any[] {
  const conditions: string[] = [];
  const args: string[] = [];
  const filters: Array<[string, string]> = [
    ["source", "source"],
    ["country", "country"],
    ["category", "category"],
    ["date", "result_date"],
  ];
  for (const [param, column] of filters) {
    const value = url.searchParams.get(param);
    if (value) {
      conditions.push(`${column} = ?`);
      args.push(value);
    }
  }
  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
  const limit = safeLimit(url.searchParams.get("limit"));
  const rows = db.query(`SELECT * FROM lottery_results ${where} ORDER BY result_date DESC, id DESC LIMIT ${limit}`).all(...args) as any[];
  return rows.map((row) => ({
    source: row.source,
    source_item_id: row.source_item_id || row.lottery_id,
    lottery_id: row.lottery_id,
    lottery_name: row.lottery_name,
    category: row.category,
    country: row.country || "",
    result_date: row.result_date,
    result_time: row.result_time,
    round: row.round || null,
    status: row.status,
    scraped_at: row.scraped_at,
    source_url: row.source_url,
    metadata: JSON.parse(row.metadata_json || "{}"),
    prizes: (db.query("SELECT prize_name, numbers_json FROM lottery_prizes WHERE result_id = ? ORDER BY rowid").all(row.id) as any[])
      .map((prize) => ({ prize_name: prize.prize_name, numbers: JSON.parse(prize.numbers_json) })),
  }));
}

function fetchSourceStates(): any[] {
  return db.query("SELECT * FROM lottery_sources ORDER BY category, name, source_id").all() as any[];
}

const PORT = Number(process.env.PORT) || 8787;
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

const server = Bun.serve({
  port: PORT,
  hostname: "0.0.0.0",
  async fetch(req: Request) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (url.pathname === "/api/lottery-snapshot") {
      const [yiki, stocks] = await Promise.all([fetchYiki(), fetchStocks()]);
      const huayapp = fetchHuayapp(url.searchParams.get("lottery_id") || undefined);
      const results = fetchLotteryResults(url);
      const sources = fetchSourceStates();
      return Response.json({ yiki, stocks, huayapp, results, sources, serverTime: new Date().toISOString() }, { headers: CORS });
    }
    if (url.pathname === "/api/lottery-results") {
      return Response.json({ results: fetchLotteryResults(url), serverTime: new Date().toISOString() }, { headers: CORS });
    }
    if (url.pathname === "/api/lottery-sources") {
      return Response.json({ sources: fetchSourceStates(), serverTime: new Date().toISOString() }, { headers: CORS });
    }
    if (url.pathname === "/api/huayapp-results") {
      const huayapp = fetchHuayapp(
        url.searchParams.get("lottery_id") || undefined,
        Number(url.searchParams.get("limit") || 100),
      );
      return Response.json({ huayapp, serverTime: new Date().toISOString() }, { headers: CORS });
    }
    if (url.pathname === "/api/health") {
      return Response.json({ ok: true, ts: new Date().toISOString() }, { headers: CORS });
    }
    if (url.pathname === "/") {
      return new Response("Lottery Snapshot API. Use /api/lottery-snapshot", { headers: CORS });
    }
    return new Response("Not found", { status: 404, headers: CORS });
  },
});

console.log(`🚀 Lottery API running at http://localhost:${server.port}`);
console.log(`   GET /api/lottery-snapshot`);
console.log(`   GET /api/health`);
