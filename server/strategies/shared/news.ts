/**
 * Economic calendar filter.
 * Source: ForexFactory weekly calendar JSON (faireconomy mirror) merged with an optional local
 * file data/news_calendar.json ([{ "time": "2026-10-28T12:30:00Z", "currency": "USD", "title": "CPI m/m", "impact": "High" }]).
 */

import fs from "fs";
import path from "path";

export interface NewsEvent {
  time: number; // unix seconds UTC
  currency: string;
  title: string;
  impact: "High" | "Medium" | "Low" | "Holiday";
}

export interface NewsRule {
  currencies: string[];
  keywords: string[]; // empty = every high-impact event of those currencies
  minutesBefore: number;
  minutesAfter: number;
}

export function newsBlock(tsSec: number, events: NewsEvent[], rule: NewsRule): { blocked: boolean; event: NewsEvent | null; next: NewsEvent | null } {
  const relevant = events.filter(e =>
    e.impact === "High" &&
    rule.currencies.includes(e.currency) &&
    (rule.keywords.length === 0 || rule.keywords.some(k => e.title.toLowerCase().includes(k.toLowerCase())))
  );
  const hit = relevant.find(e => tsSec >= e.time - rule.minutesBefore * 60 && tsSec <= e.time + rule.minutesAfter * 60) || null;
  const next = relevant.filter(e => e.time > tsSec).sort((a, b) => a.time - b.time)[0] || null;
  return { blocked: hit !== null, event: hit, next };
}

let cache: { events: NewsEvent[]; expires: number; source: string } | null = null;

export async function loadNewsCalendar(): Promise<{ events: NewsEvent[]; source: string }> {
  if (cache && cache.expires > Date.now()) return cache;
  const events: NewsEvent[] = [];
  const sources: string[] = [];
  try {
    const res = await fetch("https://nfs.faireconomy.media/ff_calendar_thisweek.json", { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      const data = await res.json();
      for (const e of Array.isArray(data) ? data : []) {
        const t = Date.parse(e.date);
        if (!Number.isFinite(t)) continue;
        events.push({ time: Math.floor(t / 1000), currency: String(e.country || ""), title: String(e.title || ""), impact: e.impact });
      }
      sources.push("ForexFactory calendar");
    }
  } catch {
    // calendar unavailable: fall back to the local file
  }
  try {
    const file = path.resolve(process.cwd(), "data/news_calendar.json");
    if (fs.existsSync(file)) {
      for (const e of JSON.parse(fs.readFileSync(file, "utf8"))) {
        const t = Date.parse(e.time);
        if (Number.isFinite(t)) events.push({ time: Math.floor(t / 1000), currency: e.currency, title: e.title, impact: e.impact || "High" });
      }
      sources.push("data/news_calendar.json");
    }
  } catch {
    // malformed local file is ignored
  }
  cache = { events, expires: Date.now() + (sources.length ? 60 : 5) * 60 * 1000, source: sources.join(" + ") || "none" };
  return cache;
}
