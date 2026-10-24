/**
 * Candle-close scheduler: evaluates each strategy the moment its entry candle closes
 * (gold M5, EURUSD M15) instead of waiting for a polling loop.
 * At close + graceMs it re-downloads the entry timeframe (no cache), and retries every
 * retryMs until the provider has published the closed bar, then hands the result over.
 */

import { getMarketSessionStatus } from "./liveMarket";
import { getStrategyResult, STRATEGY_DEFS, StrategyBundle, Sym } from "./strategies";
import { TF_SEC } from "./strategies/shared/types";

export interface SchedulerOptions {
  graceMs: number;
  retryMs: number;
  maxRetries: number;
}

export const DEFAULT_SCHEDULER: SchedulerOptions = { graceMs: 1200, retryMs: 2000, maxRetries: 10 };

/** Next candle close (unix seconds) strictly after `nowMs` for a timeframe. */
export function nextCloseSec(nowMs: number, tfSec: number): number {
  return (Math.floor(nowMs / 1000 / tfSec) + 1) * tfSec;
}

export function startCandleCloseScheduler(
  onClose: (sym: Sym, closeSec: number, bundle: StrategyBundle) => Promise<void>,
  opts: SchedulerOptions = DEFAULT_SCHEDULER
) {
  for (const sym of Object.keys(STRATEGY_DEFS) as Sym[]) {
    const def = STRATEGY_DEFS[sym];
    const tfSec = TF_SEC[def.entryTf];

    const schedule = () => {
      const now = Date.now();
      const close = nextCloseSec(now, tfSec);
      setTimeout(() => fire(close, 0), close * 1000 + opts.graceMs - now);
    };

    const fire = async (closeSec: number, attempt: number) => {
      try {
        if (!getMarketSessionStatus(sym).isOpen) return schedule();
        const bundle = await getStrategyResult(sym, { fresh: true });
        const entry = bundle.candles[def.entryTf] || [];
        const published = entry.some(c => c.time === closeSec - tfSec);
        if (!published && attempt < opts.maxRetries) {
          setTimeout(() => fire(closeSec, attempt + 1), opts.retryMs);
          return;
        }
        await onClose(sym, closeSec, bundle);
      } catch (err: any) {
        console.warn(`[CandleClose] ${sym} evaluation failed:`, err?.message || err);
      }
      schedule();
    };

    schedule();
    console.log(`[CandleClose] ${sym} evaluated at every ${def.entryTf} close (+${opts.graceMs}ms)`);
  }
}
