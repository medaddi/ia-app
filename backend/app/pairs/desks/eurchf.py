"""The EUR/CHF team. A slow, range-bound cross (the franc is a safe haven): premium / discount of the range matters most,
the trend less. Europe's hours only. COT: built from two legs (euro and franc), so trusted less."""

DESK = {
    "symbol": "EUR/CHF", "team": "EUR/CHF desk", "teamFr": "Équipe EUR/CHF", "teamAr": "فريق EUR/CHF",
    "sessions": [(7, 12, "Europe")],
    "weights": {"trade": 1.5, "structure": 0.8, "liquidity": 0.9, "zones": 1.3, "strategy": 1.5, "cot": 0.5},
    "tags": ["Europe", "range", "safe haven"],
}
