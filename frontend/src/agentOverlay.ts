/**
 * The isolated agent-to-chart rendering contract. Each pair has its own autonomous agent (backend app/agents/) that runs
 * its own state machine and emits this state for ITS chart only; the chart renders exactly what its agent emits.
 */
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from './api';

export type TradableSymbol = 'EURUSD' | 'GBPUSD' | 'EURCHF' | 'AUDCAD' | 'AUDCHF' | 'XAUUSD';
export type FsmState = 'IDLE' | 'ARMED' | 'LIQUIDITY_SWEPT' | 'MSS_CONFIRMED' | 'PENDING_ORDER' | 'IN_TRADE' | 'COOLDOWN';
export type ZoneCategory = 'ASIAN_BOX' | 'LONDON_BOX' | 'FVG_BULL' | 'FVG_BEAR' | 'OB_BULL' | 'OB_BEAR' | 'OTE_GOLD_ZONE' | 'SUPPLY_BAND' | 'DEMAND_BAND';
export type LineCategory = 'PDH' | 'PDL' | 'SESSION_HIGH' | 'SESSION_LOW' | 'MSS_BREAK' | 'EQUILIBRIUM' | 'DIVERGENCE_LINE'
  | 'BSL' | 'SSL' | 'BOS' | 'CHOCH';  // the SMC view (backend agents/smc.py): context, never a signal

export interface OverlayZone {
  id: string;
  category: ZoneCategory;
  startTime: number;
  endTime: number;
  topPrice: number;
  bottomPrice: number;
  midPrice?: number;      // a dashed 50 % equilibrium / CE line inside the box
  fillColor: string;      // RGBA
  borderColor: string;    // hex / RGBA
  label: string;          // inside the top-right corner of the box
  isMitigated: boolean;
}

export interface OverlayPriceLine {
  id: string;
  category: LineCategory;
  startTime: number;
  endTime: number;
  startPrice: number;
  endPrice: number;       // = startPrice for a horizontal line; sloped for the RSI divergence
  lineStyle: 'SOLID' | 'DASHED' | 'DOTTED';
  color: string;
  label: string;
}

export interface OverlayMarker {
  id: string;
  time: number;
  price: number;
  position: 'aboveBar' | 'belowBar';
  shape: 'arrowDown' | 'arrowUp' | 'circle';
  color: string;
  text: string;
}

export interface TradeExecutionBox {
  direction: 'LONG' | 'SHORT';
  orderType: 'LIMIT' | 'MARKET';
  status: 'PENDING' | 'OPEN' | 'TP1_HIT_BE';
  entryTime: number;
  entryPrice: number;
  stopLoss: number;
  tp1Price: number;
  tp2Price: number;
  rrRatio: number;
  floatingPips: number;
}

export interface AgentChartOverlayState {
  symbol: TradableSymbol;
  agentId: string;
  fsmState: FsmState;
  statusBannerText: string;  // top-left of this pair's chart
  metrics: { spreadPips: number; atrPips: number; sessionName: string; confluenceTag: string };
  zones: OverlayZone[];
  priceLines: OverlayPriceLine[];
  markers: OverlayMarker[];
  tradeExecutionBox?: TradeExecutionBox | null;
  updatedAt?: number;
}

export const toTradable = (display: string): TradableSymbol => display.replace('/', '').toUpperCase() as TradableSymbol;

export const FSM_TONE: Record<FsmState, string> = {
  IDLE: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
  ARMED: 'bg-sky-500/15 text-sky-200 ring-sky-500/30',
  LIQUIDITY_SWEPT: 'bg-amber-500/15 text-amber-200 ring-amber-500/30',
  MSS_CONFIRMED: 'bg-violet-500/15 text-violet-200 ring-violet-500/30',
  PENDING_ORDER: 'bg-gold-500/15 text-gold-200 ring-gold-500/30',
  IN_TRADE: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
  COOLDOWN: 'bg-rose-500/10 text-rose-300 ring-rose-500/25',
};

/**
 * Subscribes a chart to its own agent's overlay: re-read every `ms` while the tab is visible (the agent re-emits at
 * each candle close and each price tick). Answers for another pair (after a switch) are dropped.
 */
export function useAgentOverlay(symbol: string, ms = 2000, asOf = 0) {
  const [overlay, setOverlay] = useState<AgentChartOverlayState | null>(null);
  const [meta, setMeta] = useState<{ price: number; decimals: number; entryTf: string; ok: boolean; reason: string } | null>(null);
  const cur = useRef(symbol);
  cur.current = symbol;
  useEffect(() => {
    let alive = true;
    setOverlay(null);
    const load = async () => {
      if (document.hidden) return;
      try {
        const res = await apiFetch(`/api/agents/overlay?symbol=${encodeURIComponent(symbol)}${asOf > 0 ? `&asOf=${asOf}` : ''}`, { cache: 'no-store' });
        const j = await res.json();
        if (!alive || cur.current !== symbol || !j.success) return;
        setOverlay(j.overlay ?? null);
        setMeta({ price: j.price, decimals: j.decimals, entryTf: j.entryTf, ok: !!j.dataQuality?.ok, reason: j.dataQuality?.reason ?? '' });
      } catch { /* the next tick retries */ }
    };
    load();
    const id = asOf > 0 ? null : setInterval(load, ms);
    return () => { alive = false; if (id) clearInterval(id); };
  }, [symbol, ms, asOf]);
  return { overlay, meta };
}
