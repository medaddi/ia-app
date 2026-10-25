"""Prices, candles, the economic calendar (as news) and a price-action sentiment gauge. XAU/USD and EUR/USD only."""

import asyncio
import time
import zlib
from datetime import datetime, timezone

from fastapi import APIRouter

from ..market.data import TIMEFRAME_SECONDS, fetch_candle_series, fetch_live_price, market_session_status
from ..strategies.exunu import run_exunu, to_ai_signal
from ..strategies.service import _cache as strategy_cache, normalize_symbol
from ..strategies.shared.news import load_news_calendar

router = APIRouter(prefix="/api")

ASSETS = {
    "XAU/USD": {"id": "xauusd", "name": "Spot Gold", "arabicName": "الذهب الفوري", "frenchName": "Or au comptant", "category": "commodities", "pipSize": 0.1, "decimalPlaces": 2},
    "EUR/USD": {"id": "eurusd", "name": "Euro / US Dollar", "arabicName": "اليورو / الدولار", "frenchName": "Euro / Dollar US", "category": "forex", "pipSize": 0.0001, "decimalPlaces": 5},
}


def _trend(sym: str) -> tuple[str, int]:
    """Trend from the strategy's own bias (cached result), never invented."""
    hit = strategy_cache.get(sym)
    if not hit:
        return "Sideways", 50
    r = hit[0]["result"]
    d = r["bias"]["direction"]
    return ("Bullish" if d == "BULLISH" else "Bearish" if d == "BEARISH" else "Sideways"), int(r["score"]) if r["setup"] else 50


async def assets_list() -> list[dict]:
    prices = await asyncio.gather(*(fetch_live_price(s) for s in ASSETS))
    out = []
    for (sym, meta), p in zip(ASSETS.items(), prices):
        trend, strength = _trend(sym)
        out.append({**meta, "symbol": sym, "price": p["price"], "change24h": p["change24h"], "change24hAmount": p["change24hAmount"],
                    "high24h": p["high24h"], "low24h": p["low24h"], "volume24h": "—", "trend": trend, "trendStrength": strength,
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


@router.get("/market/candles")
async def market_candles(symbol: str = "XAU/USD", timeframe: str = "15M", count: int = 600, force: bool = False):
    sym = normalize_symbol(symbol)
    series = await fetch_candle_series(sym, timeframe if timeframe in TIMEFRAME_SECONDS else "15M", min(max(count, 10), 2000), fresh=force)
    return {"symbol": sym, "timeframe": timeframe, "candles": [c.to_dict() for c in series["candles"]], "indicators": None,
            "isLiveFeed": not series["isSynthetic"], "source": series["source"]}


async def all_signals() -> list[dict]:
    results = await asyncio.gather(*(run_exunu(s) for s in ASSETS))
    return [to_ai_signal(r) for r in results]


@router.get("/signals")
async def signals():
    sigs = await all_signals()
    actionable = [s for s in sigs if s["isActionableNow"]]
    return {"signals": sigs, "actionableCount": len(actionable), "totalCount": len(sigs), "allowedCount": len(actionable),
            "waitCount": len(sigs) - len(actionable)}


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
    for e in sorted((e for e in cal["events"] if e.get("currency") in ("USD", "EUR") and e.get("impact") in ("High", "Medium")),
                    key=lambda e: abs(e["time"] - now))[:40]:
        cur = e["currency"]
        high = e["impact"] == "High"
        lock = high and abs(e["time"] - now) <= 30 * 60
        asset = "XAU/USD & EUR/USD" if cur == "USD" else "EUR/USD"
        out.append({
            "id": f"cal-{cur}-{e['time']}-{zlib.crc32(e['title'].encode()) % 100000}", "title": f"{cur} · {e['title']}", "titleAr": f"{cur} · {e['title']}",
            "source": cal["source"], "timeAgo": _ago(e["time"], now), "category": _category(e["title"]), "impactAsset": asset,
            "impactVerdict": "neutral", "impactHeadlineAr": "حدث اقتصادي عالي التأثير" if high else "حدث اقتصادي متوسط التأثير",
            "reasonAr": "الاستراتيجيات لا تفتح صفقات 30 دقيقة قبل وبعد الأخبار القوية." if high else "تأثير متوسط على التقلب.",
            "reasonEn": "The strategies open no trade 30 min before or after high-impact news." if high else "Medium impact on volatility.",
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


# ---------------------------------------------------------------- sentiment (price action, not social media)

async def sentiment_for(symbol: str) -> dict:
    sym = normalize_symbol(symbol)
    series = await fetch_candle_series(sym, "1H", 120)
    c = series["candles"][-48:]
    up = sum(1 for x in c if x.close > x.open)
    down = sum(1 for x in c if x.close < x.open)
    n = len(c) or 1
    pos, neg = round(up / n * 100), round(down / n * 100)
    neu = max(0, 100 - pos - neg)
    move = (c[-1].close - c[0].open) / c[0].open * 100 if len(c) > 1 else 0
    index = max(0, min(100, round(50 + move * (10 if sym == "XAU/USD" else 25))))
    label = "Greed" if index >= 60 else "Fear" if index <= 40 else "Neutral"
    split = {"positive": pos, "negative": neg, "neutral": neu}
    return {
        "assetSymbol": sym, **split,
        "sentimentSummaryAr": f"آخر 48 شمعة H1: {pos}% صاعدة و {neg}% هابطة، التغير {move:+.2f}%.",
        "sentimentSummary": f"Last 48 H1 candles: {pos}% up, {neg}% down, change {move:+.2f}%.",
        "sources": {"priceAction": split}, "fearAndGreedIndex": index, "fearAndGreedLabel": label,
        "method": "Share of bullish/bearish H1 candles over 48 hours (real candles, no social-media data)",
    }


@router.get("/sentiment")
async def sentiment(symbol: str = "XAU/USD"):
    return {"sentiment": await sentiment_for(symbol)}


@router.get("/market/sync-all")
async def sync_all(symbol: str = "XAU/USD", timeframe: str = "1H"):
    sym = normalize_symbol(symbol)
    assets, candles, sigs, items, sent = await asyncio.gather(assets_list(), market_candles(sym, timeframe, 300), all_signals(), news_items(), sentiment_for(sym))
    return {"success": True, "assets": assets, "selectedAsset": next(a for a in assets if a["symbol"] == sym),
            "candleData": candles, "signals": sigs, "news": items, "sentiment": sent, "updated": int(time.time() * 1000)}
