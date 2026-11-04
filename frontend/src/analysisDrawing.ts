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
const subs = new Set<() => void>();
const emit = () => subs.forEach(f => f());

export function setAnalysisDrawing(symbol: string, d: AnalysisDrawing | null) {
  if (d) store.set(symbol, { ...d, at: Date.now() });
  else store.delete(symbol);
  emit();
}

export function useAnalysisDrawing(symbol: string): AnalysisDrawing | null {
  const [, tick] = useState(0);
  useEffect(() => {
    const f = () => tick(n => n + 1);
    subs.add(f);
    return () => { subs.delete(f); };
  }, []);
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
