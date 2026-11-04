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
from ..strategies._pairs import PAIRS
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
    # Exact pairs first ("audchf", "aud/chf"), then the usual nicknames
    for pair in PAIRS:
        a, b = pair.lower().split("/")
        if re.search(rf"{a}\s*[/ _-]?\s*{b}", t):
            wanted.append(pair.replace("/", ""))
    if not any(w.startswith("EUR") for w in wanted) and re.search(r"(eur|euro|يورو|اليورو)", t):
        wanted.append("EURUSD")
    if "GBPUSD" not in wanted and re.search(r"(gbp|cable|pound|sterling|livre|جنيه|الباوند|باوند)", t):
        wanted.append("GBPUSD")
    if not any(w.startswith("AUD") for w in wanted) and re.search(r"(aussie|\baud\b)", t):
        wanted.append("AUDCHF")
    if not any(w.endswith("CHF") for w in wanted) and re.search(r"(\bchf\b|franc|swissy)", t):
        wanted.append("EURCHF")
    if "AUDCAD" not in wanted and re.search(r"(loonie|\bcad\b)", t):
        wanted.append("AUDCAD")
    return wanted or ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]


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


def _strategy_line(r: dict) -> str:
    """The pair's strategy in one line: what it does and why, and how it did on the unseen part of its test."""
    ps = r.get("pairStrategy") or {}
    if not ps:
        return ""
    ov = r.get("overlay") or {}
    return f"**Agent:** {ps['name']} ({ps['timeframe']}) · state {ov.get('fsmState', '—')}: {ps['why']}"


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
        lv = [x for x in (r["facts"].get("levels") or []) if x.get("untaken") is not False and x.get("kind") != "ROUND"]
        lv.sort(key=lambda x: abs(x["price"] - r["price"]))
        levels = " · ".join(f"{x.get('label') or x['kind']} {f(x['price'])}" for x in lv[:5])
        checklist = "\n".join(f"{'✔' if c['passed'] else '✘'} {c['ruleAr'] if lang == 'ar' else c['rule']} — {c['detail']}" for c in r["checklist"])
        s = r["setup"]
        if s and r["status"] == "SIGNAL":
            v = validate_signal(r)
            issues = "" if v["approved"] else f" · ✘ {'; '.join(v['issues'])}"
            targets = f"TP1 {f(s['tp1'])} · TP2 {f(s['tp3'])} (1:{to_fixed(s['rrTarget'], 1)})"
            plan = (f"{s['direction']} {s['entryType']} · {t['entry']} {f(s['entry'])} · SL {f(s['sl'])} ({js_str(s['slPips'])} pips) · "
                    f"{targets} · score {js_str(v['score'])}/100{issues}")
        elif s and r["status"] == "WATCH":
            plan = f"WATCH (score {r['score']} < 75): {s['direction']} {f(s['entry'])} / SL {f(s['sl'])} / TP2 {f(s['tp2'])} — {t['noTrade']}"
        else:
            plan = f"{t['noTrade']} — {t['missing']}: {r['rejection'] or r['headline']}"
        score_txt = f" (score {r['score']})" if s else ""
        lines = [
            head,
            _strategy_line(r),
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


WHAT = {
    "ASIAN_BOX": ("the Asian session range (00:00–07:00/07:30 UTC+1): the stops of the night rest just beyond its high and low",
                  "رينج جلسة آسيا: الستوبات ديال الليل كاينين فوق القمة وتحت القاع ديالو"),
    "LONDON_BOX": ("the London session range (08:00–13:15 UTC+1): its high / low become New York liquidity targets",
                   "رينج لندن: القمة والقاع ديالو كيوليو أهداف سيولة لنيويورك"),
    "FVG_BULL": ("a bullish fair value gap: Low[-1] above High[-3], an imbalance the price tends to refill; the dashed line is its 50 % (CE)",
                 "فجوة FVG صاعدة: الخط المتقطع هو 50% (CE) فين كيتحط الأمر"),
    "FVG_BEAR": ("a bearish fair value gap: High[-1] below Low[-3]; the dashed line is its 50 % (CE)", "فجوة FVG هابطة: الخط المتقطع هو 50%"),
    "OB_BULL": ("a bullish order block: the lowest down candle of the 10 before the break; the dashed line is OB_Mean (50 % of its body)",
                "بلوك أوامر صاعد: الخط المتقطع هو 50% ديال الجسم"),
    "OB_BEAR": ("a bearish order block: the highest up candle of the 10 before the break; the dashed line is OB_Mean", "بلوك أوامر هابط"),
    "OTE_GOLD_ZONE": ("the Fibonacci OTE of the displacement leg, 61.8–78.6 %; the dotted line is the 70.5 % sweet spot",
                      "منطقة OTE ديال فيبوناتشي 61.8–78.6%، والخط المنقط هو 70.5%"),
    "SUPPLY_BAND": ("the H4 supply zone: the 60-bar high down 0.8 × ATR_H4", "منطقة العرض H4"),
    "DEMAND_BAND": ("the H4 demand zone: the 60-bar low up 0.8 × ATR_H4", "منطقة الطلب H4"),
    "PDH": ("the previous day's high", "أعلى ثمن ديال البارح"), "PDL": ("the previous day's low", "أدنى ثمن ديال البارح"),
    "SESSION_HIGH": ("a session high: buy-side liquidity", "قمة الجلسة: سيولة الشراء"), "SESSION_LOW": ("a session low: sell-side liquidity", "قاع الجلسة"),
    "MSS_BREAK": ("the market structure shift: the swing a candle closed through", "كسر الهيكل: القمة / القاع لي سدات شمعة من وراه"),
    "EQUILIBRIUM": ("the 50 % of the range", "نص الرينج 50%"),
    "DIVERGENCE_LINE": ("the RSI divergence: price at or beyond its previous swing while RSI(14) is 3+ points better", "دايفرجنس RSI"),
}


def explain_overlay_item(r: dict, item_id: str, lang: str) -> str | None:
    """Explains one item of the pair agent's chart overlay from its own data."""
    ov = r.get("overlay") or {}
    d = r["spec"]["decimals"]
    f = lambda v: to_fixed(float(v), d)  # noqa: E731
    ar = lang == "ar"
    for z in ov.get("zones", []):
        if z["id"] == item_id:
            what = WHAT.get(z["category"], ("", ""))[1 if ar else 0]
            mid = f" · 50 % {f(z['midPrice'])}" if z.get("midPrice") is not None else ""
            return f"{z['label']}: {f(z['bottomPrice'])} – {f(z['topPrice'])}{mid}. {what}."
    for ln in ov.get("priceLines", []):
        if ln["id"] == item_id:
            what = WHAT.get(ln["category"], ("", ""))[1 if ar else 0]
            return f"{ln['label']} {f(ln['startPrice'])}" + (f" → {f(ln['endPrice'])}" if ln["endPrice"] != ln["startPrice"] else "") + f": {what}."
    for m in ov.get("markers", []):
        if m["id"] == item_id:
            return f"{m['text']} at {f(m['price'])} ({fmt_utc_minute(m['time'])} UTC)."
    if item_id == "trade" and r.get("setup"):
        return build_explanation(r, "ar" if ar else "en")
    return None
