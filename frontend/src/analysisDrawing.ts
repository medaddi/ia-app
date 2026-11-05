/**
 * What the Analyse button draws on a pair's chart: the setup that applies now (backend analysis/drawing.py), kept per
 * pair until it is cleared or replaced by a new analysis, and merged into that pair's agent overlay on every chart of it.
 */
import { useEffect, useState } from 'react';
import type { AgentChartOverlayState, OverlayMarker, OverlayPriceLine, OverlayZone, TradeExecutionBox } from './agentOverlay';

export interface AnalysisDrawing {
  label: string;
  family: 'plan' | 'smc';
  id: string;
  zones: OverlayZone[];
  priceLines: OverlayPriceLine[];
  markers: OverlayMarker[];
  tradeExecutionBox: TradeExecutionBox | null;
  at?: number;
}

const store = new Map<string, AnalysisDrawing>();
const subs = new Map<string, Set<() => void>>();  // per pair: a drawing on one pair re-renders only that pair's screens

export function setAnalysisDrawing(symbol: string, d: AnalysisDrawing | null) {
  if (d) store.set(symbol, { ...d, at: Date.now() });
  else store.delete(symbol);
  subs.get(symbol)?.forEach(f => f());
}

export function useAnalysisDrawing(symbol: string): AnalysisDrawing | null {
  const [, tick] = useState(0);
  useEffect(() => {
    const f = () => tick(n => n + 1);
    if (!subs.has(symbol)) subs.set(symbol, new Set());
    subs.get(symbol)!.add(f);
    return () => { const s = subs.get(symbol); s?.delete(f); if (s && s.size === 0) subs.delete(symbol); };
  }, [symbol]);
  return store.get(symbol) ?? null;
}

/** The agent's overlay with the analysis drawing on top (its trade box replaces the agent's while it is shown). */
export function withAnalysis(overlay: AgentChartOverlayState | null, d: AnalysisDrawing | null): AgentChartOverlayState | null {
  if (!d) return overlay;
  if (!overlay) return null;
  return {
    ...overlay,
    zones: [...overlay.zones, ...d.zones],
    priceLines: [...overlay.priceLines, ...d.priceLines],
    markers: [...overlay.markers, ...d.markers],
    tradeExecutionBox: d.tradeExecutionBox ?? overlay.tradeExecutionBox,
  };
}
