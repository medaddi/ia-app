"""
In-app AI agent.
- Answers only from the deterministic strategy results (build_agent_context), never from its own analysis.
- With GEMINI_API_KEY it asks Gemini using the generated system prompt, then rejects the answer
  if it contains any price that is not in the context (no invented levels). Otherwise, or on
  rejection, it returns a deterministic answer in the required format.
- Explains any drawing on the chart from the drawing's own data and the shared definitions.
"""

import json
import re
from datetime import datetime, timezone

import httpx

from ..config import settings
from ..strategies.alexg.config import ALEXG_CONFIGS
from ..strategies.shared.jsnum import finite, fmt_utc_minute, iso, js_str, round_to, to_fixed
from .explain import build_explanation
from .system_prompt import build_system_prompt
from .validator import validate_signal

DARIJA = re.compile(r"\b(chno|chnou|kifach|kifash|wach|wash|dyal|dial|bghit|safqa|daba|3lach|3lash|mzn|khas|kayn|kayna|wla|bzaf|f had|dyali)\b")
FRENCH = re.compile(r"\b(pourquoi|quel|quelle|est-ce|analyse|le |la |les |pas de|achat|vente|tendance)\b")


def detect_lang(text: str) -> str:
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    t = f" {text.lower()} "
    if DARIJA.search(t):
        return "darija"
    if FRENCH.search(t):
        return "fr"
    return "en"


def symbols_from_question(text: str) -> list[str]:
    t = text.lower()
    wanted = []
    if re.search(r"(xau|gold|dhab|dahab|ذهب|\bor\b)", t):
        wanted.append("XAUUSD")
    # Exact pairs first ("eurchf", "nzd/cad", "aud cad"), then the usual nicknames
    for pair in ALEXG_CONFIGS:
        a, b = pair.lower().split("/")
        if re.search(rf"{a}\s*[/ _-]?\s*{b}", t):
            wanted.append(pair.replace("/", ""))
    if not any(w.startswith("EUR") for w in wanted) and re.search(r"(eur|euro|يورو|اليورو)", t):
        wanted.append("EURUSD")
    if "GBPUSD" not in wanted and re.search(r"(gbp|cable|pound|sterling|livre|جنيه|الباوند|باوند)", t):
        wanted.append("GBPUSD")
    if not any(w in ("USDCAD", "NZDCAD", "AUDCAD") for w in wanted) and re.search(r"(loonie|\bcad\b)", t):
        wanted.append("USDCAD")
    if not any(w.startswith("NZD") for w in wanted) and re.search(r"(kiwi|\bnzd\b)", t):
        wanted.append("NZDUSD")
    return wanted or ["XAUUSD", "EURUSD", "GBPUSD"]


L = {
    "en": {"bias": "Bias", "levels": "Key levels", "setup": "Setup status", "plan": "Plan", "noTrade": "NO TRADE", "missing": "missing rule", "risk": "Risk",
           "riskText": "1% of equity per trade, losses are part of trading; nothing here is guaranteed.", "data": "Data not usable", "entry": "Entry", "lot": "lot per $1k"},
    "fr": {"bias": "Biais", "levels": "Niveaux clés", "setup": "État du setup", "plan": "Plan", "noTrade": "PAS DE TRADE", "missing": "règle manquante", "risk": "Risque",
           "riskText": "1 % du capital par trade ; les pertes font partie du trading, rien n'est garanti.", "data": "Données inutilisables", "entry": "Entrée", "lot": "lot par 1k$"},
    "ar": {"bias": "الاتجاه", "levels": "المستويات المهمة", "setup": "حالة الإعداد", "plan": "الخطة", "noTrade": "لا صفقة", "missing": "الشرط الناقص", "risk": "المخاطرة",
           "riskText": "1% من الرصيد لكل صفقة، والخسارة جزء من التداول؛ لا شيء مضمون.", "data": "البيانات غير صالحة", "entry": "الدخول", "lot": "لوت لكل 1000$"},
    "darija": {"bias": "Ttijah (bias)", "levels": "Niveaux mohimmin", "setup": "7alat setup", "plan": "Plan", "noTrade": "MA KAYNACH TRADE", "missing": "chart li na9es", "risk": "Risk",
               "riskText": "1% mn l'capital f kol trade; l'khsara jz2 mn trading, walo madmoun.", "data": "Data ma salhach", "entry": "Dkhoul", "lot": "lot l kol 1000$"},
}


def build_agent_context(results: list[dict]) -> dict:
    def setup_ctx(s):
        if not s:
            return None
        return {
            "id": s["id"], "type": s["setup"], "direction": s["direction"], "entryType": s["entryType"],
            "entry": s["entry"], "sl": s["sl"], "tp1": s["tp1"], "tp2": s["tp2"], "tp3": s["tp3"],
            "tp2Source": s["tp2Source"], "tp3Source": s["tp3Source"], "rrTp2": round_to(s["rrTp2"], 2),
            "slPips": s["slPips"], "lotsAt1Pct": s["lots"], "invalidation": s["invalidation"],
            "orderState": s["lifecycle"]["state"], "expiresAt": iso(s["expiresAt"]) if s["expiresAt"] else None,
        }

    return {
        "generatedAt": iso(datetime.now(timezone.utc).timestamp()),
        "instruments": [{
            "symbol": r["symbol"], "strategy": r["strategyName"], "timeframes": r["timeframes"], "price": r["price"],
            "dataQuality": r["dataQuality"], "market": r["market"], "bias": r["bias"], "status": r["status"], "score": r["score"],
            "headline": r["headline"], "rejection": r["rejection"],
            "checklist": [{"rule": c["rule"], "passed": c["passed"], "required": c["required"], "detail": c["detail"]} for c in r["checklist"]],
            "setup": setup_ctx(r["setup"]), "news": r["news"], "day": r["day"], "facts": r["facts"],
            "historyStats": r.get("historyStats"),  # the pair's performance under the current rules
        } for r in results],
    }


def _gpa_answer(r: dict, lang: str, head: str, f) -> str:
    """Forex answer in the 5 parts of the Set & Forget rules: trend sync, AOI, grade, verdict, parameters."""
    ar = lang == "ar"
    fa = r["facts"]
    conf = [c for c in r["checklist"] if c["weight"] == 10]
    live = r.get("liveGrade") or {}
    s = r["setup"]
    score = r["score"] if s else live.get("score", 0)
    grade = r["grade"] if s else live.get("grade", "NO TRADE")
    direction = {"BULLISH": "BUY only", "BEARISH": "SELL only"}.get(r["bias"]["direction"], "no majority → no trade")
    zones = fa.get("areasOfInterest") or []
    aoi_item = next((c for c in conf if c["key"] == "aoi"), None)
    if s and r["status"] == "SIGNAL" and s["lifecycle"]["state"] in ("OPEN", "PENDING"):
        verdict = "TAKE TRADE"
    elif r["bias"]["direction"] == "NEUTRAL" or score < 50:
        verdict = "NO TRADE"
    else:
        verdict = "WAIT"
    lines = [
        head,
        f"**1. {'تزامن الاتجاه' if ar else 'Trend Sync Check'}:** 1W {fa.get('trendW1', '—')} | 1D {fa.get('trendD1', '—')} | 4H {fa.get('trendH4', '—')} → {direction}",
        f"**2. {'منطقة الاهتمام' if ar else 'AOI Validation'}:** {aoi_item['detail'] if aoi_item and aoi_item['passed'] else ''}"
        + ("" if aoi_item and aoi_item["passed"] else ("Price is not at a valid zone. Nearest: " + " · ".join(f"{z['tfs']} {f(z['lo'])}–{f(z['hi'])} ({z['touches']} touches)" for z in zones[:3]) if zones else "No W1 / D1 zone with 3+ touches")),
        f"**3. {'التقييم' if ar else 'Confluence Checklist & Final Grade'}:** {score}% → {grade}\n"
        + "\n".join(f"{'✔' if c['passed'] else '✘'} +10% {c['ruleAr'] if ar else c['rule']} — {c['detail']}" for c in conf),
        f"**4. {'القرار' if ar else 'Final Verdict'}:** {verdict}" + ("" if verdict == "TAKE TRADE" else f" — {fa.get('progress') or r['headline']}"),
    ]
    if s and r["status"] == "SIGNAL":
        lines.append(f"**5. {'معطيات الصفقة' if ar else 'Trade Parameters'}:** {s['direction']} MARKET {f(s['entry'])} · SL {f(s['sl'])} ({js_str(s['slPips'])} pips) · "
                     f"TP {f(s['tp3'])} ({s['tp3Source']}) · R:R 1:{to_fixed(s['rrTarget'], 2)} · set & forget · {s['lifecycle']['state']}")
    else:
        lines.append(f"**5. {'معطيات الصفقة' if ar else 'Trade Parameters'}:** — ({'ما كاين حتى صفقة صالحة' if ar else 'no valid trade'})")
    return "\n".join(lines)


def deterministic_answer(results: list[dict], lang: str) -> str:
    t = L[lang]
    blocks = []
    for r in results:
        d = r["spec"]["decimals"]
        f = lambda v: to_fixed(float(v), d)  # noqa: E731
        head = f"**{r['symbol']} — {r['strategyName']}** ({r['timeframes']['bias']} → {r['timeframes']['entry']})"
        if not r["dataQuality"]["ok"]:
            blocks.append(f"{head}\n{t['data']}: {r['dataQuality']['reason']}")
            continue
        if r["strategy"] == "FXAlexG_SetForget_GPA":
            blocks.append(_gpa_answer(r, lang, head, f))
            continue
        lv = [x for x in (r["facts"].get("levels") or []) if x.get("untaken") is not False and x.get("kind") != "ROUND"]
        lv.sort(key=lambda x: abs(x["price"] - r["price"]))
        levels = " · ".join(f"{x.get('label') or x['kind']} {f(x['price'])}" for x in lv[:5])
        checklist = "\n".join(f"{'✔' if c['passed'] else '✘'} {c['ruleAr'] if lang == 'ar' else c['rule']} — {c['detail']}" for c in r["checklist"])
        s = r["setup"]
        if s and r["status"] == "SIGNAL":
            v = validate_signal(r)
            issues = "" if v["approved"] else f" · ✘ {'; '.join(v['issues'])}"
            targets = (f"exit at the first H4 close {'above' if s['direction'] == 'BUY' else 'below'} EMA5 · safety TP {f(s['tp3'])}" if s["setup"] == "RSI2"
                       else f"TP1 {f(s['tp1'])} · TP2 {f(s['tp2'])} (1:{to_fixed(s['rrTp2'], 1)}) · TP3 {f(s['tp3'])}")
            plan = (f"{s['direction']} {s['entryType']} · {t['entry']} {f(s['entry'])} · SL {f(s['sl'])} ({js_str(s['slPips'])} pips) · "
                    f"{targets} · score {js_str(v['score'])}/100{issues}")
        elif s and r["status"] == "WATCH":
            plan = f"WATCH (score {r['score']} < 75): {s['direction']} {f(s['entry'])} / SL {f(s['sl'])} / TP2 {f(s['tp2'])} — {t['noTrade']}"
        else:
            plan = f"{t['noTrade']} — {t['missing']}: {r['rejection'] or r['headline']}"
        score_txt = f" (score {r['score']})" if s else ""
        lines = [
            head,
            f"**{t['bias']}:** {r['bias']['direction']} — {r['bias']['detail']}",
            f"**{t['levels']}:** {levels or '—'}",
            f"**{t['setup']}:** {r['status']}{score_txt}\n{checklist}",
            f"**{t['plan']}:** {plan}",
            build_explanation(r, "ar" if lang == "ar" else "en") if s and r["status"] == "SIGNAL" else "",
            f"**{t['risk']}:** {t['riskText']}",
        ]
        blocks.append("\n".join(x for x in lines if x))
    return "\n\n".join(blocks)


def invents_numbers(answer: str, context) -> list[str]:
    """Every price-like number in the answer must exist in the context (at the instrument's precision)."""
    allowed: set[str] = set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)) and finite(v):
            allowed.update((to_fixed(v, 2), to_fixed(v, 4), to_fixed(v, 5), js_str(v)))
        elif isinstance(v, str):
            allowed.update(re.findall(r"\d+\.\d+", v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(context)
    bad = []
    for m in re.findall(r"\b\d{1,5}\.\d{2,5}\b", answer):
        n = float(m)
        if n < 0.5 or n > 100000:
            continue
        if not (m in allowed or to_fixed(n, 2) in allowed or to_fixed(n, 4) in allowed or to_fixed(n, 5) in allowed):
            bad.append(m)
    return bad


async def _gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {"systemInstruction": {"parts": [{"text": build_system_prompt()}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1}}
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(url, params={"key": settings.gemini_api_key}, json=body)
    res.raise_for_status()
    cands = res.json().get("candidates") or []
    parts = ((cands[0].get("content") or {}).get("parts") or []) if cands else []
    return "".join(p.get("text", "") for p in parts).strip()


async def ask_agent(question: str, results: list[dict]) -> dict:
    lang = detect_lang(question)
    wanted = symbols_from_question(question)
    scoped = [r for r in results if r["symbol"] in wanted]
    context = build_agent_context(scoped)
    fallback = deterministic_answer(scoped, lang)
    if not settings.gemini_api_key or settings.gemini_api_key == "MY_GEMINI_API_KEY":
        return {"answer": fallback, "source": "deterministic", "lang": lang}
    try:
        text = await _gemini(f"CONTEXT (deterministic strategy output, the only source of truth):\n{json.dumps(context, ensure_ascii=False)}\n\n"
                             f"User language: {lang}\nUser question: {question}")
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as err:
        return {"answer": fallback, "source": "deterministic", "lang": lang, "note": f"Model unavailable: {err}"}
    if not text:
        return {"answer": fallback, "source": "deterministic", "lang": lang, "note": "Empty model reply"}
    invented = invents_numbers(text, context)
    if invented:
        return {"answer": fallback, "source": "deterministic", "lang": lang, "note": f"Model reply rejected: prices not in the data ({', '.join(invented[:3])})"}
    return {"answer": text, "source": "gemini", "lang": lang}


LEVEL_WHAT = {"PDH": "previous day high", "PDL": "previous day low", "PWH": "previous week high", "PWL": "previous week low",
              "$$$": "equal highs/lows (resting stops)", "Asia H": "Asian session high", "Asia L": "Asian session low",
              "London H": "London session high", "London L": "London session low"}


def explain_drawing(r: dict, drawing: dict, lang: str) -> str:
    """Explains one chart drawing from its own data and the shared definitions."""
    d = r["spec"]["decimals"]
    f = lambda v: to_fixed(float(v), d)  # noqa: E731
    time_ = lambda t: f"{fmt_utc_minute(t)} UTC" if t else "now"  # noqa: E731
    tf = drawing.get("tf") or ""
    ar = lang == "ar"
    layer = drawing.get("layer")
    text = drawing.get("text") or ""
    p1, p2 = drawing.get("p1"), drawing.get("p2")
    bull = drawing.get("color") == "bull"
    faded = drawing.get("faded")
    if layer == "structure":
        choch = "CHoCH" in text
        if ar:
            return (f"{'CHoCH (تغير الطابع)' if choch else 'BOS (كسر الهيكل)'} على {tf}: شمعة أغلقت {'فوق' if bull else 'تحت'} القمة/القاع المؤكد عند {f(p1)} "
                    f"(تكوّن {time_(drawing.get('t1'))}، كُسر {time_(drawing.get('t2'))}). {'هذا أول إغلاق عكس الاتجاه السابق.' if choch else 'إغلاق في اتجاه الترند الحالي.'}")
        return (f"{'CHoCH (change of character)' if choch else 'BOS (break of structure)'} on {tf}: a candle CLOSED {'above' if bull else 'below'} the confirmed swing at {f(p1)} "
                f"(formed {time_(drawing.get('t1'))}, broken {time_(drawing.get('t2'))}). "
                f"{'It is the first close against the previous trend.' if choch else 'The close is in the direction of the current trend.'}")
    if layer == "fvg" and p2 is not None:
        if ar:
            return f"فجوة FVG على {tf} بين {f(p2)} و {f(p1)}: الشمعة الأولى والثالثة لا تتلامسان. منتصفها {f((p1 + p2) / 2)}. {'تم ملء 50% منها (مستعملة).' if faded else 'لم يُملأ نصفها بعد.'}"
        return (f"{tf} Fair Value Gap {f(p2)}–{f(p1)}: candle 1 and candle 3 do not overlap, leaving an imbalance (size ≥ 0.25 × ATR). Its 50% line is {f((p1 + p2) / 2)}. "
                f"{'Price has already filled 50%, so it is mitigated.' if faded else 'Price has not filled 50% yet.'}")
    if layer == "ob" and p2 is not None:
        if ar:
            return f"بلوك أوامر {'طلب' if bull else 'عرض'} على {tf} ({f(p2)}–{f(p1)}): آخر شمعة عكسية قبل الاندفاع (جسم > 1.5× المتوسط) الذي كسر الهيكل. {'السعر رجع إليه (مستعمل).' if faded else 'لم يُختبر بعد.'}"
        return (f"{tf} {'demand' if bull else 'supply'} order block {f(p2)}–{f(p1)}: the last opposite-coloured candle before the displacement (body > 1.5× the 20-candle average) "
                f"that broke structure. {'Price has returned into it (mitigated).' if faded else 'Not revisited yet.'}")
    if layer in ("levels", "liquidity"):
        if drawing.get("kind") == "marker":
            if ar:
                return f"سحب سيولة عند {f(p1)} ({time_(drawing.get('t1'))}): ذيل تجاوز المستوى ثم أُغلقت الشمعة داخله."
            return f"Liquidity sweep at {f(p1)} ({time_(drawing.get('t1'))}): the wick went beyond the level and the candle closed back inside."
        if ar:
            return f"مستوى {text} عند {f(p1)}: سيولة (أوامر وقف) تتجمع هنا."
        return f"{text} at {f(p1)}: {LEVEL_WHAT.get(text, 'key level')}. Stops rest beyond it, which is why the strategy watches for a sweep here."
    if layer == "fib":
        return f"فيبوناتشي {text} لآخر موجة اندفاع H1 عند {f(p1)}." if ar else f"Fibonacci {text} of the last H1 impulse leg at {f(p1)}; the forex pullback zone is 50–61.8%."
    if layer == "sessions":
        return f"جلسة {text}." if ar else f"{text} session window ({time_(drawing.get('t1'))} → {time_(drawing.get('t2'))})."
    if layer == "trade" and r["setup"]:
        return build_explanation(r, "ar" if ar else "en")
    return f"عنصر {drawing.get('id')}." if ar else f"Drawing {drawing.get('id')}."
