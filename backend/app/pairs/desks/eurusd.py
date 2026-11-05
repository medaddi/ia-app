"""The EUR/USD team. The most liquid pair: clean structure, the London open and the London / New York overlap move it, and
it respects premium / discount well. The COT report is the euro futures contract: trusted, a little less than gold's."""

DESK = {
    "symbol": "EUR/USD", "team": "EUR/USD desk", "teamFr": "Équipe EUR/USD", "teamAr": "فريق EUR/USD",
    "sessions": [(7, 10, "London"), (12, 16, "NY overlap")],
    "weights": {"trade": 1.5, "structure": 1.0, "liquidity": 1.0, "zones": 1.0, "strategy": 1.5, "cot": 0.9},
    "tags": ["London + overlap", "ECB / Fed", "COT euro"],
}
