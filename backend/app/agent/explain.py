"""
Deterministic trade explanation built only from the strategy result (no invented levels).
Order: the pair's plan → why this candle → entry → stop and target → time limit → invalidation → risk.
"""

from ..strategies.shared.jsnum import js_str, to_fixed


def build_explanation(r: dict, lang: str = "en") -> str:
    d = r["spec"]["decimals"]
    f = lambda v: to_fixed(float(v), d)  # noqa: E731
    s = r["setup"]
    ps = r.get("pairStrategy") or {}
    if not s:
        reason = r["rejection"] or r["headline"]
        if lang == "ar":
            return f"لا صفقة ({r['displaySymbol']}). الاتجاه: {r['bias']['direction']}. السبب: {reason}."
        return f"NO TRADE on {r['displaySymbol']}. Bias: {r['bias']['direction']} ({r['bias']['detail']}). Reason: {reason}."
    a = (s.get("anchors") or {}).get("pair") or {}
    why = a.get("why") or []
    fade = a.get("style") == "reversal"
    bars = s["params"].get("maxBars")
    tf = ps.get("timeframe") or r["timeframes"]["entry"]
    if lang == "ar":
        parts = [f"الخطة: {ps.get('name', '')} {tf}" + (" (عكس الحركة الممتدة)." if fade else " (مع الاتجاه)."),
                 "السبب: " + "، ".join(why) + ".",
                 f"الدخول بسعر السوق عند {f(s['entry'])}، الوقف {f(s['sl'])} ({js_str(s['slPips'])} نقطة)، هدف واحد {f(s['tp3'])} (2R).",
                 f"كتسد الصفقة بالسوق من بعد {bars} شمعة {tf} إلا ما وصلاتش للهدف ولا للوقف.",
                 f"الإلغاء: {s['invalidation']}.", "الخسارة ممكنة دائماً. لا يوجد ربح مضمون."]
        return " ".join(parts)
    u = (ps.get("test") or {}).get("unseen") or {}
    parts = [f"Plan: {ps.get('name', '')} {tf} — {'a fade of a stretched close, against the move by design' if fade else 'a breakout with the trend'}.",
             "Why now: " + "; ".join(why) + ".",
             f"Market entry at the close {f(s['entry'])}. Stop {f(s['sl'])} ({js_str(s['slPips'])} pips), one target {f(s['tp3'])} "
             f"(1:{to_fixed(s['rrTarget'], 1)}); no partials, no breakeven: the stop and the target stay where they are.",
             f"Closed at market after {bars} {tf} candles if neither level is reached.",
             f"Invalidation: {s['invalidation']}."]
    if u:
        parts.append(f"On the unseen part of its test this plan made {u.get('totalR', 0):+}R on {u.get('trades')} trades ({u.get('tp2R')}% reached 2R).")
    parts.append(f"Score {r['score']}/100. Losses happen; this is not a guaranteed outcome.")
    return " ".join(parts)
