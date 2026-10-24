/**
 * Deterministic trade explanation built only from the strategy result (no invented levels).
 * Order: bias → liquidity taken → structure shift → entry zone → targets → invalidation → risk.
 */

import { StrategyResult } from "../strategies/shared/result";

export function buildExplanation(r: StrategyResult, lang: "en" | "ar" = "en"): string {
  const d = r.spec.decimals;
  const f = (v: number) => Number(v).toFixed(d);
  const s = r.setup;
  const a = (s?.anchors || {}) as any;
  if (!s) {
    return lang === "ar"
      ? `لا صفقة (${r.displaySymbol}). الاتجاه: ${r.bias.direction}. السبب: ${r.rejection || r.headline}.`
      : `NO TRADE on ${r.displaySymbol}. Bias: ${r.bias.direction} (${r.bias.detail}). Reason: ${r.rejection || r.headline}.`;
  }
  const buy = s.direction === "BUY";
  const parts: string[] = [];
  if (lang === "ar") {
    parts.push(`الاتجاه ${r.bias.direction === "BULLISH" ? "صاعد" : "هابط"} (${r.bias.detail}).`);
    if (a.sweep) parts.push(`تم سحب سيولة ${a.sweep.level.label} عند ${f(a.sweep.level.price)} (ذيل حتى ${f(a.sweep.extreme)}) ثم إغلاق داخل المستوى.`);
    if (a.mss) parts.push(`كسر هيكلي ${a.mss.type === "CHOCH" ? "CHoCH" : "BOS"} فوق/تحت ${f(a.mss.level)} بشمعة اندفاع.`);
    if (a.leg) parts.push(`رجوع إلى منطقة التوافق (فيبو 50–61.8% ${f(a.leg.fib618)}–${f(a.leg.fib50)}) مع شمعة تأكيد ${a.trigger}.`);
    parts.push(`الدخول ${s.entryType === "LIMIT" ? "بأمر معلق" : "بسعر السوق"} عند ${f(s.entry)}، الوقف ${f(s.sl)} (${s.slPips} نقطة).`);
    parts.push(`الأهداف: TP1 ${f(s.tp1)} (1R، إغلاق 50% ونقل الوقف للدخول)، TP2 ${f(s.tp2)} (${s.tp2Source}، 1:${s.rrTp2.toFixed(1)})، TP3 ${f(s.tp3)}.`);
    parts.push(`الإلغاء: ${s.invalidation}.`);
    parts.push(`المخاطرة 1% من الرصيد فقط. لا يوجد ربح مضمون.`);
  } else {
    parts.push(`Bias ${r.bias.direction.toLowerCase()}: ${r.bias.detail}.`);
    if (a.sweep) parts.push(`Liquidity taken: ${a.sweep.level.label} ${f(a.sweep.level.price)} swept (wick ${f(a.sweep.extreme)}) and closed back inside.`);
    if (a.mss) parts.push(`Structure shift: M5 ${a.mss.type === "CHOCH" ? "CHoCH" : "BOS"} ${buy ? "above" : "below"} ${f(a.mss.level)} with a displacement candle.`);
    if (a.poi) parts.push(`Entry zone: ${a.poi.kind} ${f(a.poi.bottom)}–${f(a.poi.top)}, limit at its 50% ${f(s.entry)}.`);
    if (a.leg) parts.push(`Pullback into confluence (Fib 50–61.8% ${f(Math.min(a.leg.fib50, a.leg.fib618))}–${f(Math.max(a.leg.fib50, a.leg.fib618))}${a.ob ? `, H1 OB ${f(a.ob.bottom)}–${f(a.ob.top)}` : ""}), confirmed by ${a.trigger}; entry at the close ${f(s.entry)}.`);
    if (a.asia) parts.push(`Asian range ${f(a.asia.low)}–${f(a.asia.high)} false breakout, entry at the close ${f(s.entry)}.`);
    parts.push(`Stop ${f(s.sl)} (${s.slPips} pips). Targets: TP1 ${f(s.tp1)} (1R, close 50%, stop to breakeven), TP2 ${f(s.tp2)} (${s.tp2Source}, 1:${s.rrTp2.toFixed(1)}), TP3 ${f(s.tp3)} (${s.tp3Source}).`);
    parts.push(`Invalidation: ${s.invalidation}.`);
    parts.push(`Score ${r.score}/100. Risk is fixed at 1% of equity; this is not a guaranteed outcome.`);
  }
  return parts.join(" ");
}
