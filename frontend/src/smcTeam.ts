/**
 * A pair's team (backend /api/smc/team): the pair's strategies from the guide with their status, and the setups that passed the guide's checklist.
 * One pair at a time: a switch aborts the old request, an answer for another pair is dropped.
 */
import { useEffect, useState } from 'react';
import { apiFetch } from './api';
import type { SmcDrawing } from './chart/smcDrawing';

export interface Check { q: string; ok: boolean; detail: string }
export interface Step { step: string; ok: boolean; detail: string }
export interface TeamSetup {
  id: string; strategy: string; name: string; direction: 'BUY' | 'SELL'; time: number; entry: number; sl: number; tp: number;
  rr: number; zone?: [number, number]; rrBest?: number; riskPct?: number; validUntil: number; tp1?: number | null; part?: number; market?: boolean; liveUntil?: number; state: string; pass: boolean; checklist: Check[]; steps: Step[]; lots: { '1000': number; '10000': number };
  draw: { entry: number; sl: number; tp: number; zones: { label: string; top: number; bottom: number; from: number }[]; from: number };
  symbol?: string; sentAt?: string | null;
  // FXAlexG: the setup's grade, its S_AlexG score and its live confluences
  grade?: string; gpa?: number; consensus?: number; setupType?: string; checklistGpa?: Confluence[];
  /** the plan's details: the confirmation timeframe, trend-following or counter-trend, what invalidates it, distances in pips */
  etf?: string; family?: 'trend-following' | 'counter-trend' | null; invalidation?: string | null; slPips?: number; tpPips?: number; bePips?: number;
  // set once sent, by the trade manager (backend smc/manager.py)
  status?: 'PENDING' | 'OPEN' | 'CLOSED' | 'EXPIRED' | 'MISSED'; outcome?: 'WIN' | 'LOSS' | 'BREAKEVEN' | null; resultR?: number | null; events?: string[];
}
/** One of the 18 FXAlexG confluences: its weight in % and whether it is live at the AOI. */
export interface Confluence { key: string; label: string; pts: number; ok: boolean }
/** A radar read: the SoS is in at an AOI, only the engulfing candle is missing. Shown as the "Watching" status on the pair's
 * own card only: it is never a notification (no toast, no bell item, no push, no Telegram). */
export interface RadarAlert { id: string; symbol?: string; direction: 'BUY' | 'SELL'; tf: string; touches: number; low: number; high: number; psych?: number | null; etf: string; gpa: number; grade: string; time: number; setup?: string | null; at?: number }
export interface Measured { trades: number; wins: number; winRate: number | null; totalR: number }
export interface TeamStrategy { id: string; name: string; status: 'SIGNAL' | 'BLOCKED' | 'WATCHING' | 'IDLE' | 'OFF'; setup: TeamSetup | null;
  claimed?: string; measured?: Measured | null;
  watch: { time: number; direction: string; steps: Step[] } | null }
export interface TeamChart extends SmcDrawing { trend: 'BULLISH' | 'BEARISH' | 'UNDEFINED'; premium: boolean }
/** One of the 5 FXAlexG agents (backend smc/alexg.py squad): its badge, status, score 0-100, weight and details. */
export interface TeamAgent { key: 'trend' | 'aoi' | 'confluence' | 'trigger' | 'risk'; id?: string; name?: string; badge?: string; details?: string[]; role: string; status: 'ok' | 'warn' | 'wait' | 'veto'; finding: string; score?: number; weight?: number; lines: string[] }
/** The pair's strategies from the guide; each row of `strategies` carries what the guide claims and what the test measured (smc/PLAYBOOK.md). */
export interface TeamPlaybook { name: string; source?: string | null; from?: number | null; to?: number | null }
export interface Team { success: boolean; symbol: string; at: number; lastCandle: number | null; marketOpen?: boolean; source?: string; error?: string;
  strategies: TeamStrategy[]; signals: TeamSetup[]; chart?: TeamChart; agents?: TeamAgent[]; playbook?: TeamPlaybook;
  /** the pair profile's H1 badge (e.g. "H1 range · Z -1.8σ · discount 18 %") */ badge?: string;
  /** FXAlexG: the live read's GPA (0-100), grade (A+ / A / B / C+ / F), the 5 agents' consensus, the decision, the 9-point checklist */
  grade?: string; gpa?: number; consensus?: number; decision?: 'EXECUTE' | 'WAIT_FOR_TRIGGER' | 'WATCH_ONLY' | 'VETOED'; direction?: 'BUY' | 'SELL';
  setupType?: string | null; checklist?: Confluence[]; radar?: RadarAlert | null;
  /** what the validation can say about this pair's strategy (smc/tools/validate.py): never "profitable" from a few trades */
  evidence?: Evidence; family?: 'trend-following' | 'counter-trend' | null; params?: { minRr: number; counterMinGpa: number; version: string } }
export interface Evidence { state: 'insufficient data' | 'experimental' | 'validated for research'; oosTrades: number; needed: number; trades: number;
  expectancyR?: number | null; ci95?: [number, number] | null; source?: string | null; date?: string }

const decOf = (sym = '') => (sym.startsWith('XAU') ? 2 : sym.endsWith('JPY') ? 3 : 5);
/** A signal's first line, the same as Telegram's: pair, side, timeframe, UTC time. */
export const signalHead = (s: TeamSetup) => `${s.symbol ?? ''} ${s.direction} · ${s.etf ?? 'H1'} · ${new Date(s.time * 1000).toISOString().slice(11, 16)} UTC`;
/** Its levels, the same as Telegram's: entry, stop, target, R:R. */
export const signalLevels = (s: TeamSetup) => {
  const d = decOf(s.symbol);
  return `Entry ${s.entry.toFixed(d)} · SL ${s.sl.toFixed(d)} · TP ${s.tp.toFixed(d)} · 1:${s.rr.toFixed(1)}`;
};

// Each pair's last good team read, kept for the whole session: a switch shows THAT pair's last read at once (never another
// pair's: the key is the pair, and the read carries its own symbol), and the fresh read replaces it a moment later.
const teams = new Map<string, Team>();
const keep = (t: Team) => { if (t.success) teams.set(t.symbol, t); };
/** Every pair's last read in memory (the Sunday Swings watchlist ranks them). */
export const cachedTeams = (): Team[] => [...teams.values()];

/** Reads the teams of `symbols` that are not in memory yet, one after the other (the chart page warms the other pairs). */
export async function prefetchTeams(symbols: readonly string[], signal?: AbortSignal): Promise<void> {
  for (const s of symbols) {
    if (signal?.aborted) return;
    if (teams.has(s)) continue;
    try {
      const r = await apiFetch(`/api/smc/team?symbol=${encodeURIComponent(s)}`, { cache: 'no-store', signal });
      const j = await r.json();
      if (j.symbol === s) keep(j);
    } catch { /* the pair loads when it is opened */ }
  }
}

export function useSmcTeam(symbol: string, ms = 30000): Team | null {
  const [st, setSt] = useState<Team | null>(() => teams.get(symbol) ?? null);
  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();
    setSt(teams.get(symbol) ?? null);  // this pair's last read at once, or nothing: never the previous pair's
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      if (document.hidden) return;
      let ok = false;
      try {
        const r = await apiFetch(`/api/smc/team?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store', signal: ctrl.signal });
        const j = await r.json();
        if (alive && j.symbol === symbol) { keep(j); setSt(j.success ? j : teams.get(symbol) ?? j); ok = !!j.success; }
      } catch { /* retried below */ }
      if (!ok && alive) retry = setTimeout(load, 5000);  // a failed read (server waking up, feed down) is retried soon
    };
    load();
    const id = setInterval(load, ms);
    return () => { alive = false; ctrl.abort(); clearInterval(id); if (retry) clearTimeout(retry); };
  }, [symbol, ms]);
  return st && st.symbol === symbol ? st : null;
}
