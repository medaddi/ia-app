"""The AUD/CHF team. Risk-on (AUD) against safe haven (CHF): it trends with risk mood, moves in Asia and at the London open.
COT from two legs: trusted less."""

DESK = {
    "symbol": "AUD/CHF", "team": "AUD/CHF desk", "teamFr": "Équipe AUD/CHF", "teamAr": "فريق AUD/CHF",
    "sessions": [(0, 3, "Asia"), (7, 10, "London")],
    "weights": {"trade": 1.5, "structure": 1.1, "liquidity": 1.0, "zones": 0.9, "strategy": 1.5, "cot": 0.5},
    "tags": ["Asia + London", "risk mood", "safe haven"],
}
