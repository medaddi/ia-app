"""
OANDA v20 REST (the user's choice of primary feed, 2026-11-09): mid-price candles with the bid / ask spread and real
tick volume, up to 5,000 per request, aligned to UTC (H4 at 00 / 04 / 08 … UTC, days at 00:00 UTC).

On only when OANDA_API_TOKEN is set in the environment (a practice token unless OANDA_ENV=live). Without it, or when a
request fails, the app keeps the Yahoo feed (market/data.py). The token never leaves the server.
"""

import os
import time
from datetime import datetime, timezone

import httpx

from .types import Candle

INSTRUMENTS = {"XAU/USD": "XAU_USD", "EUR/USD": "EUR_USD", "GBP/USD": "GBP_USD", "EUR/CHF": "EUR_CHF", "AUD/CAD": "AUD_CAD",
               "AUD/CHF": "AUD_CHF", "USD/CAD": "USD_CAD", "USD/CHF": "USD_CHF", "AUD/USD": "AUD_USD"}
GRANULARITY = {"1M": "M1", "5M": "M5", "15M": "M15", "30M": "M30", "1H": "H1", "4H": "H4", "1D": "D", "1W": "W"}
MAX_COUNT = 5000
SOURCE = "OANDA v20 (mid, bid/ask spread)"

_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[list[Candle], float]] = {}
_fail_until = 0.0  # after a failure, Yahoo serves for 60 s before OANDA is tried again


def enabled() -> bool:
    return bool(os.environ.get("OANDA_API_TOKEN")) and time.time() >= _fail_until


def _base() -> str:
    return "https://api-fxtrade.oanda.com" if os.environ.get("OANDA_ENV", "practice").lower() == "live" else "https://api-fxpractice.oanda.com"


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=8)
    return _client


def _ts(s: str) -> int:
    # "2026-11-09T13:05:00.000000000Z" -> unix seconds
    return int(datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def parse(body: dict, decimals: int) -> list[Candle]:
    out = []
    for x in body.get("candles") or []:
        m, b, a = x.get("mid"), x.get("bid"), x.get("ask")
        if not m:
            continue
        sp = float(a["c"]) - float(b["c"]) if a and b else 0.0
        out.append(Candle(_ts(x["time"]), round(float(m["o"]), decimals), round(float(m["h"]), decimals), round(float(m["l"]), decimals),
                          round(float(m["c"]), decimals), float(x.get("volume") or 0), round(sp, decimals + 1)))
    return out


async def candles(symbol: str, timeframe: str, count: int, decimals: int, frm: int | None = None, to: int | None = None,
                  ttl: float = 5.0) -> list[Candle]:
    """Mid candles from OANDA (the forming one included). Raises on any failure (the caller falls back)."""
    global _fail_until
    inst, gran = INSTRUMENTS[symbol], GRANULARITY[timeframe]
    key = f"{inst}|{gran}|{count}|{frm}|{to}"
    hit = _cache.get(key)
    if hit and hit[1] > time.time():
        return hit[0]
    params: dict = {"granularity": gran, "price": "MBA", "alignmentTimezone": "UTC", "dailyAlignment": 0, "weeklyAlignment": "Monday"}
    if frm is not None:
        params["from"] = frm
        params["to"] = to or int(time.time())
    else:
        params["count"] = min(max(count, 1), MAX_COUNT)
    try:
        r = await _http().get(f"{_base()}/v3/instruments/{inst}/candles", params=params,
                              headers={"Authorization": f"Bearer {os.environ['OANDA_API_TOKEN']}", "Accept-Datetime-Format": "RFC3339"})
        r.raise_for_status()
        out = parse(r.json(), decimals)
        if not out:
            raise ValueError("no candles")
    except (httpx.HTTPError, ValueError, KeyError) as err:
        _fail_until = time.time() + 60
        raise RuntimeError(f"OANDA {inst} {gran}: {err!r}") from None
    _cache[key] = (out, time.time() + ttl)
    return out


async def price(symbol: str, decimals: int) -> dict | None:
    """The forming M1 candle's mid close and its bid / ask spread (cached 1 s)."""
    try:
        c = await candles(symbol, "1M", 1, decimals, ttl=1.0)
        s5 = c[-1]
        return {"price": s5.close, "spread": s5.spread, "time": s5.time}
    except RuntimeError:
        return None
