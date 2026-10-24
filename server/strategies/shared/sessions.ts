/**
 * Timezone-aware session helpers. Windows are defined in local time (Europe/London,
 * America/New_York) and converted to UTC with the real DST offset of that date.
 */

import { Candle } from "./types";

export const LONDON = "Europe/London";
export const NEW_YORK = "America/New_York";

export interface ZonedParts { year: number; month: number; day: number; hour: number; minute: number; weekday: number }

const fmtCache = new Map<string, Intl.DateTimeFormat>();
function formatter(tz: string) {
  let f = fmtCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", {
      timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", weekday: "short", hourCycle: "h23",
    });
    fmtCache.set(tz, f);
  }
  return f;
}
const WEEKDAYS: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

export function zonedParts(tsSec: number, tz: string): ZonedParts {
  const p: Record<string, string> = {};
  for (const part of formatter(tz).formatToParts(new Date(tsSec * 1000))) p[part.type] = part.value;
  return { year: +p.year, month: +p.month, day: +p.day, hour: +p.hour % 24, minute: +p.minute, weekday: WEEKDAYS[p.weekday] };
}

/** Offset of `tz` from UTC at that instant, in seconds (London summer = +3600). */
export function tzOffsetSec(tsSec: number, tz: string): number {
  const z = zonedParts(tsSec, tz);
  return Date.UTC(z.year, z.month - 1, z.day, z.hour, z.minute) / 1000 - Math.floor(tsSec / 60) * 60;
}

/** Converts a local wall-clock time in `tz` to a UTC unix timestamp. */
export function zonedToUtc(year: number, month: number, day: number, hour: number, minute: number, tz: string): number {
  const guess = Date.UTC(year, month - 1, day, hour, minute) / 1000;
  const first = guess - tzOffsetSec(guess, tz);
  return guess - tzOffsetSec(first, tz);
}

const hm = (s: string) => { const [h, m] = s.split(":").map(Number); return { h, m }; };

export function minutesOfDay(tsSec: number, tz: string): number {
  const z = zonedParts(tsSec, tz);
  return z.hour * 60 + z.minute;
}

/** True if tsSec falls in [start, end) local time of `tz`. */
export function inLocalWindow(tsSec: number, tz: string, start: string, end: string): boolean {
  const m = minutesOfDay(tsSec, tz);
  const a = hm(start), b = hm(end);
  return m >= a.h * 60 + a.m && m < b.h * 60 + b.m;
}

export function localDateKey(tsSec: number, tz: string): string {
  const z = zonedParts(tsSec, tz);
  return `${z.year}-${String(z.month).padStart(2, "0")}-${String(z.day).padStart(2, "0")}`;
}

/** UTC bounds of a local window on a given local date. */
export function windowBounds(dateKey: string, tz: string, start: string, end: string): { startSec: number; endSec: number } {
  const [y, mo, d] = dateKey.split("-").map(Number);
  const a = hm(start), b = hm(end);
  return { startSec: zonedToUtc(y, mo, d, a.h, a.m, tz), endSec: zonedToUtc(y, mo, d, b.h, b.m, tz) };
}

/** Forex trading day: rolls over at 17:00 New York (so the key is the NY date 7h later). */
export function tradingDayKey(tsSec: number): string {
  return localDateKey(tsSec + 7 * 3600, NEW_YORK);
}

/** Trading week key: the Monday of the trading day's week. */
export function tradingWeekKey(tsSec: number): string {
  const [y, m, d] = tradingDayKey(tsSec).split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  const dow = (date.getUTCDay() + 6) % 7; // Monday = 0
  date.setUTCDate(date.getUTCDate() - dow);
  return date.toISOString().slice(0, 10);
}

export interface SessionRange {
  name: string;
  dateKey: string;
  startSec: number;
  endSec: number;
  high: number;
  low: number;
  highTime: number;
  lowTime: number;
  complete: boolean;
}

/** High/low of candles inside a session window, using only candles closed by nowSec. */
export function sessionRange(c: Candle[], tfSec: number, name: string, dateKey: string, tz: string, start: string, end: string, nowSec: number): SessionRange | null {
  const { startSec, endSec } = windowBounds(dateKey, tz, start, end);
  let high = -Infinity, low = Infinity, highTime = 0, lowTime = 0;
  for (const x of c) {
    if (x.time < startSec || x.time >= endSec || x.time + tfSec > nowSec) continue;
    if (x.high > high) { high = x.high; highTime = x.time; }
    if (x.low < low) { low = x.low; lowTime = x.time; }
  }
  if (!Number.isFinite(high)) return null;
  return { name, dateKey, startSec, endSec, high, low, highTime, lowTime, complete: nowSec >= endSec };
}
