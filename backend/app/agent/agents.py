"""
Three agents, one trade: a signal goes out only when all three agree.

1. Market Analysis agent: reads the market on its own (not the strategy's rules): the daily trend (EMA20 / EMA50 on daily
   candles), the volatility regime (ATR now vs its usual level) and the high-impact news ahead. It writes a trend report
   and objects to a trade against the daily trend, in a volatility spike, or with major news less than an hour away.
2. Strategy agent: takes the strategy's own decision (rules, score, a fresh setup it may notify) and the market report,
   and builds the plan (entry, stop, target, R:R). It agrees only with a valid signal that fits the report.
3. Risk & Execution agent: the AI trade desk (rules re-checked, live data, price drift, live R:R, market open, currency
   exposure) plus the book: at most MAX_OPEN signals open at once. It approves the final order.

4. Trade management agent (after the entry, never before): runs the open trade like a disciplined professional. The plan
   is the edge, so the stop and the target never move; it tracks the progress (R now, best and worst since the fill), the
   strategy's own exits (RSI(2): an H4 close back across EMA5; time exits) and the market around the trade (news, a
   volatility spike, a daily trend turning against it), and says one thing to do: HOLD, CAUTION, EXIT SOON, WAIT or CANCEL.

Measured on each pair's past trades, the market agent's trend veto blocked 8 of 111 trades for about the same total result
(+0.3R): it mostly removes counter-trend trades, it is not a profit engine. Each agent can only block, never create a trade.
"""

import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal
from ..strategies.shared.types import TF_SEC, Candle
from .trade_desk import OPEN_STATES, review

MAX_OPEN = 4  # signals open at the same time across every pair
NEWS_AHEAD_SEC = 3600  # major news of the pair's currencies less than an hour away: no new trade
SPIKE_ATR = 2.5  # ATR(14) above 2.5 × its usual level = volatility spike
DAILY_FAST, DAILY_SLOW = 20, 50


def _ema(vals: list[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    k, e = 2 / (n + 1), vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _daily(c: list[Candle]) -> list[tuple[float, float, float, float]]:
    days: dict[int, list[float]] = {}
    for x in c:
        k = x.time // 86400
        if k not in days:
            days[k] = [x.open, x.high, x.low, x.close]
        else:
            d = days[k]
            d[1], d[2], d[3] = max(d[1], x.high), min(d[2], x.low), x.close
    return [tuple(days[k]) for k in sorted(days)]


def _vote(key: str, name: str, agree: bool, summary: str, checks: list[dict], extra: Optional[dict] = None) -> dict:
    return {"key": key, "name": name, "agree": bool(agree), "summary": summary, "checks": checks, **(extra or {})}


def _check(label: str, passed: bool, detail: str) -> dict:
    return {"label": label, "passed": bool(passed), "detail": detail}


def market_agent(r: dict, candles: list[Candle], news_events: list[dict], now: Optional[int] = None) -> dict:
    """The market report (always), and the agent's vote on the strategy's trade when there is one."""
    now = now or int(time.time())
    s = r.get("setup")
    d = r["spec"]["decimals"]
    closed = [x for x in candles if x.time < now - 1]
    days = _daily(closed)[:-1]  # complete days only
    closes = [x[3] for x in days]
    fast, slow = _ema(closes, DAILY_FAST), _ema(closes, DAILY_SLOW)
    if fast is None or slow is None:
        trend, trend_txt = 0, "not enough daily history"
    else:
        trend = 1 if fast > slow and closes[-1] > slow else -1 if fast < slow and closes[-1] < slow else 0
        trend_txt = (f"EMA{DAILY_FAST} {fast:.{d}f} {'>' if fast > slow else '<'} EMA{DAILY_SLOW} {slow:.{d}f}, "
                     f"close {closes[-1]:.{d}f}")
    tr = [max(x.high, p.close) - min(x.low, p.close) for p, x in zip(closed[-501:-1], closed[-500:])]
    atr = sum(tr[-14:]) / 14 if len(tr) >= 14 else 0
    usual = sorted(tr)[len(tr) // 2] if tr else 0
    ratio = atr / usual if usual else 1
    regime = "spike" if ratio > SPIKE_ATR else "high" if ratio > 1.5 else "low" if ratio < 0.7 else "normal"
    ccys = set(r["spec"]["displaySymbol"].split("/"))
    ahead = sorted((e for e in news_events if e.get("impact") == "High" and e.get("currency") in ccys and 0 < e["time"] - now <= 6 * 3600),
                   key=lambda e: e["time"])
    soon = [e for e in ahead if e["time"] - now <= NEWS_AHEAD_SEC]
    word = {1: "bullish", -1: "bearish", 0: "neutral"}[trend]
    report = {"dailyTrend": word, "trendDetail": trend_txt, "volatility": regime, "atrRatio": round(ratio, 2),
              "newsAhead": [{"currency": e["currency"], "title": e["title"], "inMin": int((e["time"] - now) // 60)} for e in ahead[:3]]}
    checks = [_check("Daily trend", True, f"{word} ({trend_txt})"),
              _check("Volatility regime", regime != "spike", f"{regime}: ATR {ratio:.2f}× its usual level"),
              _check("No major news within 1 h", not soon, f"{soon[0]['currency']} {soon[0]['title']} in {int((soon[0]['time'] - now) // 60)} min" if soon else
                     (f"next: {ahead[0]['currency']} {ahead[0]['title']} in {int((ahead[0]['time'] - now) // 60)} min" if ahead else "none in the next 6 h"))]
    if s:
        side = 1 if s["direction"] == "BUY" else -1
        checks.insert(1, _check("Trade with the daily trend (or a neutral one)", trend != -side,
                                f"{s['direction']} vs a {word} daily trend"))
    agree = bool(s) and all(c["passed"] for c in checks)
    summary = (f"Daily trend {word}, volatility {regime}" + (f", {len(ahead)} major news in 6 h" if ahead else ", no major news ahead")
               + ("" if not s else " · agrees with the trade" if agree else " · objects: " + "; ".join(c["label"] for c in checks if not c["passed"])))
    return _vote("market", "Market analysis", agree, summary, checks, {"report": report, "bias": word})


def strategy_agent(r: dict, market: dict) -> dict:
    """The strategy's decision turned into a plan; agrees with a valid, fresh signal that fits the market report."""
    s = r.get("setup")
    if not s:
        return _vote("strategy", "Strategy", False, r.get("headline") or "No setup", [_check("A setup", False, r.get("rejection") or r.get("headline", ""))])
    risk = abs(s["entry"] - s["sl"])
    rr = abs(s["tp3"] - s["entry"]) / risk if risk else 0
    d = r["spec"]["decimals"]
    plan = {"direction": s["direction"], "entryType": s["entryType"], "entry": s["entry"], "sl": s["sl"], "tp": s["tp3"], "rr": round(rr, 2)}
    checks = [
        _check("Strategy rules: signal", r["status"] == "SIGNAL", f"{r['status']} · score {r['score']}"),
        _check("Fresh setup the strategy may send", bool(r.get("canNotify")) and s["lifecycle"]["state"] in ("PENDING", "OPEN"), s["lifecycle"]["state"]),
        _check("Fits the market report", market["bias"] == "neutral" or (market["bias"] == "bullish") == (s["direction"] == "BUY"),
               f"{s['direction']} with a {market['bias']} daily trend"),
    ]
    agree = all(c["passed"] for c in checks)
    summary = f"{s['direction']} {s['entryType']} {s['entry']:.{d}f} · SL {s['sl']:.{d}f} · TP {s['tp3']:.{d}f} (1:{rr:.1f})"
    return _vote("strategy", "Strategy", agree, summary, checks, {"plan": plan})


def risk_agent(r: dict, db: Optional[Session]) -> dict:
    """The AI trade desk plus the size of the book: approves the final order."""
    if not r.get("setup"):
        return _vote("risk", "Risk & execution", False, "Nothing to execute", [])
    desk = review(r, db)
    checks = [_check(c["label"], c["passed"], c["detail"]) for c in desk["checks"]]
    if db is not None:
        n = len(db.scalars(select(Signal.id).where(Signal.state.in_(OPEN_STATES), Signal.id != r["setup"]["id"])).all())
        checks.append(_check(f"At most {MAX_OPEN} signals open across every pair", n < MAX_OPEN, f"{n} open now"))
    agree = all(c["passed"] for c in checks)
    summary = "Order approved" if agree else "Blocked: " + "; ".join(c["label"] for c in checks if not c["passed"])
    return _vote("risk", "Risk & execution", agree, summary, checks, {"score": desk["score"]})


def consensus(r: dict, candles: list[Candle], news_events: list[dict], db: Optional[Session]) -> dict:
    """The three votes; `approved` only when all three agree."""
    market = market_agent(r, candles, news_events)
    strategy = strategy_agent(r, market)
    risk = risk_agent(r, db)
    agents = [market, strategy, risk]
    agreed = sum(a["agree"] for a in agents)
    approved = agreed == 3
    return {"approved": approved, "agreed": agreed, "agents": agents,
            "summary": "3/3 agents agree: the trade is sent" if approved else f"{agreed}/3 agents agree: no trade",
            "issues": [f"{a['name']}: {a['summary']}" for a in agents if not a["agree"]]}


LIVE = ("OPEN", "TP1_HIT", "TP2_HIT")
CAUTION_NEWS_MIN = 60  # major news this close: be ready, add nothing
GIVEBACK_FROM, GIVEBACK_TO = 1.0, 0.25  # was +1R, now near entry


def _hhmm(t: int) -> str:
    return time.strftime("%H:%M", time.gmtime(t))


def _left(sec: int) -> str:
    sec = max(0, int(sec))
    h, m = sec // 3600, sec % 3600 // 60
    return f"{h}h {m:02d}m" if h else f"{m} min"


def _say(en: str, fr: str, ar: str) -> dict:
    return {"en": en, "fr": fr, "ar": ar}


def manager_agent(r: dict, candles: list[Candle], market: Optional[dict] = None, now: Optional[int] = None) -> Optional[dict]:
    """The trade-management agent for the pair's running (or pending) trade; None when there is no trade to manage.
    It never moves the stop or the target (that is the tested plan): it applies the strategy's own exits on time and
    reads the market around the trade to say whether to hold, be careful, or get ready to exit."""
    s = r.get("setup")
    state = s["lifecycle"]["state"] if s else None
    if state not in (*LIVE, "PENDING"):
        return None
    now = now or int(time.time())
    d = r["spec"]["decimals"]
    f = lambda v: f"{v:.{d}f}"  # noqa: E731
    buy = s["direction"] == "BUY"
    entry, sl, tp = s["entry"], s["sl"], s["tp3"]
    risk = abs(entry - sl) or 1e-9
    tf_sec = TF_SEC.get(r["timeframes"]["entry"], 3600)
    checks: list[dict] = []
    extra: dict = {}

    if state == "PENDING":
        exp = s.get("expiresAt")
        checks.append(_check("Limit order placed", True, f"{s['direction']} {s['entryType']} at {f(entry)} · SL {f(sl)} · TP {f(tp)}"))
        if exp and exp - now <= 1800:
            checks.append(_check("Order still valid", False, f"expires at {_hhmm(exp)} UTC ({_left(exp - now)})"))
            verdict = "CANCEL"
            action = _say(f"Not filled yet: delete the order at {_hhmm(exp)} UTC if the price has not come.",
                          f"Pas encore déclenché : supprimez l’ordre à {_hhmm(exp)} UTC si le prix n’est pas venu.",
                          f"ما تفعلش: مسح الأمر ف {_hhmm(exp)} UTC إلا ما جاش الثمن.")
        else:
            if exp:
                checks.append(_check("Order still valid", True, f"until {_hhmm(exp)} UTC"))
            verdict = "WAIT"
            action = _say(f"Wait for the price at {f(entry)}. Don't chase it with a market order.",
                          f"Attendez le prix à {f(entry)}. Ne le poursuivez pas au marché.",
                          f"تسنى الثمن ف {f(entry)}. ما تدخلش بالماركت.")
    else:
        price = r["price"]
        sign = 1 if buy else -1
        r_now = (price - entry) * sign / risk
        fill = s["lifecycle"].get("fillTime") or s["signalTime"]
        since = [c for c in candles if c.time >= fill]
        best = max([((c.high - entry) if buy else (entry - c.low)) / risk for c in since] + [r_now])
        worst = min([((c.low - entry) if buy else (entry - c.high)) / risk for c in since] + [r_now])
        target_r = abs(tp - entry) / risk
        extra.update(rNow=round(r_now, 2), bestR=round(best, 2), worstR=round(worst, 2), targetR=round(target_r, 2), bars=len(since))
        checks.append(_check("Plan intact: SL and TP stay", True,
                             f"SL {f(sl)} · TP {f(tp)} ({target_r:.1f}R): set & forget, moving them breaks the tested edge"))
        checks.append(_check("Progress", r_now > -0.7, f"{r_now:+.2f}R now · best {best:+.2f}R · worst {worst:+.2f}R · {len(since)} candle(s)"))

        exit_soon: Optional[dict] = None
        # The strategy's own exits, applied on time
        p = s.get("params") or {}
        if p.get("maxBars"):
            end = s["signalTime"] + int(p["maxBars"]) * tf_sec
            ok = end - now > tf_sec
            checks.append(_check("Time limit", ok, f"closed at {_hhmm(end)} UTC ({_left(end - now)})" if end - now < 86400
                                 else f"closed by {time.strftime('%m-%d %H:%M', time.gmtime(end))} UTC at the latest"))
            if not ok:
                exit_soon = _say(f"Time exit: close the trade at {_hhmm(end)} UTC ({_left(end - now)}).",
                                 f"Sortie au temps : fermez le trade à {_hhmm(end)} UTC ({_left(end - now)}).",
                                 f"خروج بالوقت: سد الصفقة ف {_hhmm(end)} UTC ({_left(end - now)}).")
                extra["exitAt"] = end
        ema5 = (r.get("facts") or {}).get("ema5")
        if s.get("setup") == "RSI2" and isinstance(ema5, (int, float)):
            close = (now // 14400 + 1) * 14400
            across = price > ema5 if buy else price < ema5
            where = "above" if buy else "below"
            checks.append(_check("EMA5 exit not triggered", not across,
                                 f"price {f(price)} {where if across else ('below' if buy else 'above')} EMA5 {f(ema5)} · H4 closes at {_hhmm(close)} UTC"))
            if across:
                exit_soon = _say(f"Exit forming: if the H4 candle closes {where} EMA5 ({f(ema5)}) at {_hhmm(close)} UTC, close the trade at that close.",
                                 f"Sortie en formation : si la bougie H4 clôture {'au-dessus' if buy else 'en dessous'} de l’EMA5 ({f(ema5)}) à {_hhmm(close)} UTC, fermez le trade à cette clôture.",
                                 f"الخروج كيتكون: إلا سدات شمعة H4 {'فوق' if buy else 'تحت'} EMA5 ({f(ema5)}) ف {_hhmm(close)} UTC، سد الصفقة.")
                extra["exitAt"] = close

        # The market around the trade: be careful, never improvise (the stop already caps the loss)
        cautions: list[str] = []
        rep = (market or {}).get("report") or {}
        soon = [n for n in rep.get("newsAhead", []) if n["inMin"] <= CAUTION_NEWS_MIN]
        if market is not None:
            checks.append(_check("No major news within 1 h", not soon, f"{soon[0]['currency']} {soon[0]['title']} in {soon[0]['inMin']} min" if soon else "none"))
            checks.append(_check("Volatility normal", rep.get("volatility") != "spike", f"{rep.get('volatility', '—')}: ATR {rep.get('atrRatio', '—')}× usual"))
            against = rep.get("dailyTrend") == ("bearish" if buy else "bullish")
            checks.append(_check("Daily trend not against the trade", not against, f"daily trend {rep.get('dailyTrend', '—')}"))
            if soon:
                cautions.append("news")
            if rep.get("volatility") == "spike":
                cautions.append("spike")
            if against:
                cautions.append("trend")
        giveback = best >= GIVEBACK_FROM and r_now <= GIVEBACK_TO
        checks.append(_check("Gain kept", not giveback, f"was {best:+.2f}R, now {r_now:+.2f}R" if giveback else f"best {best:+.2f}R"))
        if giveback:
            cautions.append("giveback")

        if exit_soon:
            verdict, action = "EXIT_SOON", exit_soon
        elif cautions:
            verdict = "CAUTION"
            first = cautions[0]
            action = {
                "news": _say(f"{soon[0]['currency']} news in {soon[0]['inMin']} min: keep the SL, add nothing, expect spikes." if soon else "",
                             f"News {soon[0]['currency']} dans {soon[0]['inMin']} min : gardez le SL, n’ajoutez rien, attendez-vous à des pics." if soon else "",
                             f"خبر {soon[0]['currency']} من بعد {soon[0]['inMin']} دقيقة: خلي SL، ما تزيدش، توقع حركات قوية." if soon else ""),
                "spike": _say("Volatility spike: wider swings, the stop already caps the loss. Hold, add nothing.",
                              "Pic de volatilité : mouvements plus larges, le stop limite déjà la perte. Gardez, n’ajoutez rien.",
                              "تقلب قوي: حركات كبيرة، الستوب كيحمي. خلي الصفقة، ما تزيدش."),
                "trend": _say("The daily trend turned against the trade: the plan still decides. Hold, don't double down.",
                              "La tendance daily s’est retournée : le plan décide toujours. Gardez, ne doublez pas.",
                              "الاتجاه اليومي ولى ضد الصفقة: الخطة هي اللي كتقرر. خلي، ما تضاعفش."),
                "giveback": _say(f"The trade gave back most of its {best:+.1f}R: that is part of the plan. Hold, don't close in fear.",
                                 f"Le trade a rendu l’essentiel de ses {best:+.1f}R : ça fait partie du plan. Gardez, ne fermez pas par peur.",
                                 f"الصفقة رجعات أغلب {best:+.1f}R: هادشي من الخطة. خليها، ما تسدهاش بالخوف."),
            }[first]
        else:
            verdict = "HOLD"
            action = _say(f"Hold: {r_now:+.2f}R, plan intact. Nothing to do until TP or SL.",
                          f"Gardez : {r_now:+.2f}R, plan intact. Rien à faire jusqu’au TP ou au SL.",
                          f"خلي: {r_now:+.2f}R، الخطة سليمة. ما كاين ما تدير حتى TP ولا SL.")
    return _vote("manager", "Trade management", verdict in ("HOLD", "WAIT"), action["en"], checks,
                 {"verdict": verdict, "action": action, **extra})


def market_candles(bundle: dict) -> list[Candle]:
    """The candles the market agent reads: hourly where the strategy has them (gold, GPA), else H4 (RSI(2))."""
    c = bundle.get("candles") or {}
    return c.get("H1") or c.get("H4") or next(iter(c.values()), [])
