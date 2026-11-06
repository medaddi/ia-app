/**
 * A pair's team (backend /api/smc/team): S1–S4 with their status, and the setups that passed the 7 questions.
 * One pair at a time: a switch aborts the old request, an answer for another pair is dropped.
 */
import { useEffect, useState } from 'react';
import { apiFetch } from './api';
import type { SmcDrawing } from './chart/smcDrawing';

export interface Check { q: string; ok: boolean; detail: string }
export interface Step { step: string; ok: boolean; detail: string }
export interface TeamSetup {
  id: string; strategy: 'S1' | 'S2' | 'S3' | 'S4'; name: string; direction: 'BUY' | 'SELL'; time: number; entry: number; sl: number; tp: number;
  rr: number; validUntil: number; state: string; pass: boolean; checklist: Check[]; steps: Step[]; lots: { '1000': number; '10000': number };
  draw: { entry: number; sl: number; tp: number; zones: { label: string; top: number; bottom: number; from: number }[]; from: number };
  symbol?: string; sentAt?: string | null;
}
export interface TeamStrategy { id: string; name: string; status: 'SIGNAL' | 'BLOCKED' | 'WATCHING' | 'IDLE'; setup: TeamSetup | null;
  watch: { time: number; direction: string; steps: Step[] } | null }
export interface TeamChart extends SmcDrawing { trend: 'BULLISH' | 'BEARISH' | 'UNDEFINED'; premium: boolean }
/** One of the team's seven role agents (backend smc/agents.py): its finding, its sign-off, its detail lines. */
export interface TeamAgent { key: 'lead' | 'structure' | 'liquidity' | 'entry' | 'risk' | 'backtest' | 'devil'; role: string; status: 'ok' | 'warn' | 'wait'; finding: string; lines: string[] }
export interface Team { success: boolean; symbol: string; at: number; lastCandle: number | null; marketOpen?: boolean; source?: string; error?: string;
  strategies: TeamStrategy[]; signals: TeamSetup[]; chart?: TeamChart; agents?: TeamAgent[] }

export function useSmcTeam(symbol: string, ms = 30000): Team | null {
  const [st, setSt] = useState<Team | null>(null);
  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();
    setSt(null);
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      if (document.hidden) return;
      let ok = false;
      try {
        const r = await apiFetch(`/api/smc/team?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store', signal: ctrl.signal });
        const j = await r.json();
        if (alive && j.symbol === symbol) { setSt(j); ok = !!j.success; }
      } catch { /* retried below */ }
      if (!ok && alive) retry = setTimeout(load, 5000);  // a failed read (server waking up, feed down) is retried soon
    };
    load();
    const id = setInterval(load, ms);
    return () => { alive = false; ctrl.abort(); clearInterval(id); if (retry) clearTimeout(retry); };
  }, [symbol, ms]);
  return st && st.symbol === symbol ? st : null;
}
