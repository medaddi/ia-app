/**
 * The six SMC agents' report of a pair (backend analysis/smc_agents.py, GET /api/smc/report) and its drawing, kept per
 * pair: the chart of a pair only ever draws ITS report (ids SMC-, the report's own symbol checked).
 */
import { useEffect, useState } from 'react';
import { apiFetch } from './api';
import type { AgentChartOverlayState, OverlayMarker, OverlayPriceLine, OverlayZone } from './agentOverlay';

export interface SmcReportDraw { zones: OverlayZone[]; priceLines: OverlayPriceLine[]; markers: OverlayMarker[] }
export interface SmcReportState { symbol: string; report: any; draw: SmcReportDraw | null }

export function useSmcReport(symbol: string, ms = 30000): SmcReportState | null {
  const [st, setSt] = useState<SmcReportState | null>(null);
  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();
    setSt(null);  // a new pair: the old pair's report goes at once
    const load = async () => {
      if (document.hidden) return;
      try {
        const r = await apiFetch(`/api/smc/report?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store', signal: ctrl.signal });
        const j = await r.json();
        if (alive && j.success && j.symbol === symbol) setSt({ symbol, report: j.report, draw: j.draw });
      } catch { /* the next tick retries */ }
    };
    load();
    const id = setInterval(load, ms);
    return () => { alive = false; ctrl.abort(); clearInterval(id); };
  }, [symbol, ms]);
  return st && st.symbol === symbol ? st : null;
}

/** The agent's overlay with its SMC view replaced by the six agents' report (only the report of this same pair). */
export function withSmcReport(overlay: AgentChartOverlayState | null, rep: SmcReportState | null, symbol: string): AgentChartOverlayState | null {
  if (!overlay || !rep?.draw || rep.symbol !== symbol) return overlay;
  const own = (id: string) => !id.startsWith('SMC-');
  return {
    ...overlay,
    zones: [...overlay.zones.filter(z => own(z.id)), ...rep.draw.zones],
    priceLines: [...overlay.priceLines.filter(l => own(l.id)), ...rep.draw.priceLines],
    // the swing labels (HH / HL / LH / LL) stay the agent's; the report adds the strategy's setup at its own candle
    markers: [...overlay.markers.filter(m => own(m.id)), ...(rep.draw.markers ?? [])],
  };
}
