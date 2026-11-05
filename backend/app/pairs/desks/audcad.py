"""The AUD/CAD team. Two commodity currencies: it ranges and mean-reverts, active in Asia (AUD) and at the New York open (CAD,
oil). Zones count more than trend. COT from two legs: trusted less."""

DESK = {
    "symbol": "AUD/CAD", "team": "AUD/CAD desk", "teamFr": "Équipe AUD/CAD", "teamAr": "فريق AUD/CAD",
    "sessions": [(0, 3, "Asia"), (12, 15, "NY open")],
    "weights": {"trade": 1.5, "structure": 0.8, "liquidity": 1.0, "zones": 1.2, "strategy": 1.5, "cot": 0.5},
    "tags": ["Asia + NY", "commodities", "range"],
}
