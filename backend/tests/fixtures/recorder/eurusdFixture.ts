/** Hand-built EURUSD Setup B scenario shared by the strategy test and the parity recorder. */
import { Candle } from "../shared/types";
import { StrategyInput } from "../shared/input";

export const SWEEP_T = Date.UTC(2026, 9, 20, 6, 15) / 1000;
export const FLAT_START = Date.UTC(2026, 9, 19, 22, 0) / 1000;

export function aggregate(c: Candle[], sec: number): Candle[] {
  const out: Candle[] = [];
  for (const x of c) {
    const t = x.time - (x.time % sec);
    const l = out[out.length - 1];
    if (l && l.time === t) { l.high = Math.max(l.high, x.high); l.low = Math.min(l.low, x.low); l.close = x.close; }
    else out.push({ ...x, time: t });
  }
  return out;
}

export function buildM15(direction: 1 | -1 = 1, asiaHigh = 1.1038): Candle[] {
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

export function eurInput(m15 = buildM15()): StrategyInput {
  const now = SWEEP_T + 900 + 1;
  return {
    candles: { M15: m15, H1: aggregate(m15, 3600), H4: aggregate(m15, 14400), D1: aggregate(m15, 86400) },
    nowSec: now, livePrice: 1.1003, spread: null, isMarketOpen: true, isRealData: true, dataSource: "test",
    news: { events: [], source: "test" }, day: { trades: 0, losses: 0 },
  };
}


export function eurScenarios(): [string, StrategyInput][] {
  return [["eur_setup_b", eurInput()], ["eur_bias_bearish", eurInput(buildM15(-1))], ["eur_range_too_wide", eurInput(buildM15(1, 1.1055))]];
}
