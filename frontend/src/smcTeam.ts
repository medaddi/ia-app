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
  rr: number; zone?: [number, number]; rrBest?: number; validUntil: number; tp1?: number | null; part?: number; market?: boolean; liveUntil?: number; state: string; pass: boolean; checklist: Check[]; steps: Step[]; lots: { '1000': number; '10000': number };
  draw: { entry: number; sl: number; tp: number; zones: { label: string; top: number; bottom: number; from: number }[]; from: number };
  symbol?: string; sentAt?: string | null;
  // set once sent, by the trade manager (backend smc/manager.py)
  status?: 'PENDING' | 'OPEN' | 'CLOSED' | 'EXPIRED' | 'MISSED'; outcome?: 'WIN' | 'LOSS' | 'BREAKEVEN' | null; resultR?: number | null; events?: string[];
}
export interface Measured { trades: number; wins: number; winRate: number | null; totalR: number }
export interface TeamStrategy { id: string; name: string; status: 'SIGNAL' | 'BLOCKED' | 'WATCHING' | 'IDLE' | 'OFF'; setup: TeamSetup | null;
  claimed?: string; measured?: Measured | null;
  watch: { time: number; direction: string; steps: Step[] } | null }
export interface TeamChart extends SmcDrawing { trend: 'BULLISH' | 'BEARISH' | 'UNDEFINED'; premium: boolean }
/** One of the team's seven role agents (backend smc/agents.py): its finding, its sign-off, its detail lines. */
export interface TeamAgent { key: 'lead' | 'structure' | 'liquidity' | 'entry' | 'risk' | 'backtest' | 'devil'; role: string; status: 'ok' | 'warn' | 'wait'; finding: string; lines: string[] }
/** The pair's strategies from the guide; each row of `strategies` carries what the guide claims and what the test measured (smc/PLAYBOOK.md). */
export interface TeamPlaybook { name: string; source?: string | null; from?: number | null; to?: number | null }
export interface Team { success: boolean; symbol: string; at: number; lastCandle: number | null; marketOpen?: boolean; source?: string; error?: string;
  strategies: TeamStrategy[]; signals: TeamSetup[]; chart?: TeamChart; agents?: TeamAgent[]; playbook?: TeamPlaybook }

// Each pair's last good team read, kept for the whole session: a switch shows THAT pair's last read at once (never another
// pair's: the key is the pair, and the read carries its own symbol), and the fresh read replaces it a moment later.
const teams = new Map<string, Team>();
const keep = (t: Team) => { if (t.success) teams.set(t.symbol, t); };

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
