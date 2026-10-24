import { ChecklistItem, InstrumentSpec, StrategyStatus } from "./types";

/** Lot size for a fixed % risk: (equity × risk%) / (SL distance × contract size), rounded DOWN to the lot step. */
export function lotSize(spec: InstrumentSpec, equity: number, riskPct: number, entry: number, sl: number): number {
  const riskPerLot = Math.abs(entry - sl) * spec.contractSize;
  if (!(riskPerLot > 0)) return 0;
  const raw = (equity * riskPct) / 100 / riskPerLot;
  const lots = Math.floor(raw / spec.lotStep + 1e-9) * spec.lotStep;
  return lots >= spec.minLot ? Number(lots.toFixed(2)) : 0;
}

export function lotTable(spec: InstrumentSpec, entry: number, sl: number, riskPct: number, balances: number[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const b of balances) out[`${b}$`] = lotSize(spec, b, riskPct, entry, sl);
  return out;
}

export const rr = (entry: number, sl: number, tp: number) => {
  const risk = Math.abs(entry - sl);
  return risk > 0 ? Math.abs(tp - entry) / risk : 0;
};

export const toPips = (spec: InstrumentSpec, distance: number) => Math.round((Math.abs(distance) / spec.pipSize) * 10) / 10;

/** Score = Σ weight × quality / Σ weight × 100 (quality 0-1, defaults to passed ? 1 : 0). */
export function scoreChecklist(items: (ChecklistItem & { quality?: number })[]): number {
  const total = items.reduce((s, i) => s + i.weight, 0);
  const got = items.reduce((s, i) => s + (i.passed ? i.weight * (i.quality ?? 1) : 0), 0);
  return total > 0 ? Math.round((got / total) * 100) : 0;
}

export function classify(score: number, requiredOk: boolean, thresholds: { signal: number; watch: number }): StrategyStatus {
  if (!requiredOk) return "NO_TRADE";
  if (score >= thresholds.signal) return "SIGNAL";
  if (score >= thresholds.watch) return "WATCH";
  return "IGNORE";
}
