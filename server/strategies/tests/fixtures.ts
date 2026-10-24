/** Hand-built XAUUSD London-open scenario shared by the strategy and agent tests. */
import { Candle } from "../shared/types";
import { StrategyInput } from "../shared/input";

export const SWEEP_T = Date.UTC(2026, 9, 20, 7, 5) / 1000;

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

export function buildM5(): Candle[] {
  const explicit: [number, number, number, number][] = [
    [4003, 4003.5, 4001, 4001.5], [4001.5, 4002, 3999.5, 4000], [4000, 4000.5, 3998, 3998.6], [3998.6, 4000, 3998.5, 3999.8],
    [3999.8, 4001, 3999.2, 4000.8], [4000.8, 4002, 4000.2, 4001.6], [4001.6, 4003, 4001, 4002.2], [4002.2, 4002.5, 4000.5, 4000.8],
    [4000.8, 4001.2, 3999.6, 3999.9], [3999.9, 4000.2, 3999, 3999.3],
    [3999.3, 3999.5, 3996.5, 3999], // 80: sweep of Asia low 3997
    [3999, 4005.5, 3998.8, 4005], // 81: displacement, CHoCH above 4003
    [4005, 4006, 4001, 4005.5], // 82: leaves FVG 3999.5–4001
  ];
  const start = Date.UTC(2026, 9, 19, 0, 0) / 1000;
  const firstExplicit = SWEEP_T - 10 * 300;
  const out: Candle[] = [];
  for (let t = start, i = 0; t < firstExplicit; t += 300, i++) {
    const tri = (Math.abs((i % 10) - 5) / 5) * 2 - 1;
    const mid = 4001 + 1.5 * tri;
    let high = mid + 0.6, low = mid - 0.6;
    if (t === Date.UTC(2026, 9, 19, 10, 0) / 1000) high = 4020; // previous day high
    if (t === Date.UTC(2026, 9, 20, 1, 0) / 1000) high = 4012; // Asia high
    if (t === Date.UTC(2026, 9, 20, 2, 0) / 1000) low = 3997; // Asia low
    out.push({ time: t, open: mid - 0.2, high, low, close: mid + 0.2 });
  }
  explicit.forEach(([o, h, l, c], k) => out.push({ time: firstExplicit + k * 300, open: o, high: h, low: l, close: c }));
  return out;
}

export function trend(endSec: number, step: number, n: number, from: number, slope: number, amp: number): Candle[] {
  const out: Candle[] = [];
  for (let i = 0; i < n; i++) {
    const tri = (Math.abs((i % 8) - 4) / 4) * 2 - 1;
    const mid = from + i * slope + amp * tri;
    out.push({ time: endSec - (n - i) * step, open: mid - amp * 0.2, high: mid + amp * 0.5, low: mid - amp * 0.5, close: mid + amp * 0.2 });
  }
  return out;
}

export function xauInput(overrides: Partial<StrategyInput> = {}, m5 = buildM5()): StrategyInput {
  const now = m5[m5.length - 1].time + 300 + 1;
  const hourStart = now - (now % 3600);
  return {
    candles: {
      M5: m5,
      M15: aggregate(m5, 900),
      H1: trend(hourStart, 3600, 300, 3890, 0.37, 3),
      H4: trend(now - (now % 14400), 14400, 120, 3700, 2.5, 12),
    },
    nowSec: now,
    livePrice: m5[m5.length - 1].close,
    spread: null,
    isMarketOpen: true,
    isRealData: true,
    dataSource: "test",
    news: { events: [], source: "test" },
    day: { trades: 0, losses: 0 },
    ...overrides,
  };
}

