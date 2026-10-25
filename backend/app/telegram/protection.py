"""
Anti copy-trading protection for Telegram signals.

1. protect_content: Telegram blocks forwarding, saving and copying of signal messages.
2. Personal micro-offset: every subscriber gets the SAME trade shifted by a tiny, deterministic
   amount (gold: 1–9 cents, EURUSD: 0.1–0.9 pip). Entry, SL and all TPs move together, so the
   stop distance, R:R and lot size are identical, but no two accounts send identical orders
   (brokers / prop firms flag identical copy trades).
3. Personal reference code: printed on the message and logged with the offset, so a leaked
   screenshot or copied levels can be traced back to the subscriber.
"""

from ..strategies.shared.jsnum import round_to

MAX_OFFSET_TICKS = 9
TICK = {"gold": 0.01, "euro": 0.00001}
_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def hash32(s: str) -> int:
    """FNV-1a 32-bit over UTF-16 code units (same values as the JS version)."""
    h = 0x811C9DC5
    data = s.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def _base36(n: int) -> str:
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = _B36[r] + out
        if n == 0:
            return out


def reference_code(chat_id: str, signal_id: str) -> str:
    return _base36(hash32(f"ref|{chat_id}|{signal_id}")).upper().rjust(6, "0")[-6:]


def personal_offset(symbol: str, chat_id: str, signal_id: str) -> float:
    """Signed offset in price units for this subscriber and this signal (never zero)."""
    gold = "EUR" not in symbol
    h = hash32(f"off|{chat_id}|{signal_id}")
    ticks = 1 + h % MAX_OFFSET_TICKS
    sign = 1 if (h >> 16) & 1 else -1
    return sign * ticks * (TICK["gold"] if gold else TICK["euro"])


def personalize_signal(signal: dict, chat_id: str, enabled: bool = True) -> tuple[dict, float, str]:
    """Copy of the signal with every level shifted by the same personal offset → (signal, offset, ref)."""
    ref = reference_code(chat_id, str(signal["id"]))
    if not enabled:
        return signal, 0.0, ref
    gold = "EUR" not in str(signal["symbol"])
    d = 2 if gold else 5
    offset = personal_offset(str(signal["symbol"]), chat_id, str(signal["id"]))

    def shift(v):
        return round_to(v + offset, d) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else v

    out = {**signal, **{k: shift(signal.get(k)) for k in ("entryPrice", "stopLoss", "target1", "target2", "target3")}}
    return out, offset, ref
