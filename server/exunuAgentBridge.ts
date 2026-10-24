/**
 * EXUNU agent bridge.
 * Presents the strategy result of the app's two strategies (server/strategies) as the 4-agent
 * EXUNU view (Structure, Liquidity, Risk, CTO). The agents run no logic of their own: each one
 * reports its part of the same deterministic result the chart and Telegram use.
 */

import { AISignal, MarketAsset } from "../src/types";
import { getStrategyResult, getStrategyResultAsOf, normalizeSymbol } from "./strategies";
import { StrategyResult } from "./strategies/shared/result";
import { buildExplanation } from "./agent/explain";

export interface ExunuSMCResult {
  terminal: string;
  symbol: "XAU/USD" | "EUR/USD";
  current_price: number;
  status: "CONFIRMED_ENTRY" | "WAITING_CONFIRMATION" | "NO_SETUP";
  action: "BUY" | "SELL" | "WAIT";
  confidence: number;
  setup_json: {
    status: string;
    state: string;
    action: "BUY" | "SELL" | "WAIT";
    symbol: string;
    confidence: number;
    setup_grade: string;
    strategy: string;
    current_price: number;
    entry_price: number;
    stop_loss: number;
    target1: number;
    target2: number;
    target3: number;
    risk_reward: string;
    sl_pips: number;
    risk_management: { lot_sizing: Record<string, number | string>; is_rr_valid: boolean };
    timestamp: number;
  };
  agents: {
    structure_agent: { agent: string; summary: string; [k: string]: unknown };
    liquidity_agent: { agent: string; summary: string; [k: string]: unknown };
    risk_agent: { agent: string; summary: string; [k: string]: unknown };
    cto_agent: { agent: string; summary: string; [k: string]: unknown };
  };
  inter_agent_dialogue: Array<{ sender: string; recipient: string; topic: string; summary: string }>;
  summary_ar: string;
  explanation: string;
  timestamp: number;
  strategy: StrategyResult;
}

const grade = (score: number) => (score >= 90 ? "A+" : score >= 75 ? "A" : score >= 60 ? "B" : "C");

/** Maps a strategy status to the legacy EXUNU status. Only a SIGNAL is a confirmed entry. */
function legacyStatus(r: StrategyResult): ExunuSMCResult["status"] {
  if (r.status === "SIGNAL") return "CONFIRMED_ENTRY";
  if (r.status === "WATCH") return "WAITING_CONFIRMATION";
  return "NO_SETUP";
}

export function buildExunuResult(r: StrategyResult): ExunuSMCResult {
  const d = r.spec.decimals;
  const f = (v: number) => v.toFixed(d);
  const s = r.setup;
  const a = (s?.anchors || {}) as any;
  const facts = r.facts as any;
  const status = legacyStatus(r);
  const action: ExunuSMCResult["action"] = s && r.status !== "NO_TRADE" && r.status !== "IGNORE" ? s.direction : "WAIT";

  const structureSummary = `Bias ${r.bias.direction}: ${r.bias.detail}`;
  const liquiditySummary = a.sweep
    ? `${a.sweep.level.label} ${f(a.sweep.level.price)} swept (wick ${f(a.sweep.extreme)})${a.poi ? ` · POI ${a.poi.kind} ${f(a.poi.bottom)}–${f(a.poi.top)}` : ""}`
    : a.leg ? `Pullback into Fib 50–61.8% ${f(Math.min(a.leg.fib50, a.leg.fib618))}–${f(Math.max(a.leg.fib50, a.leg.fib618))}${a.ob ? ` + H1 OB ${f(a.ob.bottom)}–${f(a.ob.top)}` : ""}`
    : facts?.asianRange ? `Asian range ${f(facts.asianRange.low)}–${f(facts.asianRange.high)}` : "No liquidity event in the setup window";
  const riskSummary = s
    ? `${s.entryType} ${s.direction} ${f(s.entry)} · SL ${f(s.sl)} (${s.slPips}p) · TP1 ${f(s.tp1)} · TP2 ${f(s.tp2)} 1:${s.rrTp2.toFixed(1)} · ${s.lots["1000$"] ?? 0} lot per $1k at 1%`
    : "No levels: no setup";
  const ctoSummary = `${r.status} · score ${r.score}/100 · ${r.headline}`;

  return {
    terminal: "EXUNU Terminal",
    symbol: r.displaySymbol,
    current_price: r.price,
    status,
    action,
    confidence: r.score,
    setup_json: {
      status,
      state: s?.lifecycle.state ?? "NO_SETUP",
      action,
      symbol: r.displaySymbol,
      confidence: r.score,
      setup_grade: s ? grade(r.score) : "—",
      strategy: r.strategyName,
      current_price: r.price,
      entry_price: s?.entry ?? 0,
      stop_loss: s?.sl ?? 0,
      target1: s?.tp1 ?? 0,
      target2: s?.tp2 ?? 0,
      target3: s?.tp3 ?? 0,
      risk_reward: s ? `1:${s.rrTp2.toFixed(1)}` : "—",
      sl_pips: s?.slPips ?? 0,
      risk_management: { lot_sizing: { ...(s?.lots || {}), standard_risk_pct: "1.0%" }, is_rr_valid: !!s && s.rrTp2 >= 2 },
      timestamp: Date.now(),
    },
    agents: {
      structure_agent: { agent: "Structure Agent", summary: structureSummary, bias: r.bias },
      liquidity_agent: { agent: "Liquidity Agent", summary: liquiditySummary },
      risk_agent: { agent: "Risk Agent", summary: riskSummary, lots: s?.lots ?? {} },
      cto_agent: { agent: "Chief Trading Officer (CTO)", summary: ctoSummary, status: r.status, score: r.score, checklist: r.checklist, rejection: r.rejection, can_notify: r.canNotify },
    },
    inter_agent_dialogue: [
      { sender: "Structure Agent", recipient: "Liquidity Agent", topic: "BIAS", summary: structureSummary },
      { sender: "Liquidity Agent", recipient: "Risk Agent", topic: "LIQUIDITY", summary: liquiditySummary },
      { sender: "Risk Agent", recipient: "CTO Agent", topic: "RISK", summary: riskSummary },
      { sender: "CTO Agent", recipient: "Terminal", topic: "DECISION", summary: ctoSummary },
    ],
    summary_ar: r.headlineAr,
    explanation: buildExplanation(r),
    timestamp: Date.now(),
    strategy: r,
  };
}

export async function runExunuSMCEngine(symbol: string = "XAU/USD", currentPrice?: number, _candles?: any[]): Promise<ExunuSMCResult> {
  const { result } = await getStrategyResult(symbol, { livePrice: currentPrice });
  return buildExunuResult(result);
}

export async function runExunuSMCEngineAsOf(symbol: string, asOfSec: number): Promise<ExunuSMCResult> {
  const { result } = await getStrategyResultAsOf(symbol, asOfSec);
  return buildExunuResult(result);
}

export function convertExunuToAISignal(res: ExunuSMCResult, asset: MarketAsset): AISignal {
  const r = res.strategy;
  const s = r.setup;
  const d = r.spec.decimals;
  const confirmed = r.status === "SIGNAL";
  const sym = normalizeSymbol(asset?.symbol || r.displaySymbol);
  return {
    id: s ? `sig-${s.id}` : `sig-${r.symbol.toLowerCase()}`,
    symbol: sym,
    assetName: sym === "EUR/USD" ? "Euro / US Dollar" : "Spot Gold (XAU/USD)",
    signalType: res.action,
    signalLabel: confirmed ? `${s!.direction} SIGNAL` : r.status === "WATCH" ? `${s?.direction} WATCH` : "NO TRADE",
    entryZone: s ? s.entry.toFixed(d) : "",
    entryPrice: s?.entry ?? 0,
    stopLoss: s?.sl ?? 0,
    target1: s?.tp1 ?? 0,
    target2: s?.tp2 ?? 0,
    target3: s?.tp3 ?? 0,
    confidence: r.score,
    reasons: r.checklist.map(c => `${c.passed ? "✓" : "✕"} ${c.rule}: ${c.detail}`),
    riskReward: s ? `1:${s.rrTp2.toFixed(1)}` : "—",
    timeframe: r.timeframes.entry,
    createdAt: s ? new Date(s.signalTime * 1000).toISOString() : "—",
    status: "ACTIVE",
    overallVerdict: confirmed ? (s!.direction === "BUY" ? "STRONG_BUY_SETUP" : "STRONG_SELL_SETUP") : "WAIT",
    currentLivePrice: asset?.price || r.price,
    isActionableNow: confirmed,
    decisionStatus: confirmed ? "ALLOWED" : "NO_TRADE",
    confirmationCheckPassed: confirmed,
    confirmationCloseTime: s?.signalTime,
    isMarketOpen: r.market.isOpen,
    tradeScore: r.score,
    tradeScoreGrade: r.score >= 90 ? "EXCELLENT" : r.score >= 75 ? "VERY_STRONG" : r.score >= 60 ? "GOOD" : "WEAK",
    strategyUsed: r.strategyName,
    strategyType: "ICT_SMC",
    setupGrade: (s ? grade(r.score) : "B") as any,
    pipSize: r.spec.pipSize,
    pipsRisk: s?.slPips,
    slPointsOrPips: s?.slPips,
    dataSourceName: r.dataQuality.source,
    distanceToEntryText: r.headlineAr,
    invalidationCondition: s?.invalidation,
    invalidationConditionAr: s ? `الإلغاء: ${s.invalidation}` : undefined,
    entryType: s?.entryType,
    expiresAt: r.signal?.expires_at,
    signalJson: r.signal,
    explanation: res.explanation,
    marketSuitability: {
      isSuitable: confirmed,
      trend: r.bias.direction === "BULLISH" ? "Bullish" : r.bias.direction === "BEARISH" ? "Bearish" : "Sideways",
      reasonAr: r.headlineAr,
      reasonEn: r.headline,
      emaAlignment: r.bias.detail,
      structureVerdict: r.bias.detail,
    },
    validationChecklist: {
      dataValid: r.dataQuality.ok,
      structureValid: r.checklist.find(c => c.key === "mss" || c.key === "trigger")?.passed ?? false,
      htfAligned: r.checklist.find(c => c.key === "bias")?.passed ?? false,
      entryConfirmed: confirmed,
      slLogical: r.checklist.find(c => c.key === "sl")?.passed ?? false,
      tpLogical: r.checklist.find(c => c.key === "rr")?.passed ?? false,
      acceptableRR: r.checklist.find(c => c.key === "rr")?.passed ?? false,
      spreadAcceptable: r.checklist.find(c => c.key === "spread")?.passed ?? false,
      volatilityAcceptable: r.checklist.find(c => c.key === "volatility")?.passed ?? true,
      noAbnormalConditions: !r.news.blocked,
      riskWithinLimits: r.checklist.find(c => c.key === "daily" || c.key === "dailyLimit")?.passed ?? true,
      allChecksPassed: confirmed,
    },
  } as AISignal;
}
