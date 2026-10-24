import { Candle } from "./types";

/** EMA seeded with the SMA of the first `period` values. NaN until enough data. */
export function emaSeries(values: number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = ema;
  for (let i = period; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

/** Wilder ATR. NaN until `period` true ranges exist. */
export function atrSeries(c: Candle[], period = 14): number[] {
  const out = new Array<number>(c.length).fill(NaN);
  if (c.length <= period) return out;
  let sum = 0;
  for (let i = 1; i <= period; i++) sum += trueRange(c, i);
  let atr = sum / period;
  out[period] = atr;
  for (let i = period + 1; i < c.length; i++) {
    atr = (atr * (period - 1) + trueRange(c, i)) / period;
    out[i] = atr;
  }
  return out;
}

function trueRange(c: Candle[], i: number): number {
  const p = c[i - 1].close;
  return Math.max(c[i].high - c[i].low, Math.abs(c[i].high - p), Math.abs(c[i].low - p));
}

/** Wilder RSI. NaN until `period` changes exist. */
export function rsiSeries(closes: number[], period = 14): number[] {
  const out = new Array<number>(closes.length).fill(NaN);
  if (closes.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gain += d; else loss -= d;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

export const body = (c: Candle) => Math.abs(c.close - c.open);

/** Average body of the `period` candles BEFORE index i (the candle itself is excluded). */
export function avgBodySeries(c: Candle[], period = 20): number[] {
  const out = new Array<number>(c.length).fill(NaN);
  let sum = 0;
  for (let i = 0; i < c.length; i++) {
    if (i >= period) out[i] = sum / period;
    sum += body(c[i]);
    if (i >= period) sum -= body(c[i - period]);
  }
  return out;
}

/** Last finite value of a series. */
export function lastValue(series: number[]): number {
  for (let i = series.length - 1; i >= 0; i--) if (Number.isFinite(series[i])) return series[i];
  return NaN;
}
