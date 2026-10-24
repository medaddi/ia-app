/**
 * Unit tests for the shared strategy detectors.
 * Run: node node_modules/tsx/dist/cli.mjs server/strategies/tests/shared.test.ts
 */

import { Candle, closedOnly } from "../shared/types";
import { atrSeries, avgBodySeries, emaSeries, rsiSeries } from "../shared/indicators";
import { detectStructure, detectSwings } from "../shared/structure";
import { detectFvgs, detectOrderBlocks } from "../shared/zones";
import { inLocalWindow, tradingDayKey, tradingWeekKey, windowBounds, zonedToUtc } from "../shared/sessions";
import { dailyWeeklyLevels, equalLevels, findSweeps, Level, roundNumberLevels } from "../shared/liquidity";
import { newsBlock } from "../shared/news";
import { classify, lotSize, rr, scoreChecklist } from "../shared/risk";

let passed = 0;
let failed = 0;
export function check(cond: boolean, name: string, detail = "") {
  if (cond) { console.log(`[PASS] ${name}`); passed++; }
  else { console.error(`[FAIL] ${name} ${detail}`); failed++; }
}

const T0 = Date.UTC(2026, 9, 19, 0, 0) / 1000;
const mk = (rows: [number, number, number, number][], step = 300, t0 = T0): Candle[] =>
  rows.map(([o, h, l, c], i) => ({ time: t0 + i * step, open: o, high: h, low: l, close: c }));

console.log("==================================================");
console.log("SHARED DETECTORS");
console.log("==================================================");

// Indicators
{
  const ema = emaSeries([1, 2, 3, 4, 5, 6], 3);
  check(Number.isNaN(ema[1]) && ema[2] === 2 && Math.abs(ema[5] - 5) < 1e-9, "EMA seeds with SMA and tracks a linear series");
  const flat = Array.from({ length: 30 }, (_, i) => ({ time: i, open: 10, high: 11, low: 9, close: 10 }));
  check(Math.abs(atrSeries(flat, 14)[29] - 2) < 1e-9, "ATR of constant 2-point range = 2");
  const up = rsiSeries(Array.from({ length: 30 }, (_, i) => i), 14);
  check(up[29] === 100, "RSI of a straight rise = 100");
  const ab = avgBodySeries(mk(Array.from({ length: 25 }, () => [10, 11, 9, 10.5] as [number, number, number, number])), 20);
  check(Number.isNaN(ab[19]) && Math.abs(ab[20] - 0.5) < 1e-9, "Average body excludes the current candle");
}

// Swings: peak at index 3, trough at index 7, n = 3
const swingRows: [number, number, number, number][] = [
  [10, 11, 9, 10], [10, 12, 9.5, 11], [11, 13, 10, 12], [12, 15, 11, 14], [14, 14, 11, 12], [12, 13, 10, 11], [11, 12, 9, 10],
  [10, 11, 7, 8], [8, 10, 8.5, 9], [9, 11, 8.8, 10], [10, 12, 9, 11], [11, 14, 10, 13],
];
{
  const c = mk(swingRows);
  const s = detectSwings(c, 3);
  const high = s.find(x => x.kind === "HIGH");
  const low = s.find(x => x.kind === "LOW");
  check(high?.index === 3 && high.price === 15 && high.confirmedIndex === 6, "Swing high confirmed only after 3 right-side candles");
  check(low?.index === 7 && low.price === 7, "Swing low detected at the trough");
  const partial = detectSwings(c.slice(0, 9), 3);
  check(!partial.some(x => x.index === 7), "No swing before its right side has closed (no repaint)");
}

// Structure: bearish BOS then bullish CHoCH with displacement
{
  const rows: [number, number, number, number][] = [];
  for (let i = 0; i < 22; i++) rows.push([100, 100.5, 99.5, 100.2]); // calm base (avg body ~0.2)
  rows.push([100, 101, 99, 100.5], [100.5, 103, 100, 102.5], [102.5, 102.8, 101, 101.5], [101.5, 101.8, 100.6, 101], [101, 101.2, 100.4, 100.8], [100.8, 101, 100.2, 100.6]); // 22-27 swing high 103 @23
  rows.push([100.6, 100.7, 98, 98.2], [98.2, 98.5, 96, 96.4], [96.4, 97.5, 96.2, 97.2], [97.2, 98, 97, 97.8], [97.8, 98.2, 97.4, 98]); // 28-32: breaks low 99.5? swing low 96 @29
  rows.push([98, 104, 97.9, 103.8]); // 33 displacement close above 103
  const c = mk(rows);
  const s = detectSwings(c, 3);
  const { events } = detectStructure(c, s, avgBodySeries(c, 20), 1.5);
  const bull = events.find(e => e.direction === "BULLISH" && e.level === 103);
  check(!!bull && bull.breakIndex === 33, "Bullish break on the candle that CLOSES above the swing high", JSON.stringify(events));
  check(bull?.type === "CHOCH", "Break against the prior bearish trend is labelled CHoCH", bull?.type);
  check((bull?.displacementIndex ?? -1) === 33 && (bull?.displacementMult ?? 0) > 1.5, "Displacement candle body > 1.5x average body");
  const obs = detectOrderBlocks(c, events, "M5");
  const ob = obs.find(o => o.direction === "BULLISH");
  check(ob?.index === 29, "Order block = last bearish candle before the displacement", String(ob?.index));
}

// FVG
{
  const rows: [number, number, number, number][] = [];
  for (let i = 0; i < 16; i++) rows.push([100, 101, 99, 100]);
  rows.push([100, 101, 99.5, 100.8], [100.8, 105, 100.7, 104.8], [104.8, 106, 103, 105.5]); // c1.high 101 < c3.low 103
  rows.push([105.5, 105.6, 103.5, 104]); // touches but not 50% (ce 102)
  const c = mk(rows);
  const f = detectFvgs(c, atrSeries(c, 14), 0.25, "M5");
  check(f.length === 1 && f[0].direction === "BULLISH" && f[0].bottom === 101 && f[0].top === 103, "Bullish FVG c1.high < c3.low", JSON.stringify(f));
  check(f[0]?.state === "OPEN", "FVG not mitigated until 50% filled");
  const c2 = [...c, { time: c[c.length - 1].time + 300, open: 104, high: 104.2, low: 101.8, close: 102.5 }];
  check(detectFvgs(c2, atrSeries(c2, 14), 0.25, "M5")[0].state === "MITIGATED", "FVG mitigated once price reaches 50%");
  const small = detectFvgs(c, atrSeries(c, 14), 5, "M5");
  check(small.length === 0, "Gaps smaller than minAtr × ATR are ignored");
}

// Sweeps
{
  const lvl: Level = { id: "ASIA_L", kind: "ASIA_L", label: "Asia L", price: 99, side: "LOW", time: T0, availableFrom: T0 + 300, weight: 1 };
  const c = mk([[100, 101, 99.5, 100], [100, 100.5, 99.2, 99.8], [99.8, 100, 98.4, 99.6], [99.6, 100, 98, 98.5]]);
  const sw = findSweeps(c, [lvl], 0, c.length - 1, 1);
  check(sw.length === 1 && sw[0].index === 2 && sw[0].extreme === 98.4, "Sweep = wick below level and close back above", JSON.stringify(sw));
  const broken = findSweeps(mk([[100, 101, 99.5, 100], [100, 100.5, 99.2, 99.8], [99.8, 100, 98, 98.5]]), [lvl], 0, 2, 1);
  check(broken.length === 0, "A close beyond the level is a break, not a sweep");
  const eq = equalLevels(detectSwings(mk(swingRows), 3).concat([{ index: 9, time: T0 + 2700, price: 15.05, kind: "HIGH", confirmedIndex: 9, label: "LH", takenIndex: null }]), 1, 0.1, 11);
  check(eq.some(l => l.kind === "EQH"), "Equal highs within 0.1 × ATR become a $$$ level");
  const rn = roundNumberLevels(4003, [10, 50], 1, T0);
  check(rn.some(l => l.price === 4000) && rn.some(l => l.price === 4010) && rn.some(l => l.price === 4050), "Round numbers $10 / $50 around price");
}

// Sessions with DST
{
  // London summer time (BST, UTC+1): 08:00 London = 07:00 UTC on 2026-07-15
  check(zonedToUtc(2026, 7, 15, 8, 0, "Europe/London") === Date.UTC(2026, 6, 15, 7, 0) / 1000, "London 08:00 in summer = 07:00 UTC");
  // London winter (GMT): 08:00 London = 08:00 UTC on 2026-12-15
  check(zonedToUtc(2026, 12, 15, 8, 0, "Europe/London") === Date.UTC(2026, 11, 15, 8, 0) / 1000, "London 08:00 in winter = 08:00 UTC");
  // US DST starts 2nd Sunday of March, UK last Sunday: on 2026-03-16 NY is UTC-4 while London is UTC+0
  check(zonedToUtc(2026, 3, 16, 8, 30, "America/New_York") === Date.UTC(2026, 2, 16, 12, 30) / 1000, "NY 08:30 during the US/UK DST gap = 12:30 UTC");
  check(zonedToUtc(2026, 1, 15, 8, 30, "America/New_York") === Date.UTC(2026, 0, 15, 13, 30) / 1000, "NY 08:30 in winter = 13:30 UTC");
  const w = windowBounds("2026-10-26", "Europe/London", "08:00", "11:00");
  check(w.startSec === Date.UTC(2026, 9, 26, 8, 0) / 1000, "After the October clock change London 08:00 = 08:00 UTC");
  check(inLocalWindow(Date.UTC(2026, 6, 15, 7, 30) / 1000, "Europe/London", "08:00", "11:00"), "07:30 UTC in July is inside London 08:00-11:00");
  check(!inLocalWindow(Date.UTC(2026, 11, 15, 7, 30) / 1000, "Europe/London", "08:00", "11:00"), "07:30 UTC in December is outside London 08:00-11:00");
  check(tradingDayKey(Date.UTC(2026, 9, 20, 22, 0) / 1000) === "2026-10-21", "Trading day rolls at 17:00 New York");
  check(tradingWeekKey(Date.UTC(2026, 9, 21, 12, 0) / 1000) === "2026-10-19", "Trading week key = Monday");
}

// PDH / PDL
{
  const day1 = Date.UTC(2026, 9, 19, 22, 0) / 1000; // trading day 2026-10-20
  const c: Candle[] = [];
  for (let i = 0; i < 96; i++) c.push({ time: day1 + i * 900, open: 100, high: 100 + (i === 40 ? 5 : 1), low: 100 - (i === 60 ? 4 : 1), close: 100 });
  for (let i = 0; i < 10; i++) c.push({ time: day1 + 86400 + i * 900, open: 101, high: 102, low: 100, close: 101 });
  const lv = dailyWeeklyLevels(c);
  check(lv.find(l => l.kind === "PDH")?.price === 105 && lv.find(l => l.kind === "PDL")?.price === 96, "PDH/PDL from the previous trading day", JSON.stringify(lv));
}

// News
{
  const t = Date.UTC(2026, 9, 28, 12, 30) / 1000;
  const ev = [{ time: t, currency: "USD", title: "CPI m/m", impact: "High" as const }, { time: t, currency: "JPY", title: "BOJ", impact: "High" as const }];
  const rule = { currencies: ["USD"], keywords: ["CPI", "NFP", "FOMC"], minutesBefore: 30, minutesAfter: 30 };
  check(newsBlock(t - 29 * 60, ev, rule).blocked, "Blocked 29 min before USD CPI");
  check(!newsBlock(t - 31 * 60, ev, rule).blocked, "Not blocked 31 min before");
  check(newsBlock(t + 30 * 60, ev, rule).blocked && !newsBlock(t + 31 * 60, ev, rule).blocked, "Blocked until 30 min after");
  check(!newsBlock(t, ev, { ...rule, currencies: ["EUR"] }).blocked, "Other currencies' news does not block");
}

// Risk
{
  const gold = { symbol: "XAUUSD" as const, displaySymbol: "XAU/USD" as const, decimals: 2, pipSize: 0.1, contractSize: 100, minLot: 0.01, lotStep: 0.01 };
  const eur = { symbol: "EURUSD" as const, displaySymbol: "EUR/USD" as const, decimals: 5, pipSize: 0.0001, contractSize: 100000, minLot: 0.01, lotStep: 0.01 };
  check(lotSize(gold, 10000, 1, 4000, 3995) === 0.2, "Gold: 1% of 10k, $5 stop = 0.20 lot");
  check(lotSize(eur, 10000, 1, 1.1, 1.098) === 0.5, "EURUSD: 1% of 10k, 20 pip stop = 0.50 lot");
  check(lotSize(gold, 500, 1, 4000, 3992) === 0, "Below minimum lot returns 0 (cannot respect risk)");
  check(Math.abs(rr(100, 98, 106) - 3) < 1e-9, "R:R = reward / risk");
  const items = [{ key: "a", rule: "", ruleAr: "", passed: true, detail: "", weight: 30, required: true }, { key: "b", rule: "", ruleAr: "", passed: false, detail: "", weight: 10, required: false }];
  check(scoreChecklist(items) === 75 && classify(75, true, { signal: 75, watch: 60 }) === "SIGNAL" && classify(70, true, { signal: 75, watch: 60 }) === "WATCH" && classify(90, false, { signal: 75, watch: 60 }) === "NO_TRADE", "Score thresholds: >=75 signal, 60-74 watch, required failure = no trade");
}

// No look-ahead
{
  const c = mk([[1, 2, 0, 1], [1, 2, 0, 1], [1, 2, 0, 1]]);
  check(closedOnly(c, 300, T0 + 900 - 1).length === 2 && closedOnly(c, 300, T0 + 900).length === 3, "closedOnly keeps only candles closed at now");
}

console.log("==================================================");
console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
console.log("==================================================");
if (failed > 0) process.exit(1);
