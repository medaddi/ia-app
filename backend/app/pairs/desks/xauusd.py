"""The gold team. Gold moves on the dollar and US yields: London open and the New York session carry the day, Asia is thin.
Its structure and its liquidity runs are strong (long stop hunts above / below the day's highs and lows), and the CFTC gold
futures report is one contract read directly: trusted fully."""

DESK = {
    "symbol": "XAU/USD", "team": "Gold desk", "teamFr": "Équipe Or", "teamAr": "فريق الذهب",
    "sessions": [(7, 10, "London"), (12, 17, "New York")],  # UTC hours, end excluded
    "weights": {"trade": 1.5, "structure": 1.2, "liquidity": 1.2, "zones": 0.7, "strategy": 1.5, "cot": 1.0},
    "tags": ["London + NY", "USD / yields", "COT gold"],
}
