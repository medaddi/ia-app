/**
 * XAUUSD strategy test on a hand-built London-open scenario (2026-10-20, London on BST = UTC+1):
 * Asia range 3997–4012 → decline → M5 swing high 4003 → sweep of the Asia low at 07:05 UTC
 * (08:05 London) → displacement CHoCH above 4003 → bullish FVG 3999.5–4001 → limit at 4000.25.
 */

import { evaluateXauusd } from "../xauusd/strategy";
import { buildM5, trend, xauInput as input } from "./fixtures";

let passed = 0, failed = 0;
const check = (cond: boolean, name: string, detail = "") => {
  if (cond) { console.log(`[PASS] ${name}`); passed++; } else { console.error(`[FAIL] ${name} ${detail}`); failed++; }
};

console.log("==================================================");
console.log("XAUUSD STRATEGY");
console.log("==================================================");

const r = evaluateXauusd(input());
const s = r.setup;
const anchors = s?.anchors as any;
check(r.bias.direction === "BULLISH", "1. Bias bullish (H1 above EMA200, H4 last break bullish)", r.bias.detail);
check(!!s && s.direction === "BUY" && s.entryType === "LIMIT", "2. BUY limit setup found", r.headline);
check(anchors?.sweep?.level?.kind === "ASIA_L" && anchors.sweep.level.price === 3997, "3. Sweep of the Asia low 3997", JSON.stringify(anchors?.sweep?.level));
check(anchors?.mss?.type === "CHOCH" && anchors.mss.level === 4003, "4. M5 CHoCH above 4003 with displacement", JSON.stringify(anchors?.mss));
check(anchors?.poi?.kind === "FVG" && s?.entry === 4000.25, "5. Limit at FVG 50% = 4000.25", `${anchors?.poi?.kind} ${s?.entry}`);
check(!!s && s.sl < 3996.5 && s.slDistance >= 2 && s.slDistance <= 8, "6. SL beyond the sweep wick, within $2–$8", `${s?.sl} ${s?.slDistance}`);
check(!!s && Math.abs(s.tp1 - (s.entry + s.slDistance)) < 0.011, "7. TP1 = 1R", String(s?.tp1));
check(s?.tp2 === 4012 && (s?.rrTp2 ?? 0) >= 2, "8. TP2 = Asia high (opposing liquidity), R:R >= 2", `${s?.tp2} ${s?.rrTp2}`);
check(!!s && s.tp3 > s.tp2, "9. TP3 beyond TP2", String(s?.tp3));
check(r.status === "SIGNAL" && r.score >= 75, "10. Score >= 75 → SIGNAL", `${r.status} ${r.score} ${r.rejection}`);
check(r.canNotify && s?.isFresh === true && s.lifecycle.state === "PENDING", "11. Fresh pending signal can notify", `${r.canNotify} ${s?.lifecycle.state}`);
check(r.signal?.symbol === "XAUUSD" && r.signal.entry_type === "LIMIT" && r.signal.checklist.length === r.checklist.length, "12. Signal JSON matches the spec shape");
check(!!s && s.expiresAt === s.signalTime + 45 * 60, "13. Pending order expires after 45 minutes");

{
  const bear = input();
  bear.candles.H4 = trend(bear.nowSec - (bear.nowSec % 14400), 14400, 120, 4300, -2.5, 12);
  const rb = evaluateXauusd(bear);
  check(rb.bias.direction === "NEUTRAL" && rb.status === "NO_TRADE" && !rb.setup, "14. H4 and H1 disagree → NO TRADE", rb.bias.detail);
}
{
  const m5 = buildM5().map(c => ({ ...c, time: c.time - 2 * 3600 })); // 05:05 UTC sweep: before the London kill zone
  const ro = evaluateXauusd(input({}, m5));
  const kz = ro.checklist.find(c => c.key === "killzone");
  check(ro.status !== "SIGNAL" && (kz ? !kz.passed : true), "15. Outside the kill zones → no signal", `${ro.status} ${ro.rejection}`);
}
{
  const base = input();
  const rn = evaluateXauusd({ ...base, news: { events: [{ time: base.nowSec + 600, currency: "USD", title: "CPI m/m", impact: "High" }], source: "test" } });
  check(rn.status === "NO_TRADE" && rn.checklist.find(c => c.key === "news")?.passed === false, "16. USD CPI in 10 minutes blocks the trade");
  const rd = evaluateXauusd({ ...base, day: { trades: 2, losses: 0 } });
  check(rd.status === "NO_TRADE" && rd.checklist.find(c => c.key === "daily")?.passed === false, "17. Max 2 trades per day");
}
{
  const base = input();
  const future = buildM5();
  future.push({ time: future[future.length - 1].time + 300, open: 4005.5, high: 4005.6, low: 3990, close: 3991 });
  const withFuture = evaluateXauusd({ ...base, candles: { ...base.candles, M5: future } });
  check(JSON.stringify(withFuture.signal) === JSON.stringify(r.signal), "18. A candle that has not closed yet does not change the signal (no look-ahead)");
  check(JSON.stringify(evaluateXauusd(input())) === JSON.stringify(r), "19. Deterministic: same candles → same result");
}

console.log("==================================================");
console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
console.log("==================================================");
if (failed > 0) process.exit(1);
