"""Prices, candles and the economic calendar (as news). XAU/USD and the forex pairs. No analysis: it is being rebuilt."""

import asyncio
import time
import zlib
from datetime import datetime, timezone

from fastapi import APIRouter

from ..market.data import TIMEFRAME_SECONDS, canonical as normalize_symbol, fetch_candle_series, fetch_live_price, market_session_status
from ..market.news import load_news_calendar

router = APIRouter(prefix="/api")

ASSETS = {
    "XAU/USD": {"id": "xauusd", "name": "Spot Gold", "arabicName": "الذهب الفوري", "frenchName": "Or au comptant", "category": "commodities", "pipSize": 0.1, "decimalPlaces": 2},
    "EUR/USD": {"id": "eurusd", "name": "Euro / US Dollar", "arabicName": "اليورو / الدولار", "frenchName": "Euro / Dollar US", "category": "forex", "pipSize": 0.0001, "decimalPlaces": 5},
    "GBP/USD": {"id": "gbpusd", "name": "British Pound / US Dollar", "arabicName": "الباوند / الدولار", "frenchName": "Livre sterling / Dollar US", "category": "forex", "pipSize": 0.0001, "decimalPlaces": 5},
    "EUR/CHF": {"id": "eurchf", "name": "Euro / Swiss Franc", "arabicName": "اليورو / الفرنك السويسري", "frenchName": "Euro / Franc suisse", "category": "forex", "pipSize": 0.0001, "decimalPlaces": 5},
    "AUD/CAD": {"id": "audcad", "name": "Australian Dollar / Canadian Dollar", "arabicName": "الدولار الأسترالي / الدولار الكندي", "frenchName": "Dollar australien / Dollar canadien", "category": "forex", "pipSize": 0.0001, "decimalPlaces": 5},
    "AUD/CHF": {"id": "audchf", "name": "Australian Dollar / Swiss Franc", "arabicName": "الدولار الأسترالي / الفرنك السويسري", "frenchName": "Dollar australien / Franc suisse", "category": "forex", "pipSize": 0.0001, "decimalPlaces": 5},
}
NEWS_CCYS = {"USD", *(c for sym in ASSETS if sym != "XAU/USD" for c in sym.split("/"))}


async def assets_list() -> list[dict]:
    prices = await asyncio.gather(*(fetch_live_price(s) for s in ASSETS))
    out = []
    for (sym, meta), p in zip(ASSETS.items(), prices):
        out.append({**meta, "symbol": sym, "price": p["price"], "change24h": p["change24h"], "change24hAmount": p["change24hAmount"],
                    "high24h": p["high24h"], "low24h": p["low24h"], "volume24h": "—",
                    "isMarketOpen": p["isMarketOpen"], "marketStatusLabel": p["marketStatusLabel"], "marketSource": p["source"], "nextOpen": p.get("nextOpen")})
    return out


@router.get("/market/assets")
async def market_assets():
    return {"assets": await assets_list(), "updated": int(time.time() * 1000)}


@router.get("/market/ticker")
async def market_ticker(symbol: str = "XAU/USD"):
    sym = normalize_symbol(symbol)
    p = await fetch_live_price(sym)
    s = market_session_status(sym)
    return {**p, "spread": None, "isMarketOpen": s["isOpen"], "marketStatusLabel": s["labelEn"], "sessionStage": s["sessionStage"], "updated": p["lastUpdated"]}


@router.get("/market/prices")
async def market_prices():
    """Every traded pair's live price in one request (each provider asked at most once a second, shared by all viewers)."""
    syms = list(ASSETS)
    got = await asyncio.gather(*(fetch_live_price(s) for s in syms), return_exceptions=True)
    out = {}
    for s, p in zip(syms, got):
        if isinstance(p, dict) and p.get("price"):
            out[s] = {"price": p["price"], "quoteTime": p.get("quoteTime"), "source": p.get("source")}
    return {"success": True, "prices": out, "at": int(time.time())}


@router.get("/market/candles")
async def market_candles(symbol: str = "XAU/USD", timeframe: str = "15M", count: int = 600, force: bool = False):
    sym = normalize_symbol(symbol)
    series = await fetch_candle_series(sym, timeframe if timeframe in TIMEFRAME_SECONDS else "15M", min(max(count, 10), 2000), fresh=force)
    return {"symbol": sym, "timeframe": timeframe, "candles": [c.to_dict() for c in series["candles"]], "indicators": None,
            "isLiveFeed": not series["isSynthetic"], "source": series["source"]}


@router.get("/exunu/candles")
async def chart_candles(symbol: str = "XAU/USD", timeframe: str = "15M", count: int = 300):
    """The chart's candles and the live price of one pair."""
    sym = normalize_symbol(symbol)
    tf = timeframe if timeframe in TIMEFRAME_SECONDS else "15M"
    series = await fetch_candle_series(sym, tf, min(1000, max(count, 10)))
    live = await fetch_live_price(sym)
    return {"success": True, "symbol": sym, "timeframe": tf, "candles": [c.to_dict() for c in series["candles"]], "isSynthetic": series["isSynthetic"],
            "source": series["source"], "price": live.get("price"), "quoteTime": live.get("quoteTime"), "priceSource": live.get("source")}


# ---------------------------------------------------------------- news (economic calendar)

def _category(title: str) -> str:
    t = title.lower()
    if "cpi" in t or "inflation" in t or "pce" in t:
        return "cpi"
    if "non-farm" in t or "employment" in t or "jobless" in t or "nfp" in t:
        return "nfp"
    if "fomc" in t or "fed" in t or "federal funds" in t or "powell" in t or "ecb" in t or "lagarde" in t or "rate" in t:
        return "fed"
    return "forex"


def _ago(ts: int, now: int) -> str:
    d = now - ts
    if d < 0:
        m = -d // 60
        return f"in {m} min" if m < 60 else f"in {m // 60} h" if m < 1440 else f"in {m // 1440} d"
    m = d // 60
    return f"{m} min ago" if m < 60 else f"{m // 60} h ago" if m < 1440 else f"{m // 1440} d ago"


async def news_items() -> list[dict]:
    cal = await load_news_calendar()
    now = int(time.time())
    out = []
    for e in sorted((e for e in cal["events"] if e.get("currency") in NEWS_CCYS and e.get("impact") in ("High", "Medium")),
                    key=lambda e: abs(e["time"] - now))[:40]:
        cur = e["currency"]
        high = e["impact"] == "High"
        lock = high and abs(e["time"] - now) <= 30 * 60
        asset = ", ".join(sym for sym in ASSETS if cur in sym or (cur == "USD" and sym == "XAU/USD"))
        out.append({
            "id": f"cal-{cur}-{e['time']}-{zlib.crc32(e['title'].encode()) % 100000}", "title": f"{cur} · {e['title']}", "titleAr": f"{cur} · {e['title']}",
            "source": cal["source"], "timeAgo": _ago(e["time"], now), "category": _category(e["title"]), "impactAsset": asset,
            "impactVerdict": "neutral", "impactHeadlineAr": "حدث اقتصادي عالي التأثير" if high else "حدث اقتصادي متوسط التأثير",
            "reasonAr": "خبر قوي: تقلب كبير ممكن 30 دقيقة قبل وبعد." if high else "تأثير متوسط على التقلب.",
            "reasonEn": "High impact: strong volatility possible 30 min before and after." if high else "Medium impact on volatility.",
            "importance": "HIGH" if high else "MEDIUM", "isLive": True,
            "publishedAt": datetime.fromtimestamp(e["time"], timezone.utc).isoformat(), "isLockoutEvent": lock,
            "lockoutReasonAr": "نافذة حظر الأخبار نشطة" if lock else None,
        })
    return out


@router.get("/news")
async def news():
    return {"news": await news_items(), "lastUpdated": datetime.now(timezone.utc).isoformat()}


@router.post("/news/sync")
async def news_sync():
    items = await news_items()
    return {"success": True, "news": items, "count": len(items)}
