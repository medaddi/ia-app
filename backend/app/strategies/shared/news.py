"""
Economic calendar filter.
Source: ForexFactory weekly calendar JSON (faireconomy mirror) merged with an optional local
file data/news_calendar.json ([{ "time": "2026-10-28T12:30:00Z", "currency": "USD", "title": "CPI m/m", "impact": "High" }]).
"""

import json
import time
from datetime import datetime
from pathlib import Path

import httpx

from ...config import settings


def _parse_iso(s: str):
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return None


def news_block(ts_sec: int, events: list[dict], rule: dict) -> dict:
    kws = [k.lower() for k in rule["keywords"]]
    relevant = [e for e in events if e.get("impact") == "High" and e.get("currency") in rule["currencies"]
                and (not kws or any(k in str(e.get("title", "")).lower() for k in kws))]
    hit = next((e for e in relevant if e["time"] - rule["minutesBefore"] * 60 <= ts_sec <= e["time"] + rule["minutesAfter"] * 60), None)
    upcoming = sorted((e for e in relevant if e["time"] > ts_sec), key=lambda e: e["time"])
    return {"blocked": hit is not None, "event": hit, "next": upcoming[0] if upcoming else None}


_cache: dict = {"events": [], "expires": 0.0, "source": "none"}


async def load_news_calendar() -> dict:
    if _cache["expires"] > time.time():
        return {"events": _cache["events"], "source": _cache["source"]}
    events: list[dict] = []
    sources: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
        if res.status_code == 200:
            data = res.json()
            for e in data if isinstance(data, list) else []:
                t = _parse_iso(e.get("date"))
                if t is None:
                    continue
                events.append({"time": t, "currency": str(e.get("country") or ""), "title": str(e.get("title") or ""), "impact": e.get("impact")})
            sources.append("ForexFactory calendar")
    except (httpx.HTTPError, ValueError):
        pass  # calendar unavailable: fall back to the local file
    try:
        local = Path(settings.data_dir) / "news_calendar.json"
        if local.exists():
            for e in json.loads(local.read_text("utf8")):
                t = _parse_iso(e.get("time"))
                if t is not None:
                    events.append({"time": t, "currency": e.get("currency"), "title": e.get("title"), "impact": e.get("impact") or "High"})
            sources.append("data/news_calendar.json")
    except (ValueError, OSError):
        pass  # malformed local file is ignored
    _cache.update(events=events, expires=time.time() + (60 if sources else 5) * 60, source=" + ".join(sources) or "none")
    return {"events": events, "source": _cache["source"]}
