"""The pair playbook strategies: the trade rules, the checklist, and no look-ahead."""

from app.smc import playbook
from app.smc.playbook import _Bar, run

T0 = 1_790_000_000 - 1_790_000_000 % 86400


def bars(prices, t0=T0, step=300):
    """M5 candles from (open, high, low, close) tuples."""
    return [_Bar(t0 + i * step, *p) for i, p in enumerate(prices)]


def test_tp1_closes_the_part_then_the_rest_is_safe_at_entry():
    # market BUY at 100, stop 99, TP1 101 (half), TP 103: up to TP1, then back to the entry
    m5 = bars([(100, 100, 100, 100), (100, 101.2, 99.9, 101), (101, 101.1, 99.8, 100)])
    ev = []
    out = run(m5, 0, 1, 100.0, 99.0, 101.0, 103.0, 0.5, True, 0, T0 + 86400, 0.0, ev)
    assert out["state"] == "WIN" and abs(out["r"] - 0.5) < 1e-9  # half at +1R, the rest at break-even
    assert [k for _, k, _ in ev] == ["FILLED", "TP1", "BE", "BE_STOP"]


def test_the_stop_comes_first_inside_a_candle_and_a_limit_can_be_missed():
    m5 = bars([(100, 100, 100, 100), (100, 103.5, 98.5, 101)])  # one candle touches both the stop and the target
    assert run(m5, 0, 1, 100.0, 99.0, None, 103.0, 1.0, True, 0, T0 + 86400, 0.0)["state"] == "LOSS"
    m5 = bars([(100, 100, 100, 100), (100, 104, 100.5, 103.8), (103.8, 104, 99, 99)])  # target before the limit at 100
    assert run(m5, 0, 1, 100.0, 99.0, None, 103.0, 1.0, False, 10, T0 + 86400, 0.0)["state"] == "MISSED"


def test_the_trade_is_closed_at_its_time():
    m5 = bars([(100, 100, 100, 100), (100, 100.5, 99.5, 100.2), (100.4, 100.6, 100.1, 100.5)])
    out = run(m5, 0, 1, 100.0, 99.0, None, 103.0, 1.0, True, 0, m5[2].time, 0.0)
    assert out["state"] == "WIN" and abs(out["r"] - 0.4) < 1e-9  # closed at the open of the candle at hold time


def test_each_strategy_asks_its_own_reward_and_news_blocks():
    s = {"time": T0, "rr": 1.2, "sid": "P"}
    assert not playbook.checklist("XAUUSD", s, None)[2][1]  # Silver Bullet: 1:2
    assert playbook.checklist("EURCHF", s, None)[2][1]  # mean reversion: 1:1
    assert playbook.checklist("EURUSD", {**s, "sid": "P2"}, None)[2][1]  # SnapBack: 1:1 by design
    near = playbook.checklist("EURUSD", {"time": T0, "rr": 3, "sid": "P1"}, [T0 + 10 * 60])
    assert not near[1][1] and near[2][1]  # red news 10 minutes away: no


def test_new_york_times_follow_daylight_saving():
    from datetime import date
    assert playbook.ny(date(2026, 7, 1), 10) % 86400 == 14 * 3600  # 10:00 EDT = 14:00 UTC
    assert playbook.ny(date(2026, 12, 1), 10) % 86400 == 15 * 3600  # 10:00 EST = 15:00 UTC


def test_the_correlated_twins_follow_the_guide():
    from app.smc.skill import portfolio
    assert portfolio.twins("AUD/CHF") == {"AUD/CAD": 0.66} and portfolio.twins("XAU/USD") == {}


def test_no_look_ahead_on_stored_candles():
    from tests.test_smc_live import candles
    for k in ("EURCHF", "AUDCHF", "XAUUSD", "EURUSD", "GBPUSD"):
        m5, h1 = candles(k, "M5"), candles(k, "H1")
        if not m5:
            continue
        cut = m5[-1].time - 3 * 86400
        a, _ = playbook.scan(k, m5, h1, 0.1 if k == "XAUUSD" else 0.0001, 0.0)
        b, _ = playbook.scan(k, [x for x in m5 if x.time < cut], [x for x in h1 if x.time + 3600 <= cut], 0.1 if k == "XAUUSD" else 0.0001, 0.0)
        old = {(x["time"], x["dir"], round(x["entry"], 6), round(x["sl"], 6)) for x in a if x["time"] <= cut - 86400}
        new = {(x["time"], x["dir"], round(x["entry"], 6), round(x["sl"], 6)) for x in b if x["time"] <= cut - 86400}
        assert old == new  # what was found before the cut does not change when later candles arrive


def test_a_pending_limit_is_pulled_around_red_news():
    # a BUY limit at 100: price would reach it on candle 2, but a release falls 10 minutes later
    m5 = bars([(101, 101, 101, 101), (101, 101.2, 100.6, 100.8), (100.8, 100.9, 99.8, 100.2), (100.2, 103.5, 100, 103.2)])
    news = [m5[2].time + 600]
    assert run(m5, 0, 1, 100.0, 99.0, None, 103.0, 1.0, False, 10, T0 + 86400, 0.0)["state"] == "WIN"
    out = run(m5, 0, 1, 100.0, 99.0, None, 103.0, 1.0, False, 10, T0 + 86400, 0.0, None, news)
    assert out["state"] == "EXPIRED" and out["news"] == news[0]


def test_the_stored_news_calendar_is_read_by_pair():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the research project (smc/) sits next to backend/
    from smc.tools.playbook_test import load_news, pair_news
    nw = load_news()
    if not nw:
        return
    gold, eur = pair_news(nw, "XAUUSD"), pair_news(nw, "EURUSD")
    assert set(gold) <= set(eur) and len(eur) > len(gold)  # gold counts the dollar only, EUR/USD both currencies
    assert 1765393200 in gold  # FOMC 2025-12-10 19:00 UTC (14:00 New York)


def test_the_red_folder_list_and_the_eia_wednesdays():
    ev = [{"time": 1, "currency": "USD", "title": "Non-Farm Employment Change"}, {"time": 2, "currency": "EUR", "title": "Main Refinancing Rate"},
          {"time": 3, "currency": "USD", "title": "ISM Services PMI"}, {"time": 4, "currency": "CHF", "title": "SNB Policy Rate"}]
    assert playbook.red_folder(ev) == [1, 4]  # only the guide's list: NFP and SNB yes, ECB and ISM not in it
    from datetime import date
    w = playbook.eia_times(playbook.ny(date(2026, 7, 6), 0), playbook.ny(date(2026, 7, 12), 23))
    assert w == [playbook.ny(date(2026, 7, 8), 10, 30)] and w[0] % 86400 == 14 * 3600 + 1800  # Wednesday 10:30 NY = 14:30 UTC in summer


def test_the_macro_gate_and_the_risk_off_days():
    D = 86400
    up = [(T0 + k * D, 100 + k) for k in range(40)]  # S&P rising
    calm = [(T0 + k * D, 15.0) for k in range(40)]
    ore = [(T0 + k * D, 90 + 0.5 * k) for k in range(40)]
    v = playbook.macro_view(up, calm, ore)
    assert v["gate"][T0 + 39 * D][0] and not v["exits"]
    jump = calm[:30] + [(T0 + 30 * D, 18.0)] + calm[31:]  # VIX +20 % on day 30
    v = playbook.macro_view(up, jump, ore)
    assert v["exits"] == [T0 + 30 * D + 22 * 3600] and not v["gate"][T0 + 31 * D][0]


def test_a_risk_off_closes_the_trade_at_once():
    m5 = bars([(100, 100, 100, 100), (100, 100.5, 99.8, 100.3), (100.3, 100.6, 100.1, 100.4), (100.4, 103.5, 100.2, 103.2)])
    out = run(m5, 0, 1, 100.0, 99.0, None, 103.0, 1.0, True, 0, T0 + 86400, 0.0, None, None, [m5[2].time])
    assert out["state"] == "WIN" and out["riskOff"] and abs(out["r"] - 0.3) < 1e-9  # closed at the open of candle 2, not at TP
