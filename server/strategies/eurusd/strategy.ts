/**
 * EURUSD — "Trend Pullback + London Breakout Filter"
 *
 * Bias (H4, Daily filter): bullish if H4 close > EMA200, EMA50 > EMA200 and H4 swings are HH/HL;
 * bearish mirror. No buys within 15 pips of daily resistance / PWH (mirror for sells).
 * Windows: London 07:00–10:30 and London/NY overlap 13:00–16:00 (London time); none Friday after 14:00.
 *
 * Setup A (trend pullback, M15 entry): pullback into >= 2 of {H1 OB, Fib 50–61.8% of the last H1
 * impulse, M15 EMA50}; RSI(14, M15) at the pullback 40–50 (buys) / 50–60 (sells); confirmation
 * candle = engulfing, pin bar (wick >= 2× body) or M15 CHoCH; MARKET entry at its close.
 * Setup B (Asian false breakout): Asian range 12–40 pips; in the London window a candle trades
 * beyond one side and closes back inside; trade toward the other side only with the H4 bias.
 * Risk: SL beyond zone/swing + 3 pips or 1.5 × ATR(14, M15), whichever is wider, 8–25 pips.
 * TP1 = 1R (50%, SL to BE), TP2 = next H1 level (>= 2R) or 2R, TP3 trails behind M15 swings.
 */

import { Candle, closedOnly, Direction, roundTo } from "../shared/types";
import { atrSeries, avgBodySeries, body, emaSeries, lastValue, rsiSeries } from "../shared/indicators";
import { detectStructure, detectSwings, structureFromLabels, Swing } from "../shared/structure";
import { detectFvgs, detectOrderBlocks, OrderBlock } from "../shared/zones";
import { inLocalWindow, localDateKey, sessionRange, SessionRange, zonedParts } from "../shared/sessions";
import { dailyWeeklyLevels, findSweeps, Level } from "../shared/liquidity";
import { newsBlock } from "../shared/news";
import { classify, lotTable, rr, scoreChecklist, toPips } from "../shared/risk";
import { simulateLifecycle } from "../shared/lifecycle";
import { StrategyInput } from "../shared/input";
import { Drawing, StrategyResult, TradeSetup } from "../shared/result";
import { activeWindow, fmtTime, isUntaken, item, nearestSwingBeyond, toSignalJson, volatilityRatio } from "../shared/common";
import { declutterZones, fvgDrawings, levelDrawings, obDrawings, sessionDrawings, structureDrawings, sweepDrawings, swingDrawings, tradeDrawings } from "../shared/drawings";
import { EUR_CONFIG, EurConfig } from "./config";
import { ChecklistItem } from "../shared/types";

interface Candidate {
  setup: TradeSetup;
  checklist: ChecklistItem[];
  score: number;
  requiredOk: boolean;
}

export function evaluateEurusd(input: StrategyInput, cfg: EurConfig = EUR_CONFIG): StrategyResult {
  const spec = cfg.spec;
  const d = spec.decimals;
  const pip = spec.pipSize;
  const f = (v: number) => v.toFixed(d);
  const pips = (v: number) => toPips(spec, v);
  const now = input.nowSec;
  const m15 = closedOnly(input.candles.M15 || [], 900, now).slice(-700);
  const h1 = closedOnly(input.candles.H1 || [], 3600, now).slice(-800);
  const h4 = closedOnly(input.candles.H4 || [], 14400, now).slice(-500);
  const d1 = closedOnly(input.candles.D1 || [], 86400, now).slice(-300);
  const last = m15.length - 1;
  const price = input.livePrice > 0 ? input.livePrice : m15[last]?.close ?? 0;
  const spread = input.spread ?? cfg.filters.assumedSpreadPips * pip;
  const slippage = cfg.filters.slippagePips * pip;
  const S = cfg.structure;
  const W = cfg.scoring.weights;

  const result: StrategyResult = {
    symbol: spec.symbol, displaySymbol: spec.displaySymbol, strategy: cfg.strategy, strategyName: cfg.name,
    timeframes: cfg.timeframes, nowSec: now, price, spec,
    dataQuality: { ok: true, reason: "Live data OK", source: input.dataSource },
    market: { isOpen: input.isMarketOpen, window: null },
    bias: { direction: "NEUTRAL", detail: "" },
    status: "NO_TRADE", score: 0, checklist: [], rejection: null, headline: "", headlineAr: "",
    setup: null, signal: null, canNotify: false,
    news: { blocked: false, detail: "", next: null, source: input.news.source },
    day: input.day, drawings: [], facts: {},
  };

  const stale = input.isMarketOpen && m15.length > 0 && now - (m15[last].time + 900) > 3 * 900;
  if (!input.isRealData || m15.length < 150 || h1.length < 150 || h4.length < cfg.bias.emaSlow + 10 || d1.length < 30 || stale) {
    result.dataQuality = {
      ok: false, source: input.dataSource,
      reason: !input.isRealData ? "Live feed unavailable (synthetic candles): no analysis"
        : stale ? "Last M15 candle is stale (feed paused)"
        : `Not enough history (M15 ${m15.length}, H1 ${h1.length}, H4 ${h4.length}, D1 ${d1.length})`,
    };
    result.headline = "Data not usable";
    result.headlineAr = "البيانات غير صالحة";
    return result;
  }

  // ---- Detectors ----
  const atr15 = atrSeries(m15, cfg.atrPeriod);
  const swings15 = detectSwings(m15, S.swingN);
  const st15 = detectStructure(m15, swings15, avgBodySeries(m15, S.avgBodyPeriod), S.displacementMult);
  const ema50m15 = emaSeries(m15.map(x => x.close), cfg.setupA.emaPeriod);
  const rsi15 = rsiSeries(m15.map(x => x.close), cfg.setupA.rsiPeriod);
  const atrH1 = atrSeries(h1, cfg.atrPeriod);
  const swingsH1 = detectSwings(h1, S.swingN);
  const stH1 = detectStructure(h1, swingsH1, avgBodySeries(h1, S.avgBodyPeriod), S.displacementMult);
  const obsH1 = detectOrderBlocks(h1, stH1.events, "H1");
  const fvgsH1 = detectFvgs(h1, atrH1, cfg.fvgMinAtr, "H1");
  const swingsH4 = detectSwings(h4, S.htfSwingN);
  const swingsD1 = detectSwings(d1, S.dailySwingN);
  const levels: Level[] = dailyWeeklyLevels(h1);

  // ---- Bias ----
  const h4Close = h4[h4.length - 1].close;
  const e50 = lastValue(emaSeries(h4.map(x => x.close), cfg.bias.emaFast));
  const e200 = lastValue(emaSeries(h4.map(x => x.close), cfg.bias.emaSlow));
  const h4Struct = structureFromLabels(swingsH4);
  let bias: Direction | "NEUTRAL" = "NEUTRAL";
  if (h4Close > e200 && e50 > e200 && h4Struct === "BULLISH") bias = "BULLISH";
  else if (h4Close < e200 && e50 < e200 && h4Struct === "BEARISH") bias = "BEARISH";
  const biasDetail = `H4 close ${f(h4Close)} ${h4Close > e200 ? ">" : "<"} EMA200 ${f(e200)}, EMA50 ${f(e50)} ${e50 > e200 ? ">" : "<"} EMA200, H4 swings ${h4Struct === "BULLISH" ? "HH/HL" : h4Struct === "BEARISH" ? "LH/LL" : "mixed"}`;
  result.bias = { direction: bias, detail: biasDetail };

  // ---- Shared filters ----
  const news = newsBlock(now, input.news.events, cfg.filters.news);
  result.news = {
    blocked: news.blocked,
    detail: news.event ? `${news.event.currency} ${news.event.title} at ${fmtTime(news.event.time)}` : "No high-impact EUR/USD news within ±30 min",
    next: news.next ? `${news.next.currency} ${news.next.title} ${new Date(news.next.time * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC` : null,
    source: input.news.source,
  };
  const vol = volatilityRatio(atrH1, cfg.filters.volatility.lookbackBars);
  result.market.window = activeWindow(now, cfg.sessions.windows)?.name ?? null;

  const todayKey = localDateKey(now, cfg.sessions.asia.tz);
  const asia = sessionRange(m15, 900, "Asia", todayKey, cfg.sessions.asia.tz, cfg.sessions.asia.start, cfg.sessions.asia.end, now);

  // Filters evaluated at the signal time of a candidate
  const commonChecks = (signalTime: number, dir: "BUY" | "SELL", entry: number, sl: number, tp2: number, slDist: number): ChecklistItem[] => {
    const buy = dir === "BUY";
    const win = activeWindow(signalTime - 1, cfg.sessions.windows);
    const z = zonedParts(signalTime - 1, cfg.sessions.fridayCutoff.tz);
    const friday = z.weekday === 5 && !inLocalWindow(signalTime - 1, cfg.sessions.fridayCutoff.tz, "00:00", cfg.sessions.fridayCutoff.time);
    const dailyRes = nearestDailyBarrier(swingsD1, levels, entry, buy, d1.length - 1);
    const room = dailyRes ? pips(Math.abs(dailyRes.price - entry)) : 999;
    const rrTp2 = rr(entry, sl, tp2);
    const slPips = pips(slDist);
    const nb = newsBlock(signalTime, input.news.events, cfg.filters.news);
    const spreadPips = spread / pip;
    const dayOk = input.day.trades < cfg.filters.maxTradesPerDay && input.day.losses < cfg.filters.maxLossesPerDay;
    const htf = nearestSwingBeyond(swingsH1, entry, buy, h1.length - 1);
    const htfR = htf ? Math.abs(htf.price - entry) / slDist : 99;
    return [
      item("window", "London 07:00–10:30 or overlap 13:00–16:00 (London time), not Friday after 14:00", "نافذة لندن أو التداخل مع نيويورك", !!win && !friday,
        friday ? "Friday after 14:00 London: no new trades" : win ? `${win.name} at ${fmtTime(signalTime)}` : `${fmtTime(signalTime)} is outside both windows`, W.window, true),
      item("daily", `Daily room >= ${cfg.dailyRoomPips} pips`, "مسافة كافية عن مستوى يومي", room >= cfg.dailyRoomPips,
        dailyRes ? `${dailyRes.label} ${f(dailyRes.price)} is ${room} pips away` : "No daily barrier in the way", 0, true),
      item("sl", `Stop ${cfg.risk.minSlPips}–${cfg.risk.maxSlPips} pips`, "وقف الخسارة بين 8 و 25 نقطة", slPips >= cfg.risk.minSlPips && slPips <= cfg.risk.maxSlPips,
        `SL ${f(sl)} = ${slPips} pips`, 0, true),
      item("rr", `R:R to TP2 >= 1:${cfg.risk.minRr}`, "عائد 1:2 على الأقل", rrTp2 >= cfg.risk.minRr - 1e-9, `TP2 ${f(tp2)} = 1:${rrTp2.toFixed(2)}`, W.rr, true, rrTp2 >= 3 ? 1 : 0.7),
      item("htf", "Room to the next H1 level", "مسافة حتى مستوى H1", htfR >= 1,
        htf ? `Next H1 ${buy ? "high" : "low"} ${f(htf.price)} = ${htfR.toFixed(1)}R away` : "No H1 level in the way", W.htfDistance, false, htfR >= 2 ? 1 : htfR >= 1 ? 0.6 : 0.2),
      item("volatility", "Normal volatility (ATR H1 vs 20-day average)", "تقلب طبيعي", vol.ratio >= 0.5 && vol.ratio <= 2.5,
        `ATR H1 ${pips(vol.now)} pips = ${(vol.ratio * 100).toFixed(0)}% of average`, W.volatility, false, vol.ratio >= 0.8 && vol.ratio <= 1.8 ? 1 : 0.5),
      item("news", "No high-impact EUR/USD news ±30 min", "لا أخبار قوية لليورو أو الدولار", !nb.blocked,
        nb.event ? `${nb.event.currency} ${nb.event.title} at ${fmtTime(nb.event.time)}` : "Clear", 0, true),
      item("spread", `Spread <= ${cfg.filters.maxSpreadPips} pips`, "السبريد مقبول", spreadPips <= cfg.filters.maxSpreadPips,
        `Spread ${spreadPips.toFixed(1)} pips${input.spread === null ? " (assumed, no live spread in feed)" : ""}`, 0, true),
      item("dailyLimit", `Max ${cfg.filters.maxTradesPerDay} trades / stop after ${cfg.filters.maxLossesPerDay} losses per day`, "حد الصفقات اليومي", dayOk,
        `${input.day.trades} trade(s), ${input.day.losses} loss(es) today`, 0, true),
    ];
  };

  const buildSetup = (id: string, kind: "A" | "B", dir: "BUY" | "SELL", idx: number, entry: number, structuralSl: number, tp2Hint: { price: number; label: string } | null, anchors: Record<string, unknown>): TradeSetup => {
    const buy = dir === "BUY";
    const atrSl = buy ? entry - cfg.risk.slAtrMult * atr15[idx] : entry + cfg.risk.slAtrMult * atr15[idx];
    const sl = roundTo(buy ? Math.min(structuralSl, atrSl) : Math.max(structuralSl, atrSl), d);
    const slDist = Math.abs(entry - sl);
    const tp1 = roundTo(buy ? entry + slDist * cfg.risk.tp1R : entry - slDist * cfg.risk.tp1R, d);
    let tp2: number;
    let tp2Source: string;
    if (tp2Hint) { tp2 = roundTo(tp2Hint.price, d); tp2Source = tp2Hint.label; }
    else {
      const lvl = nearestH1Target(swingsH1, levels, entry, buy, h1.length - 1, entry + (buy ? 1 : -1) * slDist * cfg.risk.minRr);
      tp2 = roundTo(lvl ? lvl.price : buy ? entry + slDist * cfg.risk.tp2R : entry - slDist * cfg.risk.tp2R, d);
      tp2Source = lvl ? `${lvl.label} (next H1 level)` : `${cfg.risk.tp2R}R`;
    }
    const tp3 = roundTo(buy ? entry + slDist * cfg.risk.tp3RefR : entry - slDist * cfg.risk.tp3RefR, d);
    const signalTime = m15[idx].time + 900;
    const trail = (i: number) => {
      const sw = [...swings15].reverse().find(s => s.kind === (buy ? "LOW" : "HIGH") && s.confirmedIndex <= i);
      return sw ? (buy ? sw.price - cfg.risk.slBufferPips * pip : sw.price + cfg.risk.slBufferPips * pip) : null;
    };
    const params = { side: dir, entryType: "MARKET" as const, entry, sl, tp1, tp2, tp3: null, expiryTime: null, marketFillTime: signalTime, cancelIfTp1BeforeFill: false, partials: cfg.risk.partials, spread, slippage };
    const lifecycle = simulateLifecycle(m15, { ...params, startIndex: idx + 1, trailLevel: trail });
    return {
      id, setup: kind, direction: dir, entryType: "MARKET", entry, sl, tp1, tp2, tp3, tp2Source,
      tp3Source: "Trail behind M15 swings (3R shown as reference)", rrTp2: rr(entry, sl, tp2), slDistance: roundTo(slDist, d),
      slPips: pips(slDist), lots: lotTable(spec, entry, sl, cfg.risk.riskPct, cfg.risk.balances), signalTime, signalIndex: idx,
      expiresAt: signalTime + cfg.risk.marketOrderValidMin * 60,
      invalidation: `M15 close ${buy ? "below" : "above"} ${f(sl)}; do not enter after ${fmtTime(signalTime + cfg.risk.marketOrderValidMin * 60)}`,
      isFresh: idx === last, lifecycle, params, anchors,
    };
  };

  const candidates: Candidate[] = [];
  let progressA = "";
  let progressB = "";
  const fibDrawing: Drawing[] = [];

  // ---- Setup A: trend pullback ----
  if (bias !== "NEUTRAL") {
    const buy = bias === "BULLISH";
    const leg = [...stH1.events].reverse().find(e => e.direction === bias);
    if (!leg) progressA = "No H1 impulse leg in the bias direction";
    else {
      const legStart = buy ? h1[leg.legStartIndex].low : h1[leg.legStartIndex].high;
      let legEnd = buy ? -Infinity : Infinity, legEndTime = 0;
      for (let i = leg.legStartIndex; i < h1.length; i++) {
        if (buy ? h1[i].high > legEnd : h1[i].low < legEnd) { legEnd = buy ? h1[i].high : h1[i].low; legEndTime = h1[i].time; }
      }
      const range = Math.abs(legEnd - legStart);
      const [f50, f618] = cfg.setupA.fib.map(r => (buy ? legEnd - r * range : legEnd + r * range));
      const fibTop = Math.max(f50, f618), fibBot = Math.min(f50, f618);
      fibDrawing.push(
        { id: `FIB-50-${leg.breakTime}`, layer: "fib", kind: "hline", tf: "H1", t1: h1[leg.legStartIndex].time, t2: null, p1: f50, text: "0.5", color: "gold", style: "dotted" },
        { id: `FIB-618-${leg.breakTime}`, layer: "fib", kind: "hline", tf: "H1", t1: h1[leg.legStartIndex].time, t2: null, p1: f618, text: "0.618", color: "gold", style: "dotted" },
        { id: `FIB-Z-${leg.breakTime}`, layer: "fib", kind: "box", tf: "H1", t1: legEndTime, t2: null, p1: fibTop, p2: fibBot, text: "Fib 50–61.8", color: "gold", faded: true },
      );
      const ob: OrderBlock | undefined = [...obsH1].reverse().find(o => o.direction === bias && o.state !== "BROKEN");
      if (pips(range) < cfg.setupA.minLegPips) progressA = `H1 impulse leg only ${pips(range)} pips`;

      for (let idx = last; idx >= Math.max(cfg.setupA.pullbackBars, last - cfg.setupA.lookbackBars) && pips(range) >= cfg.setupA.minLegPips; idx--) {
        const c = m15[idx], p = m15[idx - 1];
        if (c.time < legEndTime) break; // pullback must come after the impulse high/low
        let pbIdx = idx;
        for (let i = idx - cfg.setupA.pullbackBars + 1; i <= idx; i++) if (buy ? m15[i].low < m15[pbIdx].low : m15[i].high > m15[pbIdx].high) pbIdx = i;
        const pbExtreme = buy ? m15[pbIdx].low : m15[pbIdx].high;
        const tol = cfg.setupA.fibTolerance * range;
        const fibHit = buy ? pbExtreme <= fibTop && pbExtreme >= fibBot - tol : pbExtreme >= fibBot && pbExtreme <= fibTop + tol;
        const obHit = !!ob && (buy ? pbExtreme <= ob.top && c.close >= ob.bottom : pbExtreme >= ob.bottom && c.close <= ob.top);
        let emaHit = false;
        for (let i = idx - cfg.setupA.pullbackBars + 1; i <= idx; i++) if (m15[i].low <= ema50m15[i] && m15[i].high >= ema50m15[i]) emaHit = true;
        const confl = [fibHit, obHit, emaHit].filter(Boolean).length;
        if (confl < cfg.setupA.minConfluence) { if (idx === last) progressA = `Pullback touches ${confl}/3 zones (Fib ${fibHit ? "✓" : "✗"}, H1 OB ${obHit ? "✓" : "✗"}, EMA50 ${emaHit ? "✓" : "✗"})`; continue; }

        const engulf = buy ? p.close < p.open && c.close > c.open && c.close >= p.open && c.open <= p.close
                           : p.close > p.open && c.close < c.open && c.close <= p.open && c.open >= p.close;
        const b = Math.max(body(c), pip * 0.1);
        const lowerWick = Math.min(c.open, c.close) - c.low, upperWick = c.high - Math.max(c.open, c.close);
        const pin = buy ? lowerWick >= cfg.setupA.pinWickBody * b && c.close >= (c.high + c.low) / 2
                        : upperWick >= cfg.setupA.pinWickBody * b && c.close <= (c.high + c.low) / 2;
        const choch = st15.events.some(e => e.breakIndex === idx && e.direction === bias && e.type === "CHOCH");
        if (!engulf && !pin && !choch) { if (idx === last) progressA = `In zone (${confl}/3), waiting for an engulfing / pin bar / M15 CHoCH`; continue; }

        const rsiV = rsi15[pbIdx];
        const [rLo, rHi] = buy ? cfg.setupA.rsiBuy : cfg.setupA.rsiSell;
        const entry = roundTo(c.close, d);
        const zoneEdge = buy ? Math.min(pbExtreme, obHit && ob ? ob.bottom : Infinity, fibHit ? fibBot : Infinity) : Math.max(pbExtreme, obHit && ob ? ob.top : -Infinity, fibHit ? fibTop : -Infinity);
        const structuralSl = buy ? zoneEdge - cfg.risk.slBufferPips * pip : zoneEdge + cfg.risk.slBufferPips * pip;
        const dir = buy ? "BUY" : "SELL";
        const setup = buildSetup(`EURUSD-A-${c.time}`, "A", dir, idx, entry, structuralSl, null, {
          leg: { start: legStart, end: legEnd, fib50: f50, fib618: f618 }, ob: ob ? { top: ob.top, bottom: ob.bottom } : null,
          ema50: ema50m15[idx], pullback: pbExtreme, trigger: engulf ? "Engulfing" : pin ? "Pin bar" : "M15 CHoCH",
        });
        const checklist = [
          item("bias", "H4 trend: close vs EMA200, EMA50 vs EMA200, HH/HL structure", "اتجاه H4 واضح", true, biasDetail, W.bias, true),
          item("zone", `Pullback into >= ${cfg.setupA.minConfluence} of: H1 OB, Fib 50–61.8%, EMA50 M15`, "رجوع لمنطقة توافق", true,
            `Fib ${fibHit ? "✓" : "✗"} (${f(fibBot)}–${f(fibTop)}), H1 OB ${obHit ? "✓" : "✗"}${ob ? ` (${f(ob.bottom)}–${f(ob.top)})` : ""}, EMA50 ${emaHit ? "✓" : "✗"}; pullback ${f(pbExtreme)}`,
            W.zone, true, confl / 3),
          item("momentum", `RSI(14, M15) at the pullback ${rLo}–${rHi}`, "RSI في المجال المطلوب", rsiV >= rLo && rsiV <= rHi, `RSI ${rsiV.toFixed(1)}`, W.momentum, true),
          item("trigger", "Confirmation: engulfing, pin bar or M15 CHoCH", "شمعة تأكيد", true,
            `${engulf ? "Engulfing" : pin ? "Pin bar" : "M15 CHoCH"} closed at ${f(c.close)} (${fmtTime(c.time + 900)})`, W.trigger, true, choch ? 1 : engulf ? 0.9 : 0.8),
          ...commonChecks(setup.signalTime, dir, entry, setup.sl, setup.tp2, setup.slDistance),
        ];
        candidates.push({ setup, checklist, score: scoreChecklist(checklist), requiredOk: checklist.every(x => !x.required || x.passed) });
        break;
      }
      if (!candidates.length && !progressA) progressA = "Waiting for a pullback into the confluence zone";
    }
  } else progressA = "H4 trend not clear: no trade";

  // ---- Setup B: Asian range false breakout ----
  if (asia?.complete) {
    const rangePips = pips(asia.high - asia.low);
    const asiaLevels: Level[] = [
      { id: `ASIA_H-${asia.dateKey}`, kind: "ASIA_H", label: "Asia H", price: asia.high, side: "HIGH", time: asia.startSec, availableFrom: asia.endSec, weight: 1 },
      { id: `ASIA_L-${asia.dateKey}`, kind: "ASIA_L", label: "Asia L", price: asia.low, side: "LOW", time: asia.startSec, availableFrom: asia.endSec, weight: 1 },
    ];
    const london = cfg.sessions.windows[0];
    const sweeps = findSweeps(m15, asiaLevels, 0, last, lastValue(atr15)).filter(s => inLocalWindow(s.time, london.tz, london.start, london.end));
    const rangeOk = rangePips >= cfg.setupB.minRangePips && rangePips <= cfg.setupB.maxRangePips;
    if (!rangeOk) progressB = `Asian range ${rangePips} pips (needs ${cfg.setupB.minRangePips}–${cfg.setupB.maxRangePips})`;
    else if (!sweeps.length) progressB = `Asian range ${rangePips} pips, waiting for a false breakout in the London window`;
    for (const sw of rangeOk ? sweeps.reverse() : []) {
      const dir = sw.level.side === "HIGH" ? "SELL" : "BUY";
      const needBias = dir === "BUY" ? "BULLISH" : "BEARISH";
      const c = m15[sw.index];
      const entry = roundTo(c.close, d);
      const structuralSl = dir === "BUY" ? sw.extreme - cfg.risk.slBufferPips * pip : sw.extreme + cfg.risk.slBufferPips * pip;
      const opposite = dir === "BUY" ? asia.high : asia.low;
      const setup = buildSetup(`EURUSD-B-${c.time}`, "B", dir, sw.index, entry, structuralSl, { price: opposite, label: `Asian range ${dir === "BUY" ? "high" : "low"}` }, { sweep: sw, asia: { high: asia.high, low: asia.low } });
      const checklist = [
        item("bias", `H4 bias ${needBias.toLowerCase()} (trade only with the trend)`, "توافق مع اتجاه H4", bias === needBias, biasDetail, W.bias, true),
        item("zone", `Asian range ${cfg.setupB.minRangePips}–${cfg.setupB.maxRangePips} pips`, "نطاق آسيا مناسب", true, `Asian range ${f(asia.low)}–${f(asia.high)} = ${rangePips} pips`, W.zone, true, 1),
        item("trigger", "False breakout: wick beyond the Asian range, close back inside", "اختراق كاذب لنطاق آسيا", true,
          `${sw.level.label} ${f(sw.level.price)} taken to ${f(sw.extreme)}, closed back inside at ${f(c.close)} (${fmtTime(c.time + 900)})`, W.trigger, true, sw.depthAtr <= 1.5 ? 1 : 0.7),
        item("momentum", "Breakout failed on the first candle that took the level", "فشل الاختراق من أول شمعة", true, `${pips(Math.abs(sw.extreme - sw.level.price))} pips beyond the range`, W.momentum, false, 1),
        ...commonChecks(setup.signalTime, dir, entry, setup.sl, setup.tp2, setup.slDistance),
      ];
      candidates.push({ setup, checklist, score: scoreChecklist(checklist), requiredOk: checklist.every(x => !x.required || x.passed) });
      break;
    }
  } else progressB = "Asian range not complete yet";

  // ---- Pick: valid candidates first, then the higher score, then the newer one ----
  candidates.sort((a, b) => Number(b.requiredOk) - Number(a.requiredOk) || b.score - a.score || b.setup.signalTime - a.setup.signalTime);
  const best = candidates[0];
  if (best) {
    result.setup = best.setup;
    result.checklist = best.checklist;
    result.score = best.score;
    const failedItems = best.checklist.filter(c => c.required && !c.passed);
    result.rejection = failedItems.length ? `${failedItems[0].rule}: ${failedItems[0].detail}` : null;
    result.status = classify(best.score, best.requiredOk, cfg.scoring.thresholds);
    if (result.status === "SIGNAL") result.signal = toSignalJson(spec, cfg.strategy, best.setup, best.score, cfg.timeframes, best.checklist);
    result.canNotify = result.status === "SIGNAL" && best.setup.isFresh && input.isMarketOpen;
  } else {
    result.checklist = [
      item("bias", "H4 trend: close vs EMA200, EMA50 vs EMA200, HH/HL structure", "اتجاه H4 واضح", bias !== "NEUTRAL", biasDetail, W.bias, true),
      item("setupA", "Setup A: pullback into confluence + confirmation", "الإعداد A", false, progressA || "Not found", 0, true),
      item("setupB", "Setup B: Asian range false breakout", "الإعداد B", false, progressB || "Not found", 0, false),
    ];
    result.rejection = bias === "NEUTRAL" ? "H4 trend not clear" : progressA || progressB;
  }

  // ---- Drawings ----
  const max = cfg.drawings.maxPerType;
  const sessions: SessionRange[] = [];
  for (const off of [1, 0]) {
    const key = localDateKey(now - off * 86400, LONDON_TZ(cfg));
    const a = sessionRange(m15, 900, "Asia", key, cfg.sessions.asia.tz, cfg.sessions.asia.start, cfg.sessions.asia.end, now);
    if (a) sessions.push(a);
    cfg.sessions.windows.forEach((w, i) => {
      const r = sessionRange(m15, 900, i === 0 ? "London" : "NY", key, w.tz, w.start, w.end, now);
      if (r) sessions.push(r);
    });
  }
  const drawings: Drawing[] = [
    ...sessionDrawings(sessions),
    ...levelDrawings(levels),
    ...fibDrawing,
    ...structureDrawings(stH1.events, "H1", "M15", 3),
    ...structureDrawings(st15.events, "M15", "M15", max),
    ...swingDrawings(swings15, "M15", max),
    ...obDrawings(obsH1, "H1", "M15", 3),
    ...fvgDrawings(fvgsH1, "H1", "M15", 3),
  ];
  if (asia?.complete) {
    const asiaLv: Level[] = [
      { id: `ASIA_H-${asia.dateKey}`, kind: "ASIA_H", label: "Asia H", price: asia.high, side: "HIGH", time: asia.startSec, availableFrom: asia.endSec, weight: 1 },
      { id: `ASIA_L-${asia.dateKey}`, kind: "ASIA_L", label: "Asia L", price: asia.low, side: "LOW", time: asia.startSec, availableFrom: asia.endSec, weight: 1 },
    ];
    drawings.push(...sweepDrawings(findSweeps(m15, asiaLv, 0, last, lastValue(atr15)), "M15", max));
  }
  if (result.setup) drawings.push(...tradeDrawings(result.setup, "M15", `${result.setup.lots["1000$"] ?? 0} lot / $1k`));
  result.drawings = declutterZones(drawings);

  result.facts = {
    price, spreadPips: roundTo(spread / pip, 1), atrM15Pips: pips(lastValue(atr15)), atrH1Pips: pips(vol.now), volatilityRatio: roundTo(vol.ratio, 2),
    bias: { h4Close, ema50: roundTo(e50, d), ema200: roundTo(e200, d), h4Structure: h4Struct, direction: bias },
    window: result.market.window ?? "none",
    asianRange: asia ? { high: asia.high, low: asia.low, pips: pips(asia.high - asia.low), complete: asia.complete } : null,
    levels: levels.map(l => ({ kind: l.kind, price: l.price })),
    h1Structure: stH1.events.slice(-3).map(e => ({ type: e.type, direction: e.direction, level: e.level, time: e.breakTime })),
    m15Structure: st15.events.slice(-4).map(e => ({ type: e.type, direction: e.direction, level: e.level, time: e.breakTime })),
    orderBlocksH1: obsH1.filter(o => o.state !== "BROKEN").slice(-3).map(o => ({ direction: o.direction, top: o.top, bottom: o.bottom, state: o.state })),
    ema50M15: roundTo(lastValue(ema50m15), d),
    rsiM15: roundTo(lastValue(rsi15), 1),
    progress: { setupA: progressA, setupB: progressB },
  };

  const s = result.setup;
  result.headline = !s ? (bias === "NEUTRAL" ? "H4 trend not clear: no trade" : progressA || progressB || "No setup")
    : result.status === "SIGNAL" ? `${s.direction} (Setup ${s.setup}) at ${f(s.entry)} · score ${result.score}`
    : result.status === "WATCH" ? `${s.direction} Setup ${s.setup} watch · score ${result.score}`
    : result.status === "IGNORE" ? `Setup ${s.setup} scored ${result.score}: ignored`
    : `Setup ${s.setup} rejected: ${result.checklist.find(c => c.required && !c.passed)?.rule}`;
  result.headlineAr = s ? (result.status === "SIGNAL" ? `إشارة ${s.direction} (الإعداد ${s.setup})` : "إعداد موجود لكنه غير مكتمل الشروط") : "لا توجد صفقة حالياً";
  return result;
}

const LONDON_TZ = (cfg: EurConfig) => cfg.sessions.asia.tz;

/** Nearest daily barrier in the trade direction: untaken daily swing or PWH/PWL. */
function nearestDailyBarrier(swingsD1: Swing[], levels: Level[], entry: number, buy: boolean, uptoIndex: number): { price: number; label: string } | null {
  const pool: { price: number; label: string }[] = [];
  const sw = nearestSwingBeyond(swingsD1, entry, buy, uptoIndex);
  if (sw) pool.push({ price: sw.price, label: buy ? "Daily resistance" : "Daily support" });
  for (const l of levels) if ((buy ? l.kind === "PWH" && l.price > entry : l.kind === "PWL" && l.price < entry)) pool.push({ price: l.price, label: l.label });
  pool.sort((a, b) => (buy ? a.price - b.price : b.price - a.price));
  return pool[0] || null;
}

/** Nearest H1 target beyond `minPrice` (untaken H1 swing, PDH/PDL, PWH/PWL). */
function nearestH1Target(swingsH1: Swing[], levels: Level[], entry: number, buy: boolean, uptoIndex: number, minPrice: number): { price: number; label: string } | null {
  const pool: { price: number; label: string }[] = [];
  for (const s of swingsH1) {
    if (s.kind !== (buy ? "HIGH" : "LOW") || s.confirmedIndex > uptoIndex || (s.takenIndex !== null && s.takenIndex <= uptoIndex)) continue;
    pool.push({ price: s.price, label: buy ? "H1 swing high" : "H1 swing low" });
  }
  for (const l of levels) if (buy ? l.side === "HIGH" : l.side === "LOW") pool.push({ price: l.price, label: l.label });
  return pool.filter(p => (buy ? p.price >= minPrice : p.price <= minPrice)).sort((a, b) => (buy ? a.price - b.price : b.price - a.price))[0] || null;
}

export type { Candle };
