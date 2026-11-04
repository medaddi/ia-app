"""
The 4 pair agents. Each runs the plan its pair's behaviour favours, kept because it held up on the last 40 % of 2 years
of H1 / H4 it was never tuned on (with the pair's spread + slippage, the stop counted first, one trade at a time):

  XAU/USD  trends      → breakout of the 20-hour channel in the EMA50 / EMA200 trend, H1
  EUR/USD  mixed       → fade of a close beyond the 10-hour channel in the quiet Asian hours (00–06 GMT), H1
  GBP/USD  mixed       → fade of an H4 close beyond the 10-candle channel when ADX < 35 (no strong trend), H4
  AUD/CHF  reverting   → fade of a close beyond the 40-hour channel in the Asian hours (22–05 GMT), H1
"""

from .channel import ChannelAgent

# How each pair behaves (2 years): after a close beyond the 20-candle channel, how often price went 2 ATR on (follow)
# or 2 ATR back (fade) before 1 ATR the other way. The break-even at 2:1 is 33 %.


class GoldBreakoutAgent(ChannelAgent):
    symbol = "XAUUSD"
    agent_id = "XAUUSD_TrendBreakout_Agent"
    name = "TrendBreakout"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, max_bars = "breakout", 20, 2.0, 48
    profile = {"character": "trending", "follow": 40, "fade": 28, "tf": "H4"}
    why = ("Gold trends: a close beyond its 20-hour channel in the EMA50 / EMA200 trend runs on more often than it comes back "
           "(40 % vs 28 %). The agent buys strength in an uptrend and sells weakness in a downtrend, never against the trend. "
           "The stop at 2 ATR leaves room for the New York noise; the 2R target is 4 ATR away, a distance gold covers within two days.")
    steps = ["Trend: EMA50 above EMA200 on H1 for buys, below for sells",
             "Entry: an H1 close beyond the 20-candle high (buys) / low (sells): MARKET at that close",
             "Stop 2 × ATR(14, H1) · one target at 2R · closed at market after 48 H1 candles",
             "One trade at a time: while a trade runs, the agent manages it and takes no other"]
    test = {"tuned": {"trades": 142, "winRate": 44.4, "totalR": 24.9, "tp2R": 33.8},
            "unseen": {"trades": 87, "winRate": 47.1, "totalR": 31.3, "tp2R": 42.5}, "costsX2": 53.7,
            "neighbours": "every channel (10 / 20 / 40 / 55) and stop (1 / 1.5 / 2 ATR) positive on the unseen part (+21R to +57R)"}


class EurAsianFadeAgent(ChannelAgent):
    symbol = "EURUSD"
    agent_id = "EURUSD_AsianFade_Agent"
    name = "AsianFade"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, hours, max_bars = "fade", 10, 1.5, (0, 6), 48
    profile = {"character": "mixed", "follow": 32, "fade": 36, "tf": "H1"}
    why = ("EUR/USD has no clear lean over the whole day, but in the quiet Asian hours a close beyond its 10-hour channel has no news "
           "or volume behind it and comes back. The agent fades that stretch only between 00:00 and 06:00 GMT, with a 1.5 ATR stop "
           "that survives a late spike, and aims back across the channel at 2R.")
    steps = ["Window: the H1 candle opened between 00:00 and 06:00 GMT (01:00–07:00 Morocco)",
             "Entry: it closes above the 10-candle high (sell) / below the 10-candle low (buy): MARKET at that close",
             "Stop 1.5 × ATR(14, H1) · one target at 2R · closed at market after 48 H1 candles",
             "One trade at a time"]
    test = {"tuned": {"trades": 160, "winRate": 41.2, "totalR": 26.3, "tp2R": 40.0},
            "unseen": {"trades": 107, "winRate": 43.0, "totalR": 19.9, "tp2R": 42.1}, "costsX2": 26.3,
            "neighbours": "every Asian window (21–06, 22–05, 00–06 GMT) positive on both parts (+13R to +26R); tighter stops lose"}


class GbpChannelFadeAgent(ChannelAgent):
    symbol = "GBPUSD"
    agent_id = "GBPUSD_ChannelFade_Agent"
    name = "ChannelFade"
    tf = "H4"
    history = 3200
    timeframes = {"bias": "H4", "setup": "H4", "entry": "H4"}
    rule, channel, sl_atr, adx_max, max_bars = "fade", 10, 1.0, 35.0, 12
    profile = {"character": "mixed", "follow": 32, "fade": 35, "tf": "H4"}
    why = ("GBP/USD's H4 closes beyond the 10-candle channel come back more often than they run (35 % vs 32 %), unless a strong trend "
           "is under way. The agent fades the stretch only while ADX is below 35, stop 1 ATR, the 2R target back inside the channel, "
           "two days at most.")
    steps = ["No strong trend: ADX(14, H4) below 35 (else COOLDOWN)",
             "Entry: an H4 close above the 10-candle high (sell) / below the 10-candle low (buy): MARKET at that close",
             "Stop 1 × ATR(14, H4) · one target at 2R · closed at market after 12 H4 candles (2 days)",
             "One trade at a time"]
    test = {"tuned": {"trades": 144, "winRate": 43.1, "totalR": 27.4, "tp2R": 38.2},
            "unseen": {"trades": 80, "winRate": 45.0, "totalR": 14.3, "tp2R": 37.5}, "costsX2": 29.3,
            "neighbours": "positive on both parts with ADX < 25, < 35 or none (+12R to +27R)"}
    note = "Fragile to the stop size and the channel length: only the 10-candle channel with a 1 ATR stop holds"


class AudChfAsianFadeAgent(ChannelAgent):
    symbol = "AUDCHF"
    agent_id = "AUDCHF_AsianFade_Agent"
    name = "AsianFade"
    tf = "H1"
    history = 12500
    timeframes = {"bias": "H1", "setup": "H1", "entry": "H1"}
    rule, channel, sl_atr, hours, max_bars = "fade", 40, 1.0, (22, 5), 48
    profile = {"character": "reverting", "follow": 19, "fade": 43, "tf": "H4"}
    why = ("AUD/CHF reverts the most of the four: a close beyond its channel comes back 43 % of the time against 19 % that runs on. "
           "The agent fades a close beyond the 40-hour channel in the Asian hours (22:00–05:00 GMT), stop 1 ATR, the 2R target back "
           "toward the middle.")
    steps = ["Window: the H1 candle opened between 22:00 and 05:00 GMT (23:00–06:00 Morocco)",
             "Entry: it closes beyond the 40-candle high (sell) / low (buy): MARKET at that close",
             "Stop 1 × ATR(14, H1) · one target at 2R · closed at market after 48 H1 candles",
             "One trade at a time"]
    test = {"tuned": {"trades": 70, "winRate": 50.0, "totalR": 25.7, "tp2R": 50.0},
            "unseen": {"trades": 36, "winRate": 44.4, "totalR": 6.3, "tp2R": 44.4}, "costsX2": 16.4,
            "neighbours": "every Asian window positive on both parts with a 40-candle channel (+3R to +7R unseen)"}
    note = "Small edge on the unseen part (+6.3R on 36 trades): the weakest of the four"
