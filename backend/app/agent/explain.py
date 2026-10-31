"""
Deterministic trade explanation built only from the strategy result (no invented levels).
Order: bias → liquidity / level → structure shift or retest → entry → targets → invalidation → risk.
"""

from ..strategies.shared.jsnum import js_str, to_fixed


def build_explanation(r: dict, lang: str = "en") -> str:
    d = r["spec"]["decimals"]
    f = lambda v: to_fixed(float(v), d)  # noqa: E731
    s = r["setup"]
    if not s:
        reason = r["rejection"] or r["headline"]
        if lang == "ar":
            return f"لا صفقة ({r['displaySymbol']}). الاتجاه: {r['bias']['direction']}. السبب: {reason}."
        return f"NO TRADE on {r['displaySymbol']}. Bias: {r['bias']['direction']} ({r['bias']['detail']}). Reason: {reason}."
    a = s.get("anchors") or {}
    buy = s["direction"] == "BUY"
    rr1 = to_fixed(s["rrTp2"], 1)
    parts: list[str] = []
    if lang == "ar":
        parts.append(f"الاتجاه {'صاعد' if r['bias']['direction'] == 'BULLISH' else 'هابط'} ({r['bias']['detail']}).")
        if a.get("sweep"):
            sw = a["sweep"]
            parts.append(f"تم سحب سيولة {sw['level']['label']} عند {f(sw['level']['price'])} (ذيل حتى {f(sw['extreme'])}) ثم إغلاق داخل المستوى.")
        if a.get("mss"):
            parts.append(f"كسر هيكلي {'CHoCH' if a['mss']['type'] == 'CHOCH' else 'BOS'} فوق/تحت {f(a['mss']['level'])} بشمعة اندفاع.")
        if a.get("reversion"):
            rv = a["reversion"]
            parts.append(f"رجوع للمتوسط: شمعة H1 سدات {'تحت' if buy else 'فوق'} نطاق بولينجر {f(rv['band'])} عكس الاتجاه، ومن بعد رجعات للداخل عند {f(rv['close'])} مع الاتجاه.")
        if a.get("breakout"):
            bo = a["breakout"]
            parts.append(f"اختراق: شمعة H1 أغلقت {'فوق أعلى' if buy else 'تحت أدنى'} {bo['lookback']} ساعة عند {f(bo['level'])} مع الاتجاه.")
        if a.get("leg"):
            parts.append(f"رجوع إلى منطقة التوافق (فيبو 50–61.8% {f(a['leg']['fib618'])}–{f(a['leg']['fib50'])}) مع شمعة تأكيد {a.get('trigger')}.")
        if a.get("breakRetest"):
            br = a["breakRetest"]
            parts.append(f"منطقة اهتمام على اليسار {f(br['level'])} ({br['touches']} لمسات): كسرها السعر بإغلاق H4 ثم رجع لإعادة الاختبار وأعطى شمعة تأكيد ({br['pattern']}).")
        parts.append(f"الدخول {'بأمر معلق' if s['entryType'] == 'LIMIT' else 'بسعر السوق'} عند {f(s['entry'])}، الوقف {f(s['sl'])} ({js_str(s['slPips'])} نقطة).")
        if a.get("breakRetest"):
            parts.append(f"Set & forget: هدف واحد {f(s['tp3'])} (3R)، بدون إغلاق جزئي وبدون نقل الوقف للدخول.")
        else:
            parts.append(f"الأهداف: TP1 {f(s['tp1'])} (1R، إغلاق 50% ونقل الوقف للدخول)، TP2 {f(s['tp2'])} ({s['tp2Source']}، 1:{rr1})، TP3 {f(s['tp3'])}.")
        parts.append(f"الإلغاء: {s['invalidation']}.")
        parts.append("الخسارة ممكنة دائماً. لا يوجد ربح مضمون.")
    else:
        parts.append(f"Bias {r['bias']['direction'].lower()}: {r['bias']['detail']}.")
        if a.get("sweep"):
            sw = a["sweep"]
            parts.append(f"Liquidity taken: {sw['level']['label']} {f(sw['level']['price'])} swept (wick {f(sw['extreme'])}) and closed back inside.")
        if a.get("mss"):
            parts.append(f"Structure shift: M5 {'CHoCH' if a['mss']['type'] == 'CHOCH' else 'BOS'} {'above' if buy else 'below'} {f(a['mss']['level'])} with a displacement candle.")
        if a.get("reversion"):
            rv = a["reversion"]
            parts.append(f"Reversion ({rv['session']}): an H1 candle closed {'below' if buy else 'above'} the Bollinger band {f(rv['band'])} against the trend, "
                         f"then this candle closed back inside at {f(rv['close'])} with the trend; one target at 1R toward the mean (middle {f(rv['mid'])}), "
                         f"closed at market after 24 H1 candles.")
        if a.get("breakout"):
            bo = a["breakout"]
            parts.append(f"Breakout: an H1 candle closed {'above the' if buy else 'below the'} {bo['lookback']}-hour {'high' if buy else 'low'} "
                         f"{f(bo['level'])} with the trend; market entry at the close {f(s['entry'])}.")
        if a.get("poi"):
            p = a["poi"]
            parts.append(f"Entry zone: {p['kind']} {f(p['bottom'])}–{f(p['top'])}, limit at its 50% {f(s['entry'])}.")
        if a.get("leg"):
            leg = a["leg"]
            ob = a.get("ob")
            ob_txt = f", H1 OB {f(ob['bottom'])}–{f(ob['top'])}" if ob else ""
            parts.append(f"Pullback into confluence (Fib 50–61.8% {f(min(leg['fib50'], leg['fib618']))}–{f(max(leg['fib50'], leg['fib618']))}{ob_txt}), "
                         f"confirmed by {a.get('trigger')}; entry at the close {f(s['entry'])}.")
        if a.get("asia"):
            parts.append(f"Asian range {f(a['asia']['low'])}–{f(a['asia']['high'])} false breakout, entry at the close {f(s['entry'])}.")
        if a.get("rsi2"):
            q = a["rsi2"]
            parts.append(f"RSI(2) pullback: the H4 trend is {'up' if buy else 'down'} (EMA50 / EMA200) and an H4 candle closed with RSI(2) {js_str(q['rsi'])} "
                         f"{'below' if buy else 'above'} {js_str(q['level'])}; market entry at the close {f(s['entry'])}.")
            parts.append(f"Stop {f(s['sl'])} ({js_str(s['slPips'])} pips). Exit at the first H4 close {'above' if buy else 'below'} EMA5, safety target {f(s['tp3'])}, "
                         f"closed at market after 48 H4 candles; no partials, no breakeven.")
        elif a.get("gpa"):
            g = a["gpa"]
            z = g["aoi"]
            tr = g["trend"]
            word = {1: "bullish", -1: "bearish", 0: "none"}
            parts.append(f"Trend sync: W1 {word[tr['W1']]} · D1 {word[tr['D1']]} · H4 {word[tr['H4']]}. Price {'held above' if buy else 'stayed below'} the "
                         f"{z['tfs']} AOI {f(z['lo'])}–{f(z['hi'])} ({z['touches']} touches)"
                         + (f", {g['pattern']['type']} on the lower timeframe" if g["pattern"] else "")
                         + f", then a {g['session']} 30m engulfing; market entry at its close {f(s['entry'])}.")
            parts.append(f"Grade {g['grade']} ({g['score']}%). Set & forget: SL {f(s['sl'])} ({js_str(s['slPips'])} pips), one target {f(s['tp3'])} "
                         f"({s['tp3Source']}, 1:{to_fixed(s['rrTarget'], 1)}); no partials, no breakeven.")
        elif a.get("reversion"):
            parts.append(f"Stop {f(s['sl'])} ({js_str(s['slPips'])} pips), one target {f(s['tp3'])} (1R); no partials, no breakeven.")
        elif a.get("breakRetest"):
            br = a["breakRetest"]
            parts.append(f"Look left: area of interest {f(br['level'])} ({br['touches']} touches). Price broke it with an H4 close, moved away to {f(br['extreme'])}, "
                         f"came back to retest it and printed {'an' if br['pattern'] == 'engulfing' else 'a'} {br['pattern']}; market entry at the close {f(s['entry'])} (no anticipation).")
            parts.append(f"Set & forget: stop {f(s['sl'])} ({js_str(s['slPips'])} pips), one target {f(s['tp3'])} ({s['tp3Source']}); "
                         f"TP1 {f(s['tp1'])} and TP2 {f(s['tp2'])} are progress marks only, no partials, no breakeven.")
        else:
            parts.append(f"Stop {f(s['sl'])} ({js_str(s['slPips'])} pips). One target {f(s['tp3'])} ({s['tp3Source']}); "
                         f"TP1 {f(s['tp1'])} and TP2 {f(s['tp2'])} are progress marks, no partials, the stop stays at the structure.")
        parts.append(f"Invalidation: {s['invalidation']}.")
        parts.append(f"Score {r['score']}/100. Losses happen; this is not a guaranteed outcome.")
    return " ".join(parts)
