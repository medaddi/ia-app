"""
Pictures for Telegram, drawn with Pillow in the app's dark and gold look (no browser needed):
- chart: the pair on 15-minute candles with the setup drawn on it (the strategy's own levels and zones, the signal arrow,
  the trade's entry / stop / target zones) and a side panel: the plan and why the strategy took the trade (its rules,
  ticked), or what it waits for when there is no trade;
- trade card: the running trade like the app's card (price now, R, the stop → entry → target bar, what to do now).
"""

import io
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..market.data import fetch_candle_series
from ..strategies.service import STRATEGY_DEFS, get_strategy_result, normalize_symbol
from ..strategies.shared.types import Candle

BG, PANEL, LINE, GRID = (7, 9, 13), (14, 17, 24), (36, 41, 54), (255, 255, 255, 13)
TEXT, MUTED, DIM = (236, 240, 245), (148, 158, 175), (98, 106, 122)
BULL, BEAR, GOLD, GOLD_LIGHT = (22, 199, 132), (234, 57, 67), (201, 160, 74), (239, 217, 154)
COLOR = {"bull": BULL, "bear": BEAR, "entry": GOLD_LIGHT, "liquidity": GOLD, "muted": (120, 128, 145)}
LIVE = ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")
M15 = 900


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


GLYPHS = {"σ": "sd", "×": "x", "–": "-", "—": "-", "≥": ">=", "≤": "<=", "→": "->", "±": "+/-", "·": "·"}


def _clean(text: str) -> str:
    """The font has no σ, ×, –, ≥…: plain equivalents instead of empty boxes."""
    return "".join(GLYPHS.get(ch, ch) for ch in str(text))


def _wrap(d: ImageDraw.ImageDraw, text: str, size: int, width: float, max_lines: int = 3) -> list[str]:
    words, lines, cur = _clean(text).split(), [], ""
    for w in words:
        nxt = f"{cur} {w}".strip()
        if d.textlength(nxt, font=_font(size)) <= width:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;") + "…"
    return lines


def _tick(d: ImageDraw.ImageDraw, x: float, y: float, ok: bool) -> None:
    """A small round ✓ (green) or ✕ (red): drawn, not a font glyph."""
    col = BULL if ok else BEAR
    ink = (8, 22, 16) if ok else (255, 235, 238)
    d.ellipse((x, y, x + 16, y + 16), fill=col)
    if ok:
        d.line((x + 4, y + 8.5, x + 7, y + 11.5, x + 12.5, y + 5), fill=ink, width=2)
    else:
        d.line((x + 5, y + 5, x + 11, y + 11), fill=ink, width=2)
        d.line((x + 11, y + 5, x + 5, y + 11), fill=ink, width=2)


def _glow(img: Image.Image) -> Image.Image:
    g = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse((img.width * 0.6, -240, img.width + 200, 200), fill=(201, 160, 74, 30))
    return Image.alpha_composite(img, g.filter(ImageFilter.GaussianBlur(110)))


def _running(r: dict) -> Optional[dict]:
    s = r.get("setup")
    return s if s and s["lifecycle"]["state"] in LIVE and r["status"] in ("SIGNAL", "WATCH") else None


# ---------------------------------------------------------------- the chart with the setup

def render_chart(candles: list[Candle], r: dict, now: Optional[float] = None) -> bytes:
    W, H = 1280, 760
    CX0, CX1, CY0, CY1 = 26, 880, 132, 700  # chart area; the panel sits on the right
    PX0 = 930
    d = r["spec"]["decimals"]
    f = lambda v: f"{v:.{d}f}"  # noqa: E731
    s = r.get("setup")
    trade = _running(r)
    price = r.get("price") or candles[-1].close

    # The window: about 30 hours of M15, longer when the trade's signal is older (the arrow stays on the picture)
    n = 120
    if s:
        since = sum(1 for c in candles if c.time >= s["signalTime"] - M15 * 8)
        n = max(n, min(len(candles), since + 12))
    c = candles[-n:]
    t0, t1 = c[0].time, c[-1].time + M15
    lo, hi = min(x.low for x in c), max(x.high for x in c)
    if trade:
        lo, hi = min(lo, trade["sl"], trade["tp3"]), max(hi, trade["sl"], trade["tp3"])
    span = hi - lo or 1
    lo, hi = lo - span * 0.07, hi + span * 0.07
    step = (CX1 - CX0) / (len(c) + 4)
    X = lambda t: CX0 + (t - t0) / M15 * step  # noqa: E731
    Y = lambda v: CY1 - (v - lo) / (hi - lo) * (CY1 - CY0)  # noqa: E731
    inside = lambda v: lo <= v <= hi  # noqa: E731

    img = _glow(Image.new("RGBA", (W, H), BG + (255,)))
    zones = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    z = ImageDraw.Draw(zones)
    for k in range(7):  # grid
        yy = CY0 + (CY1 - CY0) * k / 6
        z.line((CX0, yy, CX1, yy), fill=GRID, width=1)

    # The strategy's zones (areas of interest) and the trade's target / stop zones
    for dr in r.get("drawings") or []:
        if dr["kind"] == "box" and dr["layer"] != "trade" and dr.get("p2") is not None and (inside(dr["p1"]) or inside(dr["p2"])):
            col = COLOR.get(dr.get("color"), GOLD)
            a, b = sorted((Y(dr["p1"]), Y(dr["p2"])))
            z.rectangle((min(max(CX0, X(dr["t1"])), CX1 - 4), a, CX1, max(b, a + 2)), fill=col + (26,), outline=col + (90,))
    if trade:
        sx = min(max(CX0, X(trade["signalTime"])), CX1 - 4)  # kept inside the chart
        z.rectangle((sx, min(Y(trade["entry"]), Y(trade["tp3"])), CX1, max(Y(trade["entry"]), Y(trade["tp3"]))), fill=BULL + (32,))
        z.rectangle((sx, min(Y(trade["entry"]), Y(trade["sl"])), CX1, max(Y(trade["entry"]), Y(trade["sl"]))), fill=BEAR + (32,))
    img = Image.alpha_composite(img, zones)
    g = ImageDraw.Draw(img)

    # Candles
    body = max(2.0, step * 0.6)
    for x in c:
        cx = X(x.time) + step / 2
        col = BULL if x.close >= x.open else BEAR
        g.line((cx, Y(x.high), cx, Y(x.low)), fill=col, width=1)
        top, bot = Y(max(x.open, x.close)), Y(min(x.open, x.close))
        g.rectangle((cx - body / 2, top, cx + body / 2, max(bot, top + 1)), fill=col)

    # The strategy's levels and markers (why it acted), each named
    labels: list[tuple[float, str, tuple]] = []
    for dr in r.get("drawings") or []:
        if dr["layer"] == "trade":
            continue
        col = COLOR.get(dr.get("color"), MUTED)
        if dr["kind"] == "hline" and inside(dr["p1"]):
            yy = Y(dr["p1"])
            x_from = max(CX0, X(dr["t1"]))
            x_to = CX1 if not dr.get("t2") else min(CX1, X(dr["t2"]) + step)
            if x_to - x_from < 30:  # a level that only starts at the right edge says nothing
                continue
            dash = 8 if dr.get("style") in ("dashed", "dotted") else 0
            if dash:
                xx = x_from
                while xx < x_to:
                    g.line((xx, yy, min(xx + dash, x_to), yy), fill=col, width=2 if dr["layer"] == "structure" else 1)
                    xx += dash * 1.7
            else:
                g.line((x_from, yy, x_to, yy), fill=col, width=2 if dr["layer"] == "structure" else 1)
            if dr.get("text"):
                labels.append((yy, _clean(dr["text"]), col))
        elif dr["kind"] == "box" and dr.get("text") and dr.get("p2") is not None and (inside(dr["p1"]) or inside(dr["p2"])):
            labels.append((min(Y(dr["p1"]), Y(dr["p2"])) + 2, _clean(dr["text"]), col))
        elif dr["kind"] == "marker" and t0 <= dr["t1"] <= t1 and inside(dr["p1"]):
            mx, my = X(dr["t1"]) + step / 2, Y(dr["p1"])
            up = dr.get("position") == "below"
            g.polygon([(mx, my + (8 if up else -8)), (mx - 6, my + (18 if up else -18)), (mx + 6, my + (18 if up else -18))], fill=col)
            if dr.get("text"):
                g.text((mx, my + (28 if up else -28)), _clean(dr["text"]), font=_font(13), fill=col, anchor="mm")
    placed: list[float] = []
    for yy, text, col in sorted(labels):  # level names at the left, never on top of each other
        if any(abs(yy - p) < 16 for p in placed):
            continue
        placed.append(yy)
        tw = g.textlength(text, font=_font(13)) + 10
        g.rounded_rectangle((CX0 + 4, yy - 17, CX0 + 4 + tw, yy - 2), radius=4, fill=(10, 12, 17, 230))
        g.text((CX0 + 9, yy - 9.5), text, font=_font(13), fill=col, anchor="lm")

    # The signal arrow on the candle that triggered the trade
    if s and t0 <= s["signalTime"] - 1 <= t1:
        sig = max((x for x in c if x.time < s["signalTime"]), key=lambda x: x.time, default=None)
        if sig:
            buy = s["direction"] == "BUY"
            ax = X(sig.time) + step / 2
            ay = Y(sig.low) + 10 if buy else Y(sig.high) - 10
            col = BULL if buy else BEAR
            tip, base = (ay, ay + 16) if buy else (ay, ay - 16)
            g.polygon([(ax, tip), (ax - 9, base), (ax + 9, base)], fill=col)
            g.text((ax, base + (12 if buy else -12)), s["direction"], font=_font(14), fill=col, anchor="mm")

    # Price axis: the trade's levels and the price now, spread apart
    for k in range(7):
        v = lo + (hi - lo) * k / 6
        g.text((CX1 + 8, Y(v)), f(v), font=_font(12), fill=DIM, anchor="lm")
    badges = [(price, "", GOLD, True)]
    if trade:
        badges += [(trade["tp3"], "TP", BULL, True), (trade["sl"], "SL", BEAR, False), (trade["entry"], "ENTRY", GOLD_LIGHT, True)]
    last = None
    for v, label, col, dark in sorted(badges, key=lambda b: Y(b[0])):
        yy = Y(v)
        g.line((CX0, yy, CX1, yy), fill=col, width=1)
        by = yy if last is None else max(yy, last + 22)
        last = by
        txt = f"{label} {f(v)}" if label else f(v)
        tw = g.textlength(txt, font=_font(12)) + 10
        g.rounded_rectangle((CX1 - tw - 2, by - 10, CX1 - 2, by + 10), radius=4, fill=col)
        g.text((CX1 - tw + 3, by), txt, font=_font(12), fill=(10, 12, 16) if dark else (255, 255, 255), anchor="lm")

    # Header
    name = r["displaySymbol"]
    g.text((CX0, 28), name, font=_font(34), fill=(255, 255, 255))
    nw = g.textlength(name, font=_font(34))
    g.rounded_rectangle((CX0 + nw + 14, 33, CX0 + nw + 66, 61), radius=7, outline=LINE, width=1)
    g.text((CX0 + nw + 40, 47), "M15", font=_font(15), fill=GOLD_LIGHT, anchor="mm")
    g.text((CX0, 80), f"{f(price)}   ·   {_clean(r['strategyName'].split('·')[-1].strip())}", font=_font(17), fill=MUTED)
    g.text((CX0, 108), f"{time.strftime('%d %b %H:%M', time.gmtime(c[0].time))} - {time.strftime('%d %b %H:%M', time.gmtime(c[-1].time + M15))} UTC",
           font=_font(13), fill=DIM)

    # ---------------- the setup panel
    g.rounded_rectangle((PX0, 26, W - 26, H - 26), radius=18, fill=PANEL, outline=LINE, width=1)
    px, pw, py = PX0 + 22, W - 26 - PX0 - 44, 46
    if trade or s:
        st = trade or s
        buy = st["direction"] == "BUY"
        tag = f"{'BUY' if buy else 'SELL'} · {str(st.get('setup', '')).replace('_', ' ').title()}"
        tw = g.textlength(tag, font=_font(17)) + 26
        g.rounded_rectangle((px, py, px + tw, py + 32), radius=9, fill=BULL if buy else BEAR)
        g.text((px + tw / 2, py + 16), tag, font=_font(17), fill=(255, 255, 255), anchor="mm")
        state = {"PENDING": "WAITING", "OPEN": "RUNNING", "TP1_HIT": "RUNNING", "TP2_HIT": "RUNNING"}.get(st["lifecycle"]["state"], st["lifecycle"]["state"])
        g.text((W - 48, py + 16), state if trade else "CLOSED", font=_font(14), fill=GOLD_LIGHT if trade else DIM, anchor="rm")
        py += 52
        risk = abs(st["entry"] - st["sl"]) or 1
        rr = abs(st["tp3"] - st["entry"]) / risk
        pip = r["spec"].get("pipSize") or (0.1 if d == 2 else 0.0001)
        dist = (f"${risk:.2f}" if d == 2 else f"{risk / pip:.1f} pips")
        rows = [("Entry", f(st["entry"]), GOLD_LIGHT, st.get("entryType", "").title()), ("Stop", f(st["sl"]), BEAR, dist),
                ("Target", f(st["tp3"]), BULL, f"1:{rr:.1f}")]
        for label, val, col, note in rows:
            g.text((px, py), label.upper(), font=_font(12), fill=DIM)
            g.text((px, py + 16), val, font=_font(22), fill=col)
            g.text((W - 48, py + 26), note, font=_font(14), fill=MUTED, anchor="rm")
            py += 52
        if trade:
            r_now = (price - st["entry"]) * (1 if buy else -1) / risk
            g.text((px, py), "NOW", font=_font(12), fill=DIM)
            g.text((px, py + 16), f"{r_now:+.2f}R", font=_font(22), fill=BULL if r_now >= 0 else BEAR)
            py += 50
        g.line((px, py, W - 48, py), fill=LINE, width=1)
        py += 16
        g.text((px, py), "WHY THIS TRADE", font=_font(13), fill=GOLD)
        py += 26
        checks = [ck for ck in r.get("checklist") or [] if ck["passed"]]
    else:
        g.rounded_rectangle((px, py, px + 120, py + 32), radius=9, outline=LINE, width=1)
        g.text((px + 60, py + 16), "NO TRADE", font=_font(15), fill=MUTED, anchor="mm")
        py += 52
        g.text((px, py), "WAITING FOR", font=_font(13), fill=GOLD)
        py += 24
        for ln in _wrap(g, r.get("headline") or "", 15, pw, 4):
            g.text((px, py), ln, font=_font(15), fill=TEXT)
            py += 21
        py += 12
        g.line((px, py, W - 48, py), fill=LINE, width=1)
        py += 16
        g.text((px, py), "THE STRATEGY'S RULES", font=_font(13), fill=GOLD)
        py += 26
        checks = list(r.get("checklist") or [])
    for ck in checks:
        lines = _wrap(g, ck["rule"], 14, pw - 28, 2)
        if py + 20 * len(lines) > H - 60:
            break
        _tick(g, px, py + 1, ck["passed"])
        for k, ln in enumerate(lines):
            g.text((px + 26, py + k * 18), ln, font=_font(14), fill=TEXT if ck["passed"] else MUTED)
        py += 18 * len(lines) + 10

    brand = "Liquidity "
    bw = g.textlength(brand, font=_font(16))
    g.text((px, H - 50), brand, font=_font(16), fill=(255, 255, 255), anchor="lm")
    g.text((px + bw, H - 50), "Dissection", font=_font(16), fill=GOLD_LIGHT, anchor="lm")

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------- the trade card (follow-up)

def render_card(r: dict, manager: Optional[dict] = None) -> bytes:
    """The running trade like the app's card: price now, R, distances, the stop → entry → target bar, what to do."""
    s = _running(r)
    W, H = 1000, 400
    d = r["spec"]["decimals"]
    f = lambda v: f"{v:.{d}f}"  # noqa: E731
    img = _glow(Image.new("RGBA", (W, H), BG + (255,)))
    g = ImageDraw.Draw(img)
    g.rounded_rectangle((16, 16, W - 16, H - 16), radius=26, fill=PANEL, outline=(120, 96, 45), width=1)
    buy = s["direction"] == "BUY"
    price = r.get("price") or s["entry"]
    entry, sl, tp = s["entry"], s["sl"], s["tp3"]
    risk = abs(entry - sl) or 1
    r_now = (price - entry) * (1 if buy else -1) / risk
    col_r = BULL if r_now >= 0 else BEAR

    # top row
    tag = "BUY" if buy else "SELL"
    tw = g.textlength(tag, font=_font(18)) + 26
    g.rounded_rectangle((46, 44, 46 + tw, 78), radius=9, fill=(BULL if buy else BEAR) + (60,), outline=BULL if buy else BEAR)
    g.text((46 + tw / 2, 61), tag, font=_font(18), fill=(255, 255, 255), anchor="mm")
    g.text((60 + tw, 61), r["displaySymbol"], font=_font(28), fill=(255, 255, 255), anchor="lm")
    g.text((70 + tw + g.textlength(r["displaySymbol"], font=_font(28)), 64), r["timeframes"]["entry"], font=_font(16), fill=DIM, anchor="lm")
    g.text((W - 46, 61), {"PENDING": "WAITING"}.get(s["lifecycle"]["state"], "OPEN"), font=_font(17), fill=MUTED, anchor="rm")

    # price and R
    g.text((46, 110), "PRICE NOW", font=_font(14), fill=DIM)
    g.text((46, 132), f(price), font=_font(32), fill=(255, 255, 255))
    g.text((W - 46, 128), f"{r_now:+.2f}R", font=_font(38), fill=col_r, anchor="ra")
    away = lambda v: (f"${abs(v - price):.2f}" if d == 2 else f"{abs(v - price) / (r['spec'].get('pipSize') or 0.0001):.1f} pips")  # noqa: E731
    g.text((W - 46, 178), f"{away(tp)} to TP  ·  {away(sl)} to SL", font=_font(15), fill=DIM, anchor="ra")

    # the bar: stop on the left, target on the right, the price moving between them
    bx0, bx1, by = 46, W - 46, 222
    pos = lambda v: min(1, max(0, (v - sl) / (tp - sl)))  # noqa: E731
    e, p = pos(entry), pos(price)
    g.rounded_rectangle((bx0, by - 7, bx1, by + 7), radius=7, fill=(40, 44, 54))
    g.rounded_rectangle((bx0, by - 7, bx0 + (bx1 - bx0) * e, by + 7), radius=7, fill=(92, 30, 42))
    g.rounded_rectangle((bx0 + (bx1 - bx0) * e, by - 7, bx1, by + 7), radius=7, fill=(20, 72, 56))
    a, b = sorted((bx0 + (bx1 - bx0) * e, bx0 + (bx1 - bx0) * p))
    g.rectangle((a, by - 7, b, by + 7), fill=col_r)
    ex = bx0 + (bx1 - bx0) * e
    g.rounded_rectangle((ex - 2, by - 15, ex + 2, by + 15), radius=2, fill=GOLD_LIGHT)
    mx = bx0 + (bx1 - bx0) * p
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((mx - 24, by - 24, mx + 24, by + 24), fill=col_r + (110,))
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(10)))
    g = ImageDraw.Draw(img)
    g.ellipse((mx - 13, by - 13, mx + 13, by + 13), fill=(255, 210, 215) if r_now < 0 else (200, 255, 225), outline=(12, 14, 18), width=3)

    # levels under the bar
    g.text((bx0, 250), "SL", font=_font(15), fill=BEAR)
    g.text((bx0, 272), f(sl), font=_font(22), fill=(255, 160, 170))
    ecx = min(max(ex, bx0 + 110), bx1 - 110)
    g.text((ecx, 250), f"ENTRY · {s['direction']}", font=_font(15), fill=GOLD, anchor="ma")
    g.text((ecx, 272), f(entry), font=_font(22), fill=GOLD_LIGHT, anchor="ma")
    g.text((bx1, 250), "TP", font=_font(15), fill=BULL, anchor="ra")
    g.text((bx1, 272), f(tp), font=_font(22), fill=(130, 240, 200), anchor="ra")

    # what to do now (the trade-management agent)
    act = (manager or {}).get("action", {}).get("en") or "Keep SL and TP as they are."
    g.rounded_rectangle((46, 318, W - 46, 364), radius=12, fill=(22, 25, 33), outline=LINE, width=1)
    g.polygon([(64, 333), (64, 349), (76, 341)], fill=GOLD_LIGHT)
    lines = _wrap(g, act, 16, W - 46 - 90 - 46, 1)
    g.text((88, 341), lines[0] if lines else "", font=_font(16), fill=TEXT, anchor="lm")

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------- what the bot sends

async def _m15(sym: str, bundle: dict) -> list[Candle]:
    c = bundle["candles"].get("M15") or []
    if len(c) >= 120:
        return c
    series = await fetch_candle_series(sym, "15M", 400, bundle["result"].get("price"))
    return series["candles"]


async def pair_chart(symbol: str) -> tuple[bytes, str]:
    """The chart picture of `symbol` and its caption."""
    sym = normalize_symbol(symbol)
    bundle = await get_strategy_result(sym)
    r = bundle["result"]
    candles = await _m15(sym, bundle)
    if len(candles) < 40:
        raise ValueError("not enough candles")
    png = render_chart(candles, r)
    d = r["spec"]["decimals"]
    s = _running(r)
    cap = f"{'🥇' if sym == 'XAU/USD' else '💱'} <b>{sym}</b> · M15 · <code>{r['price']:.{d}f}</code>"
    if s:
        cap += (f"\n{'🟢 BUY' if s['direction'] == 'BUY' else '🔴 SELL'} · 📍 <code>{s['entry']:.{d}f}</code> · "
                f"🎯 <code>{s['tp3']:.{d}f}</code> · 🛑 <code>{s['sl']:.{d}f}</code>")
    else:
        cap += "\n⚪ No trade running"
    return png, cap


async def trade_pictures(symbol: str) -> list[tuple[bytes, str]]:
    """For a pair with a running trade: its chart (the setup), then its follow-up card. Empty when nothing runs."""
    from ..agent.agents import manager_agent

    sym = normalize_symbol(symbol)
    bundle = await get_strategy_result(sym)
    r = bundle["result"]
    if not _running(r):
        return []
    chart, cap = await pair_chart(sym)
    manager = manager_agent(r, bundle["candles"].get(STRATEGY_DEFS[sym].entryTf) or [])
    card = render_card(r, manager)
    verdict = (manager or {}).get("verdict", "HOLD").replace("_", " ")
    return [(chart, cap), (card, f"📍 <b>Follow-up</b> · {sym} · {verdict}")]
