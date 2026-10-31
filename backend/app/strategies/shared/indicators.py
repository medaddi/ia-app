import math

from .types import Candle

NAN = math.nan


def ema_series(values: list[float], period: int) -> list[float]:
    """EMA seeded with the SMA of the first `period` values. NaN until enough data."""
    out = [NAN] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    ema = 0.0
    for v in values[:period]:
        ema += v
    ema /= period
    out[period - 1] = ema
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        out[i] = ema
    return out


def _true_range(c: list[Candle], i: int) -> float:
    p = c[i - 1].close
    return max(c[i].high - c[i].low, abs(c[i].high - p), abs(c[i].low - p))


def atr_series(c: list[Candle], period: int = 14) -> list[float]:
    """Wilder ATR. NaN until `period` true ranges exist."""
    out = [NAN] * len(c)
    if len(c) <= period:
        return out
    s = 0.0
    for i in range(1, period + 1):
        s += _true_range(c, i)
    atr = s / period
    out[period] = atr
    for i in range(period + 1, len(c)):
        atr = (atr * (period - 1) + _true_range(c, i)) / period
        out[i] = atr
    return out


def rsi_series(closes: list[float], period: int = 14) -> list[float]:
    """Wilder RSI. NaN until `period` changes exist."""
    out = [NAN] * len(closes)
    if len(closes) <= period:
        return out
    gain = loss = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gain += d
        else:
            loss -= d
    avg_gain = gain / period
    avg_loss = loss / period
    out[period] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period
        out[i] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def body(c: Candle) -> float:
    return abs(c.close - c.open)


def avg_body_series(c: list[Candle], period: int = 20) -> list[float]:
    """Average body of the `period` candles BEFORE index i (the candle itself is excluded)."""
    out = [NAN] * len(c)
    s = 0.0
    for i in range(len(c)):
        if i >= period:
            out[i] = s / period
        s += body(c[i])
        if i >= period:
            s -= body(c[i - period])
    return out


def last_value(series: list[float]) -> float:
    """Last finite value of a series."""
    for v in reversed(series):
        if not (math.isnan(v) or math.isinf(v)):
            return v
    return NAN
