"""
The pair agents. Each runs the plan its pair's behaviour favours, chosen for a HIGH WIN RATE that still makes money:
tuned on the first 60 % of 2 years of H1 / H4 (win ≥ 55 %, expectancy ≥ +0.08R per trade), kept only if it also won
≥ 55 % and made money on the last 40 % it never saw, stayed positive with double costs, and its neighbouring settings
agreed (with the pair's spread + slippage, the stop counted first, one trade at a time). A closer target wins more often
and earns less per win; a loss always costs 1R.

  XAU/USD  trends      → H4 breakout of the 40-candle channel in the EMA50 / EMA200 trend · 1.25R
  EUR/USD  mixed       → H1 fade of a close beyond the 10-hour channel, 00–06 GMT, ADX < 35 · 1R
  GBP/USD  mixed       → H1 fade beyond the 40-hour channel in the trend's direction (EMA200), ADX < 35 · 1.25R
  EUR/CHF  reverting   → H1 fade of a close beyond the 10-hour channel, 00–06 GMT · 0.75R
  AUD/CAD  reverting   → H1 fade of a close beyond the 40-hour channel · 0.75R
  AUD/CHF  reverting   → H1 fade of a close beyond the 40-hour channel, ADX < 35 · 0.75R

USD/CAD, NZD/USD and NZD/CAD: no plan held up on the unseen part with a high win rate, so they are not traded.
"""

from .channel import ChannelAgent


class GoldBreakoutAgent(ChannelAgent):
    symbol = "XAUUSD"
    agent_id = "XAUUSD_TrendBreakout_Agent"
    name = "TrendBreakout"
    tf = "H4"
    history = 3200
    timeframes = {"bias": "H4", "setup": "H4", "entry": "H4"}
    rule, channel, sl_atr, target_r, max_bars = "breakout", 40, 2.0, 1.25, 30
    profile = {"character": "trending", "follow": 40, "fade": 28, "tf": "H4"}
    why = ("Gold trends: a close beyond its 40-candle H4 channel in the EMA50 / EMA200 trend keeps going. The agent buys strength "
           "in an uptrend and sells weakness in a downtrend, never against the trend, with a wide 2 ATR stop and a close 1.25R "
           "target the move usually reaches: about 2 trades in 3 won on the history it never saw.")
    steps = ["Trend: EMA50 above EMA200 on H4 for buys, below for sells",
             "Entry: an H4 close beyond the 40-candle high (buys) / low (sells): MARKET at that close",
             "Stop 2 × ATR(14, H4) · one target at 1.25R · closed at market after 30 H4 candles (5 days)",
             "One trade at a time: while a trade runs, the agent manages it and takes no other"]
    test = {"tuned": {"trades": 43, "winRate": 62.8, "totalR": 17.1, "tp2R": None},
            "unseen": {"trades": 25, "winRate": 72.0, "totalR": 15.4, "tp2R": None}, "costsX2": 32.1,
            "neighbours": "every neighbouring setting (channel, stop, target, time limit) positive on both parts"}
    note = "Few trades (about 3 a month): a high win rate, a slow pace"


class EurAsianFadeAgent(ChannelAgent):
    symbol = "EURUSD"
    agent_id = "EURUSD_AsianFade_Agent"
    name = "AsianFade"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, hours, adx_max, target_r, max_bars = "fade", 10, 2.0, (0, 6), 35.0, 1.0, 48
    profile = {"character": "mixed", "follow": 32, "fade": 36, "tf": "H1"}
    why = ("In the quiet Asian hours a close beyond EUR/USD's 10-hour channel has no news or volume behind it and comes back. "
           "The agent fades that stretch between 00:00 and 06:00 GMT when no strong trend runs (ADX < 35), with a wide 2 ATR stop "
           "and a 1R target back across the channel.")
    steps = ["Window: the H1 candle opened between 00:00 and 06:00 GMT (01:00–07:00 Morocco); ADX(14) below 35",
             "Entry: it closes above the 10-candle high (sell) / below the 10-candle low (buy): MARKET at that close",
             "Stop 2 × ATR(14, H1) · one target at 1R · closed at market after 48 H1 candles",
             "One trade at a time"]
    test = {"tuned": {"trades": 129, "winRate": 58.9, "totalR": 16.3, "tp2R": None},
            "unseen": {"trades": 90, "winRate": 56.7, "totalR": 6.1, "tp2R": None}, "costsX2": 9.9,
            "neighbours": "71 % of the neighbouring settings positive on both parts"}
    note = "The smallest edge of the six (+0.07R per trade on the unseen part)"


class GbpTrendFadeAgent(ChannelAgent):
    symbol = "GBPUSD"
    agent_id = "GBPUSD_TrendPullback_Agent"
    name = "TrendPullback"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, adx_max, trend_side, target_r, max_bars = "fade", 40, 1.5, 35.0, True, 1.25, 48
    profile = {"character": "mixed", "follow": 32, "fade": 35, "tf": "H1"}
    why = ("GBP/USD pulls back hard inside its trend. The agent buys a close below the 40-hour low only when price is above EMA200 "
           "(a dip in an uptrend), and sells a close above the 40-hour high only below it (a rally in a downtrend), when no runaway "
           "trend is under way (ADX < 35): stop 1.5 ATR, target 1.25R.")
    steps = ["Trend side: price above EMA200 (H1) to buy a dip, below it to sell a rally; ADX(14) below 35",
             "Entry: an H1 close below the 40-candle low (buy) / above the 40-candle high (sell): MARKET at that close",
             "Stop 1.5 × ATR(14, H1) · one target at 1.25R · closed at market after 48 H1 candles",
             "One trade at a time"]
    test = {"tuned": {"trades": 51, "winRate": 60.8, "totalR": 14.8, "tp2R": None},
            "unseen": {"trades": 29, "winRate": 65.5, "totalR": 11.1, "tp2R": None}, "costsX2": 19.3,
            "neighbours": "71 % of the neighbouring settings positive on both parts"}


class EurChfAsianFadeAgent(ChannelAgent):
    symbol = "EURCHF"
    agent_id = "EURCHF_AsianFade_Agent"
    name = "AsianFade"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, hours, target_r, max_bars = "fade", 10, 1.0, (0, 6), 0.75, 24
    profile = {"character": "reverting", "follow": 26, "fade": 39, "tf": "H4"}
    why = ("EUR/CHF is the calmest pair and the most reverting: in the Asian hours a close beyond its 10-hour channel almost always "
           "comes back a little. The agent fades it with a 1 ATR stop and a close 0.75R target: about 4 trades in 5 won on the "
           "history it never saw.")
    steps = ["Window: the H1 candle opened between 00:00 and 06:00 GMT (01:00–07:00 Morocco)",
             "Entry: it closes above the 10-candle high (sell) / below the 10-candle low (buy): MARKET at that close",
             "Stop 1 × ATR(14, H1) · one target at 0.75R · closed at market after 24 H1 candles",
             "One trade at a time"]
    test = {"tuned": {"trades": 75, "winRate": 81.3, "totalR": 21.5, "tp2R": None},
            "unseen": {"trades": 64, "winRate": 79.7, "totalR": 15.0, "tp2R": None}, "costsX2": 16.1,
            "neighbours": "79 % of the neighbouring settings positive on both parts"}


class AudCadFadeAgent(ChannelAgent):
    symbol = "AUDCAD"
    agent_id = "AUDCAD_RangeFade_Agent"
    name = "RangeFade"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, target_r, max_bars = "fade", 40, 1.0, 0.75, 48
    profile = {"character": "reverting", "follow": 20, "fade": 43, "tf": "H4"}
    why = ("AUD and CAD are both commodity currencies, so AUD/CAD mostly swings inside a range: a close beyond its 40-hour channel "
           "comes back far more often than it runs (43 % vs 20 %). The agent fades it at any hour with a 1 ATR stop and a 0.75R target.")
    steps = ["Entry: an H1 close above the 40-candle high (sell) / below the 40-candle low (buy): MARKET at that close",
             "Stop 1 × ATR(14, H1) · one target at 0.75R · closed at market after 48 H1 candles",
             "One trade at a time"]
    test = {"tuned": {"trades": 222, "winRate": 74.8, "totalR": 42.7, "tp2R": None},
            "unseen": {"trades": 165, "winRate": 70.9, "totalR": 21.5, "tp2R": None}, "costsX2": 20.3,
            "neighbours": "93 % of the neighbouring settings positive on both parts"}


class AudChfFadeAgent(ChannelAgent):
    symbol = "AUDCHF"
    agent_id = "AUDCHF_RangeFade_Agent"
    name = "RangeFade"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, adx_max, target_r, max_bars = "fade", 40, 1.5, 35.0, 0.75, 48
    profile = {"character": "reverting", "follow": 19, "fade": 43, "tf": "H4"}
    why = ("AUD/CHF reverts: a close beyond its 40-hour channel comes back 43 % of the time against 19 % that runs on. The agent "
           "fades it when no strong trend runs (ADX < 35), with a 1.5 ATR stop and a close 0.75R target.")
    steps = ["No strong trend: ADX(14, H1) below 35",
             "Entry: an H1 close above the 40-candle high (sell) / below the 40-candle low (buy): MARKET at that close",
             "Stop 1.5 × ATR(14, H1) · one target at 0.75R · closed at market after 48 H1 candles",
             "One trade at a time"]
    test = {"tuned": {"trades": 155, "winRate": 75.5, "totalR": 34.8, "tp2R": None},
            "unseen": {"trades": 106, "winRate": 73.6, "totalR": 20.0, "tp2R": None}, "costsX2": 28.5,
            "neighbours": "86 % of the neighbouring settings positive on both parts"}
