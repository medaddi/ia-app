"""
Number helpers that reproduce JavaScript semantics exactly, so the Python strategies give the
same levels, texts and ids as the original TypeScript version (checked by tests/test_parity.py).
"""

import math
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

INF = math.inf
NAN = math.nan


def to_fixed(x: float, d: int) -> str:
    """Number.prototype.toFixed: exact binary value, half away from zero."""
    if x is None or math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        x = 0.0  # (-0).toFixed() is "0"
    q = Decimal(x).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return f"{q:.{d}f}"


def round_to(x: float, d: int) -> float:
    """Number(v.toFixed(d))."""
    s = to_fixed(x, d)
    return float(s) if s not in ("NaN", "Infinity", "-Infinity") else float(s.replace("Infinity", "inf"))


def js_round(x: float) -> float:
    """Math.round: half towards +Infinity."""
    if math.isnan(x) or math.isinf(x):
        return x
    return float(math.floor(x + 0.5))


def js_str(x) -> str:
    """String(number) / template-literal formatting of a number."""
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    r = repr(x)
    if "e" in r:  # 1e-07 → 1e-7, 1.5e+22 → 1.5e+22
        mant, exp = r.split("e")
        sign = "-" if exp.startswith("-") else "+"
        r = f"{mant}e{sign}{int(exp.lstrip('+-'))}"
    return r


def js_div(a: float, b: float) -> float:
    if b == 0:
        if a == 0 or math.isnan(a):
            return NAN
        return INF if a > 0 else -INF
    return a / b


def clamp01(q: float) -> float:
    """Math.max(0, Math.min(1, q)) keeping NaN."""
    if math.isnan(q):
        return q
    return max(0.0, min(1.0, q))


def iso(ts: float) -> str:
    """new Date(ts * 1000).toISOString()."""
    dt = datetime.fromtimestamp(ts, timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def fmt_time(t: float) -> str:
    return iso(t)[11:16] + " UTC"


def fmt_utc_minute(t: float) -> str:
    return iso(t)[:16].replace("T", " ")


def finite(x) -> bool:
    return isinstance(x, (int, float)) and not (math.isnan(x) or math.isinf(x))
