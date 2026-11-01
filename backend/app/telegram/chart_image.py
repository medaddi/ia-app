"""
The chart of a pair as a picture for Telegram (/chart): the app's dark and gold look, drawn with Pillow (no browser).
Candles of the pair's chart timeframe (gold H1, EUR/GBP H4, the GPA pairs H4), the averages its strategy reads, the
running trade (entry, stop, target and their zones) and the price axis, in 1280 × 720.
"""

import io
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..strategies.service import get_strategy_result, normalize_symbol
from ..strategies.shared.types import Candle

W, H = 1280, 720
PAD_L, PAD_R, TOP, BOTTOM = 28, 124, 140, 64
BARS = 110
BG, GRID, AXIS, TEXT, MUTED = (7, 9, 13), (255, 255, 255, 14), (31, 36, 48), (226, 232, 240), (141, 150, 166)
BULL, BEAR, GOLD, GOLD_LIGHT = (22, 199, 132), (234, 57, 67), (201, 160, 74), (239, 217, 154)
EMA_COLORS = [(75, 133, 184), (201, 160, 74)]
LIVE = ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")
# The timeframe each strategy reads best on one picture, and its averages
VIEW = {"XAU/USD": ("H1", [50, 200]), "EUR/USD": ("H4", [5, 200]), "GBP/USD": ("H4", [5, 200])}
DEFAULT_VIEW = ("H4", [50])


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _ema(vals: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(vals)
    if len(vals) < n:
        return out
    k, e = 2 / (n + 1), sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out


def render(symbol: str, candles: list[Candle], result: dict, tf: str, emas: list[int], now: Optional[float] = None) -> bytes:
    """The PNG of the pair: candles, averages, the running trade and the price axis."""
    now = now or time.time()
    d = result["spec"]["decimals"]
    f = lambda v: f"{v:.{d}f}"  # noqa: E731
    closes_all = [c.close for c in candles]
    lines = [(n, _ema(closes_all, n)[-BARS:]) for n in emas]
    c = candles[-BARS:]
    s = result.get("setup")
    trade = s if s and s["lifecycle"]["state"] in LIVE and result["status"] in ("SIGNAL", "WATCH") else None
    price = result.get("price") or (c[-1].close if c else 0)

    lo = min(x.low for x in c)
    hi = max(x.high for x in c)
    if trade:  # the trade's levels always fit on the picture
        lo, hi = min(lo, trade["sl"], trade["tp3"], trade["entry"]), max(hi, trade["sl"], trade["tp3"], trade["entry"])
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    x0, x1, y0, y1 = PAD_L, W - PAD_R, TOP, H - BOTTOM
    step = (x1 - x0) / max(len(c) + 3, 1)  # a little room after the last candle
    y = lambda v: y1 - (v - lo) / (hi - lo) * (y1 - y0)  # noqa: E731

    img = Image.new("RGBA", (W, H), BG + (255,))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W * 0.62, -220, W + 160, 180), fill=(201, 160, 74, 30))  # the app's soft gold glow, top right
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(120)))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(layer)
    dr = ImageDraw.Draw(img)

    # grid + price axis
    ticks = 6
    for k in range(ticks + 1):
        v = lo + (hi - lo) * k / ticks
        yy = y(v)
        g.line((x0, yy, x1, yy), fill=GRID, width=1)
        dr.text((x1 + 12, yy), f(v), font=_font(15), fill=MUTED, anchor="lm")
    dr.line((x1, y0 - 8, x1, y1), fill=AXIS, width=1)

    # the trade: target and stop zones from the signal candle, levels on the axis
    if trade:
        sig_i = next((i for i, x in enumerate(c) if x.time >= trade["signalTime"] - 1), 0)
        zx = x0 + sig_i * step
        g.rectangle((zx, min(y(trade["entry"]), y(trade["tp3"])), x1, max(y(trade["entry"]), y(trade["tp3"]))), fill=BULL + (34,))
        g.rectangle((zx, min(y(trade["entry"]), y(trade["sl"])), x1, max(y(trade["entry"]), y(trade["sl"]))), fill=BEAR + (34,))
    img = Image.alpha_composite(img, layer)
    dr = ImageDraw.Draw(img)

    # candles
    body = max(2, step * 0.62)
    for i, x in enumerate(c):
        cx = x0 + i * step + step / 2
        col = BULL if x.close >= x.open else BEAR
        dr.line((cx, y(x.high), cx, y(x.low)), fill=col, width=1)
        top, bot = y(max(x.open, x.close)), y(min(x.open, x.close))
        dr.rectangle((cx - body / 2, top, cx + body / 2, max(bot, top + 1)), fill=col)

    # averages
    for k, (n, vals) in enumerate(lines):
        pts = [(x0 + i * step + step / 2, y(v)) for i, v in enumerate(vals) if v is not None]
        if len(pts) > 1:
            dr.line(pts, fill=EMA_COLORS[k % 2], width=2, joint="curve")

    badges = [(price, "", GOLD, True)]
    if trade:
        badges += [(trade["tp3"], "TP", BULL, True), (trade["sl"], "SL", BEAR, False), (trade["entry"], "ENTRY", GOLD_LIGHT, True)]
    placed: list[list] = []
    for v, label, color, dark in sorted(badges, key=lambda b: y(b[0])):
        yy = y(v)
        dr.line((x0, yy, x1, yy), fill=color, width=1)
        by = max(yy, placed[-1][0] + 24) if placed else yy  # 24 px apart: no badge covers another
        placed.append([by, f"{label} {f(v)}" if label else f(v), color, dark])
    for by, txt, color, dark in placed:
        w = dr.textlength(txt, font=_font(14)) + 14
        dr.rounded_rectangle((x1 + 4, by - 11, x1 + 4 + w, by + 11), radius=5, fill=color)
        dr.text((x1 + 11, by), txt, font=_font(14), fill=(10, 12, 16) if dark else (255, 255, 255), anchor="lm")

    # header: pair, timeframe, price, strategy; the trade on the right
    name = result["displaySymbol"]
    dr.text((x0, 30), name, font=_font(34), fill=(255, 255, 255))
    nw = dr.textlength(name, font=_font(34))
    dr.rounded_rectangle((x0 + nw + 14, 34, x0 + nw + 14 + 46, 62), radius=7, outline=AXIS, width=1)
    dr.text((x0 + nw + 37, 48), tf, font=_font(15), fill=GOLD_LIGHT, anchor="mm")
    dr.text((x0, 76), f"{f(price)}   ·   {result['strategyName'].split('·')[-1].strip()}", font=_font(17), fill=MUTED)
    if trade:
        buy = trade["direction"] == "BUY"
        tag = f"{'BUY' if buy else 'SELL'} · {'running' if trade['lifecycle']['state'] != 'PENDING' else 'waiting'}"
        tw = dr.textlength(tag, font=_font(18)) + 30
        dr.rounded_rectangle((x1 - tw, 30, x1, 64), radius=10, fill=(BULL if buy else BEAR) + (255,))
        dr.text((x1 - tw / 2, 47), tag, font=_font(18), fill=(255, 255, 255), anchor="mm")
        risk = abs(trade["entry"] - trade["sl"]) or 1
        r_now = (price - trade["entry"]) * (1 if buy else -1) / risk
        dr.text((x1, 84), f"{r_now:+.2f}R", font=_font(20), fill=BULL if r_now >= 0 else BEAR, anchor="rm")
    else:
        tw = dr.textlength("NO TRADE", font=_font(16)) + 28
        dr.rounded_rectangle((x1 - tw, 32, x1, 62), radius=10, outline=AXIS, width=1)
        dr.text((x1 - tw / 2, 47), "NO TRADE", font=_font(16), fill=MUTED, anchor="mm")

    # legend + footer
    lx = x0
    for k, n in enumerate(emas):
        dr.line((lx, y0 - 14, lx + 18, y0 - 14), fill=EMA_COLORS[k % 2], width=3)
        dr.text((lx + 24, y0 - 14), f"EMA{n}", font=_font(14), fill=MUTED, anchor="lm")
        lx += 90
    first, last = c[0].time, c[-1].time
    dr.text((x0, H - 34), f"{time.strftime('%d %b %H:%M', time.gmtime(first))} - {time.strftime('%d %b %H:%M', time.gmtime(last))} UTC",
            font=_font(14), fill=MUTED, anchor="lm")
    brand = "Liquidity"
    bw = dr.textlength(brand + " ", font=_font(18))
    full = bw + dr.textlength("Dissection", font=_font(18))
    dr.text((W - 28 - full, H - 34), brand, font=_font(18), fill=(255, 255, 255), anchor="lm")
    dr.text((W - 28 - full + bw, H - 34), "Dissection", font=_font(18), fill=GOLD_LIGHT, anchor="lm")

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


async def pair_chart(symbol: str) -> tuple[bytes, str]:
    """The picture of `symbol` and its caption (pair, price, the trade if one is running)."""
    sym = normalize_symbol(symbol)
    bundle = await get_strategy_result(sym)
    r = bundle["result"]
    tf, emas = VIEW.get(sym, DEFAULT_VIEW)
    candles = bundle["candles"].get(tf) or bundle["candles"].get(r["timeframes"]["entry"]) or []
    if len(candles) < 20:
        raise ValueError("not enough candles")
    png = render(sym, candles, r, tf, emas)
    d = r["spec"]["decimals"]
    s = r.get("setup")
    cap = f"{'🥇' if sym == 'XAU/USD' else '💱'} <b>{sym}</b> · {tf} · <code>{r['price']:.{d}f}</code>"
    if s and s["lifecycle"]["state"] in LIVE and r["status"] in ("SIGNAL", "WATCH"):
        cap += (f"\n{'🟢 BUY' if s['direction'] == 'BUY' else '🔴 SELL'} · 📍 <code>{s['entry']:.{d}f}</code> · "
                f"🎯 <code>{s['tp3']:.{d}f}</code> · 🛑 <code>{s['sl']:.{d}f}</code>")
    else:
        cap += "\n⚪ No trade running"
    return png, cap
