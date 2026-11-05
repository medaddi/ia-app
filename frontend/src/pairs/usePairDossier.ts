/**
 * One pair's dossier (backend GET /api/pairs/dossier): its team, its SMC report and drawing, its trades.
 * Fetched for one pair at a time: a switch aborts the old pair's request, and an answer stamped with another symbol is
 * dropped, so nothing of one pair ever shows on another's screen.
 */
import { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import type { SmcReportState } from '../smcReport';

export type Side = 'BUY' | 'SELL';
export interface TeamMember { key: 'trade' | 'structure' | 'liquidity' | 'zones' | 'strategy' | 'cot'; side: Side | null; conf: number; line: string; agrees: boolean | null }
export interface Team {
  agent: { id: string } | null;
  desk: { team: string; teamFr: string; teamAr: string; tags: string[] } | null;  // the pair's own specialist team
  session: { open: boolean; label: string | null; windows?: { from: number; to: number; label: string }[] };
  members: TeamMember[];
  risk: { approves: boolean; line: string };
  probabilities: { buy: number; sell: number; wait: number };
  decision: { status: 'IN_TRADE' | 'PENDING' | 'SETUP' | 'CONFLICT' | 'WAITING'; side: Side | null; entry?: number | null; entryZone?: [number, number] | null;
    sl?: number | null; tp?: number | null; rr?: number | null; trigger?: string | null; name?: string | null; why: string };
  grade: 'A' | 'B' | 'C' | null;
}
export interface PairTrade { id: string; symbol: string; direction: Side; entry: number; sl: number; tp?: number; tp2?: number; state: string; time?: number;
  signalTime?: number; setup?: string; outcome?: string | null; r?: number | null; entryType?: string }
export interface Dossier { symbol: string; price: number; team: Team; report: any; draw: SmcReportState['draw']; trades: { running: PairTrade[]; history: PairTrade[] } }

export function usePairDossier(symbol: string, ms = 15000): Dossier | null {
  const [st, setSt] = useState<Dossier | null>(null);
  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();
    setSt(null);  // a new pair: the old pair's dossier goes at once
    const load = async () => {
      if (document.hidden) return;
      try {
        const r = await apiFetch(`/api/pairs/dossier?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store', signal: ctrl.signal });
        const j = await r.json();
        if (alive && j.success && j.symbol === symbol) setSt(j);
      } catch { /* the next tick retries */ }
    };
    load();
    const id = setInterval(load, ms);
    return () => { alive = false; ctrl.abort(); clearInterval(id); };
  }, [symbol, ms]);
  return st && st.symbol === symbol ? st : null;
}

/** The dossier's SMC report in the chart's report shape (smcReport.withSmcReport). */
export const reportOf = (d: Dossier | null): SmcReportState | null => (d ? { symbol: d.symbol, report: d.report, draw: d.draw } : null);
