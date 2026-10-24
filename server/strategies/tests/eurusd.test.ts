/**
 * EURUSD strategy test: Setup B (Asian range false breakout) on a hand-built scenario.
 * 5 weeks of H4 uptrend (HH/HL, EMA50 > EMA200) → flat Asian range 1.10000–1.10380 (38 pips)
 * → 06:15 UTC (07:15 London) candle wicks to 1.09960 and closes back inside at 1.10030 → BUY.
 */

import { Candle } from "../shared/types";
import { evaluateEurusd } from "../eurusd/strategy";
import { StrategyInput } from "../shared/input";

let passed = 0, failed = 0;
const check = (cond: boolean, name: string, detail = "") => {
  if (cond) { console.log(`[PASS] ${name}`); passed++; } else { console.error(`[FAIL] ${name} ${detail}`); failed++; }
};

const SWEEP_T = Date.UTC(2026, 9, 20, 6, 15) / 1000;
const FLAT_START = Date.UTC(2026, 9, 19, 22, 0) / 1000;

function aggregate(c: Candle[], sec: number): Candle[] {
  const out: Candle[] = [];
  for (const x of c) {
    const t = x.time - (x.time % sec);
    const l = out[out.length - 1];
    if (l && l.time === t) { l.high = Math.max(l.high, x.high); l.low = Math.min(l.low, x.low); l.close = x.close; }
    else out.push({ ...x, time: t });
  }
  return out;
}

function buildM15(direction: 1 | -1 = 1, asiaHigh = 1.1038): Candle[] {
  const out: Candle[] = [];
  const start = SWEEP_T - 35 * 86400;
  const nTrend = Math.round((FLAT_START - start) / 900);
  for (let i = 0; i < nTrend; i++) {
    const tri = (Math.abs((i % 192) - 96) / 96) * 2 - 1;
    const base = direction === 1 ? 1.0960 - (nTrend - i) * 0.000025 : 1.1200 + (nTrend - i) * 0.000025;
    const mid = base + 0.003 * tri;
    out.push({ time: start + i * 900, open: mid - 0.0001, high: mid + 0.0003, low: mid - 0.0003, close: mid + 0.0001 });
  }
  for (let t = FLAT_START, k = 0; t < SWEEP_T; t += 900, k++) {
    const mid = 1.1019 + (k % 2 ? 0.0001 : -0.0001);
    let high = mid + 0.0002, low = mid - 0.0002;
    if (t === Date.UTC(2026, 9, 20, 1, 0) / 1000) high = asiaHigh;
    if (t === Date.UTC(2026, 9, 20, 2, 0) / 1000) low = 1.1;
    out.push({ time: t, open: mid - 0.0001, high, low, close: mid + 0.0001 });
  }
  out.push({ time: SWEEP_T, open: 1.1004, high: 1.1007, low: 1.0996, close: 1.1003 });
  return out;
}

function input(m15 = buildM15()): StrategyInput {
  const now = SWEEP_T + 900 + 1;
  return {
    candles: { M15: m15, H1: aggregate(m15, 3600), H4: aggregate(m15, 14400), D1: aggregate(m15, 86400) },
    nowSec: now, livePrice: 1.1003, spread: null, isMarketOpen: true, isRealData: true, dataSource: "test",
    news: { events: [], source: "test" }, day: { trades: 0, losses: 0 },
  };
}

console.log("==================================================");
console.log("EURUSD STRATEGY");
console.log("==================================================");

const r = evaluateEurusd(input());
const s = r.setup;
check(r.bias.direction === "BULLISH", "1. H4 bias bullish (close > EMA200, EMA50 > EMA200, HH/HL)", r.bias.detail);
check(s?.setup === "B" && s.direction === "BUY" && s.entryType === "MARKET", "2. Setup B BUY at market", `${s?.setup} ${s?.direction} ${r.headline}`);
check(s?.entry === 1.1003, "3. Entry at the close of the false-breakout candle", String(s?.entry));
check(!!s && s.sl <= 1.0993 + 1e-9 && s.slPips >= 10 && s.slPips <= 25, "4. SL = the wider of (wick − 3 pips) and 1.5 × ATR, within 8–25 pips", `${s?.sl} ${s?.slPips}`);
check(s?.tp2 === 1.1038 && (s?.rrTp2 ?? 0) >= 2, "5. TP2 = opposite side of the Asian range, R:R >= 2", `${s?.tp2} ${s?.rrTp2}`);
check(!!s && Math.abs(s.tp1 - (s.entry + (s.entry - s.sl))) < 2e-5, "6. TP1 = 1R", String(s?.tp1));
check(r.status === "SIGNAL" && r.score >= 75 && r.canNotify, "7. Score >= 75 → fresh SIGNAL", `${r.status} ${r.score} ${r.rejection}`);
check(r.signal?.symbol === "EURUSD" && r.signal.setup === "B" && r.signal.entry_type === "MARKET", "8. Signal JSON (EURUSD, setup B, MARKET)");
check(r.checklist.some(c => c.key === "window" && c.passed && c.detail.startsWith("London")), "9. Inside the London window (07:00–10:30 London)");

{
  const rb = evaluateEurusd(input(buildM15(-1)));
  check(rb.status !== "SIGNAL", "10. False breakout against the H4 bias is not traded", `${rb.status} ${rb.bias.direction}`);
}
{
  const rw = evaluateEurusd(input(buildM15(1, 1.1055))); // 55-pip Asian range
  check(rw.setup?.setup !== "B", "11. Asian range > 40 pips → no Setup B", `${rw.setup?.setup} ${rw.headline}`);
}
check(JSON.stringify(evaluateEurusd(input())) === JSON.stringify(r), "12. Deterministic: same candles → same result");

console.log("==================================================");
console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
console.log("==================================================");
if (failed > 0) process.exit(1);
