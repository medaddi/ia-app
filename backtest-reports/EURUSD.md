# Backtest · EURUSD · Trend Pullback + London Breakout Filter

**Period:** 2026-08-13 → 2026-10-23 (71.6 days) · **Data:** Yahoo Finance EURUSD=X · **Costs:** spread 0.8 pips, slippage 0.2 pips

> ⚠ Only 3 closed trades: far too few to judge the strategy. Treat every number below as anecdotal.
> ⚠ History is only 72 days (Yahoo limits 5m/15m data to ~60 days). A 2–3 year test needs broker (MT5) history.
> ⚠ News filter uses the current ForexFactory week only: past news events are not filtered in this backtest.
> ⚠ Spread is a fixed config value (feed has no live spread); real spreads widen around news and rollover.

| Metric | Value |
|---|---|
| Signals | 3 (filled 3, cancelled/expired 0, open 0) |
| Closed trades | 3 (wins 3, losses 0, breakeven 0) |
| Win rate | 100% |
| Profit factor | Infinity |
| Expectancy | 0.473 R / trade |
| Total | 1.42 R |
| Average planned R:R (TP2) | 2.28 |
| Max drawdown | 0 R |
| Signals per month | 1.3 |

## By session
| Group | Trades | Wins | Losses | Total R |
|---|---|---|---|---|
| London | 3 | 3 | 0 | 1.42 |

## By setup
| Group | Trades | Wins | Losses | Total R |
|---|---|---|---|---|
| A | 3 | 3 | 0 | 1.42 |

## By weekday
| Group | Trades | Wins | Losses | Total R |
|---|---|---|---|---|
| Fri | 1 | — | — | 0.45 |
| Mon | 1 | — | — | 0.47 |
| Tue | 1 | — | — | 0.5 |

## Trades
| Signal (UTC) | Setup | Side | Score | Entry | SL | TP2 | Planned R:R | Result | R | Events |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-21 08:15 | A | BUY | 76 | 1.1697 | 1.16863 | 1.17184 | 2 | CLOSED WIN | 0.453 | FILL@08-21 08:15 TP1@08-21 08:30 BE@08-21 08:30 BE_EXIT@08-21 12:30 |
| 2026-09-07 08:00 | A | BUY | 79 | 1.1627 | 1.1609 | 1.1678 | 2.83 | CLOSED WIN | 0.472 | FILL@09-07 08:00 TP1@09-09 06:15 BE@09-09 06:15 BE_EXIT@09-09 09:45 |
| 2026-09-29 08:00 | A | SELL | 86 | 1.1353 | 1.13772 | 1.13046 | 2 | CLOSED WIN | 0.496 | FILL@09-29 08:00 TP1@09-29 16:45 BE@09-29 16:45 BE_EXIT@09-30 06:00 |
