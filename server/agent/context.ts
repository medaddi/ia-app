/**
 * Builds the JSON context handed to the AI agent: deterministic detector output only.
 */

import { StrategyResult } from "../strategies/shared/result";

export function buildAgentContext(results: StrategyResult[]) {
  return {
    generatedAt: new Date().toISOString(),
    instruments: results.map(r => ({
      symbol: r.symbol,
      strategy: r.strategyName,
      timeframes: r.timeframes,
      price: r.price,
      dataQuality: r.dataQuality,
      market: r.market,
      bias: r.bias,
      status: r.status,
      score: r.score,
      headline: r.headline,
      rejection: r.rejection,
      checklist: r.checklist.map(c => ({ rule: c.rule, passed: c.passed, required: c.required, detail: c.detail })),
      setup: r.setup ? {
        id: r.setup.id, type: r.setup.setup, direction: r.setup.direction, entryType: r.setup.entryType,
        entry: r.setup.entry, sl: r.setup.sl, tp1: r.setup.tp1, tp2: r.setup.tp2, tp3: r.setup.tp3,
        tp2Source: r.setup.tp2Source, tp3Source: r.setup.tp3Source, rrTp2: Number(r.setup.rrTp2.toFixed(2)),
        slPips: r.setup.slPips, lotsAt1Pct: r.setup.lots, invalidation: r.setup.invalidation,
        orderState: r.setup.lifecycle.state, expiresAt: r.setup.expiresAt ? new Date(r.setup.expiresAt * 1000).toISOString() : null,
      } : null,
      news: r.news,
      day: r.day,
      facts: r.facts,
    })),
  };
}
