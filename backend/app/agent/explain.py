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
    if ps.get("agent"):
        return _agent_explanation(r, s, ps, why, f, lang)
    fade = a.get("style") == "reversal"
    bars = s["params"].get("maxBars")
    tf = ps.get("timeframe") or r["timeframes"]["entry"]
    if lang == "ar":
        parts = [f"الخطة: {ps.get('name', '')} {tf}" + (" (عكس الحركة الممتدة)." if fade else " (مع الاتجاه)."),
                 "السبب: " + "، ".join(why) + ".",
                 f"الدخول بسعر السوق عند {f(s['entry'])}، الوقف {f(s['sl'])} ({js_str(s['slPips'])} نقطة)، هدف واحد {f(s['tp3'])} (2R).",
                 f"كتسد الصفقة بالسوق من بعد {bars} شمعة {tf} إلا ما وصلاتش للهدف ولا للوقف.",
                 (f"كتسد بالسوق من بعد {s['params']['maxBars']} شمعة {tf} إلا ما وصلاتش للهدف ولا للستوب." if s["params"].get("maxBars") else ""),
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


def _agent_explanation(r: dict, s: dict, ps: dict, why: list[str], f, lang: str) -> str:
    """EUR/USD, GBP/USD, AUD/CHF: the pair's own agent and its order (a limit with its expiry, or a market order)."""
    limit = s["entryType"] == "LIMIT"
    tf = ps.get("timeframe") or r["timeframes"]["entry"]
    be = s["params"].get("breakeven")
    part = (s["params"].get("partials") or [0])[0]
    if lang == "ar":
        parts = [f"Agent {ps['agent']}: {ps.get('engine', '')} {tf}.", "السبب: " + "، ".join(why) + ".",
                 (f"أمر معلق LIMIT ف {f(s['entry'])}" if limit else f"دخول بالسوق ف {f(s['entry'])}") +
                 f"، الستوب {f(s['sl'])} ({js_str(s['slPips'])} نقطة)، الهدف {f(s['tp3'])} (1:{to_fixed(s['rrTarget'], 1)}).",
                 (f"إغلاق 50% ف {f(s['tp1'])} ونقل الستوب للدخول." if part else f"الستوب للدخول (BE) ملي يوصل الثمن {f(s['tp1'])}.") if be else "",
                 (f"كتسد بالسوق من بعد {s['params']['maxBars']} شمعة {tf} إلا ما وصلاتش للهدف ولا للستوب." if s["params"].get("maxBars") else ""),
                 f"الإلغاء: {s['invalidation']}.", "الخسارة ممكنة دائماً. لا يوجد ربح مضمون."]
        return " ".join(x for x in parts if x)
    parts = [f"Agent {ps['agent']}: {ps.get('engine', '')} {tf}.", "Why: " + "; ".join(why) + ".",
             (f"LIMIT order at {f(s['entry'])}" if limit else f"Market entry at the close {f(s['entry'])}") +
             f". Stop {f(s['sl'])} ({js_str(s['slPips'])} pips), target {f(s['tp3'])} (1:{to_fixed(s['rrTarget'], 1)}).",
             (f"Close 50 % at {f(s['tp1'])} and move the stop to the entry." if part else f"Stop to break-even once the price reaches {f(s['tp1'])}.") if be else "",
             (f"Closed at market after {s['params']['maxBars']} {tf} candles if neither the stop nor the target is reached." if s["params"].get("maxBars") else ""),
             f"Invalidation: {s['invalidation']}.", f"Score {r['score']}/100. Losses happen; this is not a guaranteed outcome."]
    return " ".join(x for x in parts if x)
