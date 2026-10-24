/**
 * Backtester. Runs the SAME strategy code as the live app (server/strategies via replay.ts):
 * bar by bar, closed candles only, spread + slippage from each strategy's config, the same
 * order lifecycle (limit fill / expiry / TP1 cancel, partials, breakeven, trailing runner).
 */

import { loadStrategyCandles, normalizeSymbol, STRATEGY_DEFS } from "../strategies";
import { replay, outcome, EmittedSignal } from "../strategies/replay";
import { loadNewsCalendar } from "../strategies/shared/news";
import { activeWindow } from "../strategies/shared/common";
import { TF_SEC } from "../strategies/shared/types";
import { XAU_CONFIG } from "../strategies/xauusd/config";
import { EUR_CONFIG } from "../strategies/eurusd/config";
import { LifecycleResult } from "../strategies/shared/lifecycle";

export interface BacktestTrade {
  id: string;
  setup: string;
  direction: string;
  signalTime: string;
  session: string;
  weekday: string;
  score: number;
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  plannedRr: number;
  state: LifecycleResult["state"];
  outcome: LifecycleResult["outcome"];
  r: number | null;
  events: string;
}

export interface BacktestReport {
  symbol: string;
  strategy: string;
  period: { from: string; to: string; days: number };
  dataSource: string;
  costs: { spread: string; slippage: string };
  signals: number;
  filled: number;
  cancelledOrExpired: number;
  closed: number;
  open: number;
  wins: number;
  losses: number;
  breakevens: number;
  winRate: number | null;
  profitFactor: number | null;
  expectancyR: number | null;
  totalR: number;
  avgPlannedRr: number | null;
  maxDrawdownR: number;
  tradesPerMonth: number;
  bySession: Record<string, { trades: number; totalR: number; wins: number; losses: number }>;
  bySetup: Record<string, { trades: number; totalR: number; wins: number; losses: number }>;
  byWeekday: Record<string, { trades: number; totalR: number }>;
  equityCurve: { time: string; equityR: number }[];
  trades: BacktestTrade[];
  warnings: string[];
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export async function runBacktest(rawSymbol: string): Promise<BacktestReport> {
  const sym = normalizeSymbol(rawSymbol);
  const def = STRATEGY_DEFS[sym];
  const { candles, isReal, source } = await loadStrategyCandles(sym);
  if (!isReal) throw new Error(`Live feed unavailable for ${sym}: cannot backtest on synthetic candles`);
  const news = await loadNewsCalendar();
  const entry = candles[def.entryTf] || [];
  const tfSec = TF_SEC[def.entryTf];
  const warmup = Math.min(entry.length - 1, 700);
  const from = entry[warmup].time;
  const to = entry[entry.length - 1].time + tfSec;
  const base = { candles, livePrice: 0, spread: null, isRealData: true, dataSource: source, news };

  const state = replay(def, base, from, to);
  const indexOf = new Map(entry.map((c, i) => [c.time, i]));
  const windows = sym === "XAU/USD" ? XAU_CONFIG.sessions.killzones : EUR_CONFIG.sessions.windows;

  const trades: BacktestTrade[] = state.emitted.map((e: EmittedSignal) => {
    const lc = outcome(def, entry, indexOf, e.setup);
    const t = e.signalTime;
    return {
      id: e.id,
      setup: e.setup.setup,
      direction: e.setup.direction,
      signalTime: new Date(t * 1000).toISOString().slice(0, 16).replace("T", " "),
      session: activeWindow(t - 1, windows)?.name ?? "other",
      weekday: WEEKDAYS[new Date(t * 1000).getUTCDay()],
      score: e.score,
      entry: e.setup.entry,
      sl: e.setup.sl,
      tp1: e.setup.tp1,
      tp2: e.setup.tp2,
      plannedRr: Number(e.setup.rrTp2.toFixed(2)),
      state: lc.state,
      outcome: lc.outcome,
      r: lc.rMultiple,
      events: lc.events.map(ev => `${ev.type}@${new Date(ev.time * 1000).toISOString().slice(5, 16).replace("T", " ")}`).join(" "),
    };
  });

  const closed = trades.filter(t => t.state === "CLOSED");
  const wins = closed.filter(t => t.outcome === "WIN").length;
  const losses = closed.filter(t => t.outcome === "LOSS").length;
  const be = closed.filter(t => t.outcome === "BREAKEVEN").length;
  const pos = closed.reduce((s, t) => s + Math.max(0, t.r ?? 0), 0);
  const neg = closed.reduce((s, t) => s + Math.min(0, t.r ?? 0), 0);
  const totalR = Number((pos + neg).toFixed(2));

  let eq = 0, peak = 0, maxDd = 0;
  const curve: BacktestReport["equityCurve"] = [];
  for (const t of closed) {
    eq += t.r ?? 0;
    peak = Math.max(peak, eq);
    maxDd = Math.max(maxDd, peak - eq);
    curve.push({ time: t.signalTime, equityR: Number(eq.toFixed(2)) });
  }

  const group = <K extends string>(key: (t: BacktestTrade) => K) => {
    const out: Record<string, { trades: number; totalR: number; wins: number; losses: number }> = {};
    for (const t of closed) {
      const k = key(t);
      out[k] ||= { trades: 0, totalR: 0, wins: 0, losses: 0 };
      out[k].trades++;
      out[k].totalR = Number((out[k].totalR + (t.r ?? 0)).toFixed(2));
      if (t.outcome === "WIN") out[k].wins++;
      if (t.outcome === "LOSS") out[k].losses++;
    }
    return out;
  };
  const days = (to - from) / 86400;
  const filled = trades.filter(t => !["CANCELLED", "EXPIRED", "PENDING"].includes(t.state)).length;

  const warnings: string[] = [];
  if (closed.length < 30) warnings.push(`Only ${closed.length} closed trades: far too few to judge the strategy. Treat every number below as anecdotal.`);
  if (days < 180) warnings.push(`History is only ${days.toFixed(0)} days (Yahoo limits 5m/15m data to ~60 days). A 2–3 year test needs broker (MT5) history.`);
  warnings.push("News filter uses the current ForexFactory week only: past news events are not filtered in this backtest.");
  warnings.push("Spread is a fixed config value (feed has no live spread); real spreads widen around news and rollover.");
  if (closed.length >= 10 && totalR <= 0) warnings.push("Net result is negative or flat over this sample.");

  const cfg = sym === "XAU/USD" ? { spread: `$${XAU_CONFIG.filters.assumedSpread}`, slip: `$${XAU_CONFIG.filters.slippage}` } : { spread: `${EUR_CONFIG.filters.assumedSpreadPips} pips`, slip: `${EUR_CONFIG.filters.slippagePips} pips` };

  return {
    symbol: sym,
    strategy: sym === "XAU/USD" ? XAU_CONFIG.name : EUR_CONFIG.name,
    period: { from: new Date(from * 1000).toISOString().slice(0, 10), to: new Date(to * 1000).toISOString().slice(0, 10), days: Number(days.toFixed(1)) },
    dataSource: source,
    costs: { spread: cfg.spread, slippage: cfg.slip },
    signals: trades.length,
    filled,
    cancelledOrExpired: trades.filter(t => t.state === "CANCELLED" || t.state === "EXPIRED").length,
    closed: closed.length,
    open: trades.filter(t => ["OPEN", "TP1_HIT", "TP2_HIT", "PENDING"].includes(t.state)).length,
    wins, losses, breakevens: be,
    winRate: wins + losses > 0 ? Number(((wins / (wins + losses)) * 100).toFixed(1)) : null,
    profitFactor: neg < 0 ? Number((pos / -neg).toFixed(2)) : pos > 0 ? Infinity : null,
    expectancyR: closed.length ? Number((totalR / closed.length).toFixed(3)) : null,
    totalR,
    avgPlannedRr: trades.length ? Number((trades.reduce((s, t) => s + t.plannedRr, 0) / trades.length).toFixed(2)) : null,
    maxDrawdownR: Number(maxDd.toFixed(2)),
    tradesPerMonth: Number((trades.length / (days / 30.4)).toFixed(1)),
    bySession: group(t => t.session),
    bySetup: group(t => t.setup),
    byWeekday: Object.fromEntries(Object.entries(group(t => t.weekday)).map(([k, v]) => [k, { trades: v.trades, totalR: v.totalR }])),
    equityCurve: curve,
    trades,
    warnings,
  };
}

export function reportToMarkdown(r: BacktestReport): string {
  const tbl = (obj: Record<string, { trades: number; totalR: number; wins?: number; losses?: number }>) =>
    Object.keys(obj).length
      ? ["| Group | Trades | Wins | Losses | Total R |", "|---|---|---|---|---|", ...Object.entries(obj).map(([k, v]) => `| ${k} | ${v.trades} | ${v.wins ?? "—"} | ${v.losses ?? "—"} | ${v.totalR} |`)].join("\n")
      : "_none_";
  return `# Backtest · ${r.strategy}

**Period:** ${r.period.from} → ${r.period.to} (${r.period.days} days) · **Data:** ${r.dataSource} · **Costs:** spread ${r.costs.spread}, slippage ${r.costs.slippage}

${r.warnings.map(w => `> ⚠ ${w}`).join("\n")}

| Metric | Value |
|---|---|
| Signals | ${r.signals} (filled ${r.filled}, cancelled/expired ${r.cancelledOrExpired}, open ${r.open}) |
| Closed trades | ${r.closed} (wins ${r.wins}, losses ${r.losses}, breakeven ${r.breakevens}) |
| Win rate | ${r.winRate ?? "—"}% |
| Profit factor | ${r.profitFactor ?? "—"} |
| Expectancy | ${r.expectancyR ?? "—"} R / trade |
| Total | ${r.totalR} R |
| Average planned R:R (TP2) | ${r.avgPlannedRr ?? "—"} |
| Max drawdown | ${r.maxDrawdownR} R |
| Signals per month | ${r.tradesPerMonth} |

## By session
${tbl(r.bySession)}

## By setup
${tbl(r.bySetup)}

## By weekday
${tbl(r.byWeekday)}

## Trades
| Signal (UTC) | Setup | Side | Score | Entry | SL | TP2 | Planned R:R | Result | R | Events |
|---|---|---|---|---|---|---|---|---|---|---|
${r.trades.map(t => `| ${t.signalTime} | ${t.setup} | ${t.direction} | ${t.score} | ${t.entry} | ${t.sl} | ${t.tp2} | ${t.plannedRr} | ${t.state}${t.outcome ? ` ${t.outcome}` : ""} | ${t.r ?? "—"} | ${t.events} |`).join("\n")}
`;
}
