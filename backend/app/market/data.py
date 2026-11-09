"""
Live market data for XAU/USD and the forex pairs (EUR/USD, GBP/USD and the FXAlexG pairs).
- Live price: gold-api.com spot (gold), Yahoo GC=F / EURUSD=X as fallback.
- Candles: Yahoo Finance. Gold candles come from COMEX futures (GC=F) and are shifted by the live
  spot-futures basis so every candle is in spot terms. 4H is aggregated from 1H.
  If the provider fails, an empty series flagged `isSynthetic` is returned and the strategies
  refuse to analyse it.
"""

import asyncio
import calendar
import json
import math
import time
from datetime import datetime, timezone

import httpx

from . import oanda
from .pairs import CONVERSION_FEEDS, PAIRS
from .sanitize import merge, sanitize
from .jsnum import round_to
from .types import Candle

UA = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
PRICE_TTL = 1.0  # live price shared by every viewer: at most one provider request per symbol per second
RAW_TTL = 20.0
SLOW_TTL = 300.0
HOURLY_TTL = 60.0  # 2 years of 1h: re-downloaded at most once a minute (and right after each candle close)

TIMEFRAME_SECONDS = {"1M": 60, "5M": 300, "15M": 900, "30M": 1800, "1H": 3600, "4H": 14400, "1D": 86400, "1W": 604800}
INTERVALS = {"1M": ("1m", "5d"), "5M": ("5m", "60d"), "15M": ("15m", "60d"), "30M": ("30m", "60d"), "1H": ("1h", "2y"), "4H": ("1h", "2y"), "1D": ("1d", "5y"), "1W": ("1wk", "10y")}

_client: httpx.AsyncClient | None = None
_price_cache: dict[str, tuple[dict, float]] = {}
_raw_cache: dict[str, tuple[list[Candle], float]] = {}
_last_known: dict[str, dict] = {}
# Gold: the last real spot − futures gap (spot feed vs COMEX GC=F). When the spot feed is down, the futures price is put
# back in spot terms with it, so prices, candles and a trade's levels never jump by the gap between two views.
_gold_basis: list[float] = []
SPOT_SOURCE = "Interbank OTC Spot Feed (gold-api)"


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(headers=UA, timeout=8, follow_redirects=True)
    return _client


# Forex pairs served from Yahoo (the traded ones and the conversion feeds); gold has its own spot feed and a futures-to-spot basis
FX_TICKERS = {**{pair: ticker for pair, (_, ticker) in PAIRS.items()}, **CONVERSION_FEEDS}


def canonical(symbol: str) -> str:
    """'gbpusd', 'GBP/USD', 'GBPUSD' → 'GBP/USD'; 'EUR' → 'EUR/USD'; anything else that is not forex → 'XAU/USD'."""
    s = (symbol or "").upper().replace("/", "").replace(" ", "").replace("_", "").replace("-", "")
    for pair in FX_TICKERS:
        if pair.replace("/", "") in s:
            return pair
    # Bare currency ("EUR", "GBP"): first pair quoting it against USD, then any pair starting with it
    for pair in sorted(FX_TICKERS, key=lambda p: (p not in PAIRS, "USD" not in p)):
        if len(s) >= 3 and s[:3] == pair[:3] and pair[:3] != "USD":
            return pair
    return "XAU/USD"


def is_fx(symbol: str) -> bool:
    return canonical(symbol) in FX_TICKERS


def market_session_status(symbol: str = "XAU/USD", now: datetime | None = None) -> dict:
    """Forex / spot gold hours: Sunday 22:00 UTC to Friday 21:00 UTC (daily 21:00–22:00 rollover stays open)."""
    d = now or datetime.now(timezone.utc)
    dow = (d.weekday() + 1) % 7  # Sunday = 0
    h = d.hour
    if (dow == 5 and h >= 21) or dow == 6 or (dow == 0 and h < 22):
        return {"isOpen": False, "labelEn": "MARKET CLOSED · WEEKEND", "labelFr": "Marché fermé (week-end)",
                "labelAr": "السوق مغلق (عطلة نهاية الأسبوع)", "sessionStage": "WEEKEND_CLOSED", "nextOpen": "Sunday 22:00 GMT"}
    if h == 21 and 1 <= dow <= 4:
        return {"isOpen": True, "labelEn": "DAILY ROLLOVER WINDOW", "labelFr": "Rollover quotidien", "labelAr": "فترة التسوية اليومية", "sessionStage": "CME_ROLLOVER"}
    m = h * 60 + d.minute
    stage = "ASIAN_RANGE" if m < 8 * 60 else "LONDON_PREP" if m < 14 * 60 else "NY_SILVER_BULLET" if m <= 15 * 60 else "NY_AFTERNOON"
    label = f"{canonical(symbol)} · INTERBANK FOREX" if is_fx(symbol) else "XAU/USD · SPOT GOLD"
    return {"isOpen": True, "labelEn": label, "labelFr": label, "labelAr": label, "sessionStage": stage}


def _price_result(symbol: str, price: float, chg_pct: float, high: float, low: float, source: str, quote_time: int | None = None) -> dict:
    s = market_session_status(symbol)
    dec = 5 if is_fx(symbol) else 2
    return {
        "symbol": symbol, "price": price, "change24h": chg_pct, "change24hAmount": round_to(price * chg_pct / 100, dec),
        "high24h": high, "low24h": low, "source": source, "lastUpdated": int(time.time() * 1000),
        # when the provider itself last priced it (free feeds: forex every ~10–60 s, gold spot every ~30 s)
        "quoteTime": int(quote_time) if quote_time else int(time.time()),
        "isMarketOpen": s["isOpen"], "marketStatusLabel": s["labelEn"], "nextOpen": s.get("nextOpen"), "sessionStage": s["sessionStage"],
    }


async def _yahoo_meta(ticker: str) -> dict | None:
    try:
        r = await client().get(f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}", params={"interval": "1m", "range": "1d"}, timeout=3.5)
        if r.status_code != 200:
            return None
        return ((r.json().get("chart") or {}).get("result") or [{}])[0].get("meta")
    except (httpx.HTTPError, ValueError, IndexError):
        return None


_spark: tuple[dict, float] = ({}, 0.0)
_spark_lock: asyncio.Lock | None = None


async def _spark_quotes() -> dict:
    """Every forex pair's last price in ONE Yahoo request, refreshed at most once per second for all viewers."""
    global _spark, _spark_lock
    if _spark[1] > time.time():
        return _spark[0]
    if _spark_lock is None:
        _spark_lock = asyncio.Lock()
    async with _spark_lock:
        if _spark[1] > time.time():
            return _spark[0]
        out: dict = {}
        try:
            r = await client().get("https://query1.finance.yahoo.com/v8/finance/spark",
                                   params={"symbols": ",".join(FX_TICKERS.values()), "range": "1d", "interval": "1m"}, timeout=3.5)
            if r.status_code == 200:
                for ticker, v in r.json().items():
                    closes = [c for c in (v.get("close") or []) if isinstance(c, (int, float))]
                    if closes:
                        stamps = [t for t, x in zip(v.get("timestamp") or [], v.get("close") or []) if isinstance(x, (int, float))]
                        out[ticker] = {"price": float(closes[-1]), "prev": float(v.get("previousClose") or v.get("chartPreviousClose") or 0),
                                       "high": float(max(closes)), "low": float(min(closes)), "time": stamps[-1] if stamps else None}
        except (httpx.HTTPError, ValueError, AttributeError):
            pass
        # A failed batch is retried after 1 s; meanwhile each symbol falls back to its own request
        _spark = (out, time.time() + PRICE_TTL)
        return out


async def fetch_live_price(symbol: str = "XAU/USD", fresh: bool = False) -> dict:
    sym = canonical(symbol)
    hit = _price_cache.get(sym)
    if not fresh and hit and hit[1] > time.time():
        return hit[0]
    result = None
    if oanda.enabled() and sym in oanda.INSTRUMENTS:  # the primary feed: OANDA mid price and its live spread
        q = await oanda.price(sym, 5 if sym in FX_TICKERS else 2)
        if q and q["price"] > 0:
            result = {**_price_result(sym, q["price"], 0.0, q["price"], q["price"], oanda.SOURCE, q["time"]), "spread": q["spread"]}
            prev = _last_known.get(sym)
            if prev and prev.get("source") == oanda.SOURCE:  # the day's change / range stay those of the last full quote
                result.update(change24h=prev.get("change24h", 0.0), high24h=max(prev.get("high24h") or 0, q["price"]), low24h=min(prev.get("low24h") or q["price"], q["price"]))
    if sym == "XAU/USD":
        try:
            r = await client().get("https://api.gold-api.com/price/XAU", timeout=3.5)
            if r.status_code == 200:
                d = r.json()
                p = float(d.get("price") or 0)
                if 2000 < p < 8000:
                    chg = float(d.get("chgp") or d.get("changePercent") or 0)
                    price = round_to(p, 2)
                    qt = None
                    try:
                        qt = calendar.timegm(time.strptime(str(d.get("updatedAt"))[:19], "%Y-%m-%dT%H:%M:%S"))
                    except (ValueError, TypeError):
                        pass
                    result = _price_result(sym, price, chg, round_to(price + 14.5, 2), round_to(price - 12, 2), SPOT_SOURCE, qt)
        except (httpx.HTTPError, ValueError, TypeError):
            pass
    if result is None and sym in FX_TICKERS:
        q = (await _spark_quotes()).get(FX_TICKERS[sym])
        if q and 0.3 < q["price"] < 3.0:
            price = round_to(q["price"], 5)
            result = _price_result(sym, price, round_to((q["price"] - q["prev"]) / q["prev"] * 100, 2) if q["prev"] else 0,
                                   q["high"], q["low"], f"Interbank Forex {FX_TICKERS[sym]}", q.get("time"))
    if result is None:
        fx = sym in FX_TICKERS
        meta = await _yahoo_meta(FX_TICKERS[sym] if fx else "GC=F")
        p = float((meta or {}).get("regularMarketPrice") or 0)
        ok = 0.3 < p < 3.0 if fx else 2000 < p < 8000
        if ok:
            prev = float(meta.get("previousClose") or meta.get("chartPreviousClose") or p) or p
            dec = 5 if fx else 2
            if not fx and not _gold_basis and _last_known.get(sym, {}).get("source") == SPOT_SOURCE:
                return {**_last_known[sym], "lastUpdated": int(time.time() * 1000)}  # no gap known yet: the last real spot
            adj = 0.0 if fx else (_gold_basis[0] if _gold_basis else 0.0)  # gold futures back in spot terms
            price = round_to(p + adj, dec)
            result = _price_result(sym, price, round_to((p - prev) / prev * 100, 2),
                                   round_to(float(meta.get("regularMarketDayHigh") or p) + adj, dec), round_to(float(meta.get("regularMarketDayLow") or p) + adj, dec),
                                   f"Interbank Forex {FX_TICKERS[sym]}" if fx else f"COMEX GC=F adjusted to spot ({adj:+g})", meta.get("regularMarketTime"))
    if result is None:
        last = _last_known.get(sym)
        if last:
            s = market_session_status(sym)
            return {**last, "lastUpdated": int(time.time() * 1000), "isMarketOpen": s["isOpen"], "marketStatusLabel": s["labelEn"],
                    "sessionStage": s["sessionStage"], "source": last["source"] + " (last known)"}
        return _price_result(sym, 0, 0, 0, 0, "unavailable")
    _last_known[sym] = result
    _price_cache[sym] = (result, time.time() + PRICE_TTL)
    return result


def _parse_chart(body: bytes, decimals: int) -> list[Candle]:
    res = ((json.loads(body).get("chart") or {}).get("result") or [None])[0] or {}
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    o, h, lo, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
    out: list[Candle] = []
    for i, t in enumerate(ts):
        vals = [arr[i] if i < len(arr) else None for arr in (o, h, lo, c)]
        if all(isinstance(x, (int, float)) and not math.isnan(x) for x in vals):
            out.append(Candle(int(t), *(round_to(x, decimals) for x in vals), (v[i] if i < len(v) else 0) or 0))
    return out


async def _yahoo_candles(ticker: str, interval: str, rng: str, decimals: int, fresh: bool) -> list[Candle]:
    key = f"{ticker}|{interval}|{rng}"
    hit = _raw_cache.get(key)
    if not fresh and hit and hit[1] > time.time():
        return hit[0]
    try:
        r = await client().get(f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}", params={"interval": interval, "range": rng})
        r.raise_for_status()
        out = await asyncio.to_thread(_parse_chart, r.content, decimals)  # 2 years of 1h = 12k rows: off the event loop
        if not out:
            raise ValueError("empty series")
    except (httpx.HTTPError, ValueError) as err:
        if hit:  # provider hiccup: keep serving the last good series (a few minutes old at most) instead of failing
            print(f"[market] {ticker} {interval}: {err!r}, using the last good series")
            _raw_cache[key] = (hit[0], time.time() + RAW_TTL)
            return hit[0]
        raise
    # Intraday series refresh every 20s; hourly/daily history changes slowly
    _raw_cache[key] = (out, time.time() + (RAW_TTL if interval not in ("1h", "1d", "1wk") else HOURLY_TTL if interval == "1h" else SLOW_TTL))
    return out


def aggregate(candles: list[Candle], bucket_sec: int) -> list[Candle]:
    out: list[Candle] = []
    for c in candles:
        t = c.time - (c.time % bucket_sec)
        if out and out[-1].time == t:
            last = out[-1]
            last.high = max(last.high, c.high)
            last.low = min(last.low, c.low)
            last.close = c.close
            last.volume = (last.volume or 0) + (c.volume or 0)
        else:
            out.append(Candle(t, c.open, c.high, c.low, c.close, c.volume))
    return out


def _integrity(rep: dict) -> dict:
    """The sanitizer's report in the series: counts, the last missing slots, continuity."""
    return {"bars": rep["bars"], "missing": len(rep["missing"]), "missingRecent": rep["missing"][-12:], "artifacts": rep["artifacts"][-12:],
            "offGrid": rep["offGrid"], "duplicates": rep["duplicates"], "continuity": round(rep["continuity"], 5)}


async def _oanda_series(sym: str, timeframe: str, limit: int, decimals: int, step: int) -> dict:
    """OANDA mid candles, sanitized; missing slots in the window are backfilled once by a from / to request."""
    raw = await oanda.candles(sym, timeframe, limit, decimals)
    clean, rep = sanitize(raw, step)
    filled = 0
    if rep["missing"] and len(rep["missing"]) <= 300:
        try:
            extra = await oanda.candles(sym, timeframe, 0, decimals, frm=rep["missing"][0] - step, to=rep["missing"][-1] + 2 * step, ttl=60.0)
            before = len(clean)
            clean, rep = sanitize(merge(clean, extra), step)
            filled = len(clean) - before
        except RuntimeError:
            pass
    spread = next((c.spread for c in reversed(clean) if c.spread), 0.0)
    return {"candles": clean[-limit:], "isSynthetic": False, "basis": 0, "fetchedAt": int(time.time() * 1000), "source": oanda.SOURCE,
            "spread": spread, "integrity": {**_integrity(rep), "backfilled": filled}}


async def fetch_candle_series(symbol: str = "XAU/USD", timeframe: str = "15M", limit: int = 600, live_price: float | None = None, fresh: bool = False) -> dict:
    sym = canonical(symbol)
    euro = sym in FX_TICKERS  # any forex pair (no futures basis)
    decimals = 5 if euro else 2
    step = TIMEFRAME_SECONDS.get(timeframe, 900)
    if oanda.enabled() and sym in oanda.INSTRUMENTS and timeframe in oanda.GRANULARITY:
        try:
            return await _oanda_series(sym, timeframe, limit, decimals, step)
        except RuntimeError as err:
            print(f"[market] {err}: Yahoo serves instead")
    spot = live_price if live_price and live_price > 0 else (await fetch_live_price(symbol))["price"]
    interval, rng = INTERVALS.get(timeframe, INTERVALS["15M"])
    ticker = FX_TICKERS[sym] if euro else "GC=F"
    try:
        candles = await _yahoo_candles(ticker, interval, rng, decimals, fresh)
        # Reshaping thousands of candles is CPU work: off the event loop so other requests keep flowing
        if timeframe == "4H":
            candles = await asyncio.to_thread(aggregate, candles, 14400)
        elif step < 86400 and any(c.time % step for c in candles[-3:]):
            # Yahoo stamps the forming intraday candle with the current time (e.g. 00:28:45): put it back on its slot
            candles = await asyncio.to_thread(aggregate, candles, step)
        if len(candles) > 15:
            candles = [Candle(c.time, c.open, c.high, c.low, c.close, c.volume) for c in candles[-limit:]]
            candles, rep = sanitize(candles, step) if step < 86400 else (candles, None)  # UTC grid, duplicates, bad ticks, gaps
            # Daily / weekly: Yahoo can add the live point as an extra bar stamped with the current time (e.g. Friday 21:29
            # after this week's Monday bar): fold it into the bar of its period instead of drawing a second candle
            if step >= 86400 and len(candles) > 1 and (candles[-1].time - candles[-2].time) % step:
                prev, tick = candles[-2], candles[-1]
                if tick.time - prev.time < step - 7200:  # same period (2 h tolerance for the DST shift of the open)
                    prev.high, prev.low, prev.close = max(prev.high, tick.high), min(prev.low, tick.low), tick.close
                    candles.pop()
            last = candles[-1]
            # Spot-futures basis (gold only). Ignore implausible gaps (stale spot feed, contract roll day).
            basis = 0.0
            if not euro:
                # The gap is measured only against the real spot feed; otherwise the last measured one is reused
                live = await fetch_live_price(symbol)
                if live.get("source") == SPOT_SOURCE and live.get("price"):
                    raw = live["price"] - last.close
                    if abs(raw) / live["price"] < 0.02:
                        basis = round_to(raw, 2)
                        _gold_basis[:] = [basis]
                elif _gold_basis:
                    basis = _gold_basis[0]
            if basis:
                for c in candles:
                    c.open, c.high, c.low, c.close = (round_to(x + basis, decimals) for x in (c.open, c.high, c.low, c.close))
            # Live tick only touches the candle that is still forming
            now = int(time.time())
            if spot and market_session_status(symbol)["isOpen"]:
                bucket = now - now % step
                tail = candles[-1]
                if step >= 86400:
                    # Daily / weekly bars follow the provider's own session start: only update the bar in progress
                    if tail.time <= now < tail.time + step:
                        tail.close = round_to(spot, decimals)
                        tail.high = max(tail.high, tail.close)
                        tail.low = min(tail.low, tail.close)
                elif tail.time == bucket:
                    tail.close = round_to(spot, decimals)
                    tail.high = max(tail.high, tail.close)
                    tail.low = min(tail.low, tail.close)
                elif tail.time < bucket and now - bucket < step:
                    candles.append(Candle(bucket, tail.close, max(tail.close, spot), min(tail.close, spot), round_to(spot, decimals), 0))
            sign = "+" if basis >= 0 else ""
            return {"candles": candles, "isSynthetic": False, "basis": basis, "fetchedAt": int(time.time() * 1000), "spread": 0.0,
                    **({"integrity": _integrity(rep)} if rep else {}),
                    "source": f"Yahoo Finance {ticker}" if euro else f"COMEX GC=F adjusted to spot (basis {sign}{basis:g})"}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as err:
        print(f"[market] candle feed unavailable for {symbol} {timeframe}: {err}")
    return {"candles": [], "isSynthetic": True, "basis": 0, "fetchedAt": int(time.time() * 1000), "source": "Live feed unavailable"}


async def fetch_many(symbol: str, timeframes: list[str], limits: dict, live_price: float | None, fresh_tf: str | None = None) -> list[dict]:
    return await asyncio.gather(*(fetch_candle_series(symbol, tf, limits.get(tf, 1000), live_price, fresh=(tf == fresh_tf)) for tf in timeframes))
