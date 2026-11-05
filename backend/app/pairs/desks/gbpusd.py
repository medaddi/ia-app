"""The GBP/USD team. Cable is fast and sweeps liquidity hard at the London open: the liquidity member counts more, the
zones less (it runs through them). COT: the sterling futures contract."""

DESK = {
    "symbol": "GBP/USD", "team": "GBP/USD desk", "teamFr": "Équipe GBP/USD", "teamAr": "فريق GBP/USD",
    "sessions": [(7, 10, "London"), (12, 15, "NY open")],
    "weights": {"trade": 1.5, "structure": 1.0, "liquidity": 1.3, "zones": 0.7, "strategy": 1.5, "cot": 0.8},
    "tags": ["London open", "BoE / Fed", "COT sterling"],
}
