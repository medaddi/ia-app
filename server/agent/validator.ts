/**
 * Independent re-check of a signal before it is sent. It recomputes the rules from the signal's
 * own numbers and the strategy config. It can only LOWER the score or REJECT, never approve
 * something the strategy rejected.
 */

import { StrategyResult } from "../strategies/shared/result";
import { rr, scoreChecklist } from "../strategies/shared/risk";
import { XAU_CONFIG } from "../strategies/xauusd/config";
import { EUR_CONFIG } from "../strategies/eurusd/config";

export interface Validation {
  approved: boolean;
  score: number;
  issues: string[];
}

export function validateSignal(r: StrategyResult): Validation {
  const issues: string[] = [];
  const s = r.setup;
  if (r.status !== "SIGNAL" || !s) return { approved: false, score: Math.min(r.score, r.score), issues: ["Strategy status is not SIGNAL"] };
  if (!r.dataQuality.ok) issues.push(`Data not usable: ${r.dataQuality.reason}`);

  const buy = s.direction === "BUY";
  const ordered = buy ? s.sl < s.entry && s.entry < s.tp1 && s.tp1 < s.tp2 && s.tp2 <= s.tp3 : s.sl > s.entry && s.entry > s.tp1 && s.tp1 > s.tp2 && s.tp2 >= s.tp3;
  if (!ordered) issues.push("Levels are not in order (SL / entry / TP1 / TP2 / TP3)");

  const rrTp2 = rr(s.entry, s.sl, s.tp2);
  const dist = Math.abs(s.entry - s.sl);
  if (r.symbol === "XAUUSD") {
    if (rrTp2 < XAU_CONFIG.risk.minRrTp2 - 1e-9) issues.push(`R:R to TP2 ${rrTp2.toFixed(2)} < ${XAU_CONFIG.risk.minRrTp2}`);
    if (dist < XAU_CONFIG.risk.minSl || dist > XAU_CONFIG.risk.maxSl) issues.push(`Stop $${dist.toFixed(2)} outside $${XAU_CONFIG.risk.minSl}–$${XAU_CONFIG.risk.maxSl}`);
    if (s.entryType !== "LIMIT") issues.push("Gold entries must be LIMIT orders");
  } else {
    const pips = dist / r.spec.pipSize;
    if (rrTp2 < EUR_CONFIG.risk.minRr - 1e-9) issues.push(`R:R to TP2 ${rrTp2.toFixed(2)} < ${EUR_CONFIG.risk.minRr}`);
    if (pips < EUR_CONFIG.risk.minSlPips - 1e-6 || pips > EUR_CONFIG.risk.maxSlPips + 1e-6) issues.push(`Stop ${pips.toFixed(1)} pips outside ${EUR_CONFIG.risk.minSlPips}–${EUR_CONFIG.risk.maxSlPips}`);
  }
  const failed = r.checklist.filter(c => c.required && !c.passed);
  for (const f of failed) issues.push(`Required rule failed: ${f.rule}`);
  const recomputed = scoreChecklist(r.checklist);
  const thresholds = r.symbol === "XAUUSD" ? XAU_CONFIG.scoring.thresholds : EUR_CONFIG.scoring.thresholds;
  const score = Math.min(r.score, recomputed);
  if (score < thresholds.signal) issues.push(`Score ${score} < ${thresholds.signal}`);
  return { approved: issues.length === 0, score, issues };
}
