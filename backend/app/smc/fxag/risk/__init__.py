"""
Agent 2 · the Risk agent (the owner, 2026-11-20: "one agent that computes the stop loss, the take profit and the lot").
levels.py: the stop (structural invalidation + 6 lambda pips + spread), the structural target (capped before an opposing
Weekly AOI), R:R >= 2.0, the No-Trap runway, the seasonal risk % x grade, the lot formula and the ranking of one close's
signals. order.py: the locked Set & Forget order (idempotent id, signal only).
"""
