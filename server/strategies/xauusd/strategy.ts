/**
 * XAUUSD (Gold) — "Liquidity Sweep + MSS + FVG"
 *
 * Bias (H4 + H1): bullish if H1 close > EMA200(H1) AND the last H4 structure break is bullish;
 * bearish mirror; disagreement = no trade.
 * Kill zones: London 08:00–11:00 London time, New York 08:30–11:30 New York time.
 * Sequence (M5, all required, in order):
 *   1. Sweep of a key level against the bias (Asian low/PDL/PWL/EQL/round number for buys).
 *   2. Within 6 M5 candles: MSS/CHoCH in the bias direction with displacement (body > 1.5× avg body 20).
 *   3. The displacement leaves an FVG (else an OB).
 *   4. LIMIT entry at FVG 50% (or OB 50%).
 * Risk: SL beyond the sweep wick + 0.2 × ATR(14, M5) + spread, $2–$8. TP1 = 1R (50%, SL to BE),
 * TP2 = nearest opposing liquidity (min 1:2), TP3 = next H1 level or 3R. Pending order expires
 * after 45 minutes or when TP1 trades first.
 */

import { closedOnly, roundTo } from "../shared/types";
import { atrSeries, avgBodySeries, emaSeries, lastValue } from "../shared/indicators";
import { detectStructure, detectSwings, StructureEvent } from "../shared/structure";
import { detectFvgs, detectOrderBlocks, Fvg, OrderBlock } from "../shared/zones";
import { localDateKey, sessionRange, SessionRange } from "../shared/sessions";
import { dailyWeeklyLevels, equalLevels, findSweeps, Level, roundNumberLevels, Sweep } from "../shared/liquidity";
import { newsBlock } from "../shared/news";
import { classify, lotTable, rr, scoreChecklist, toPips } from "../shared/risk";
import { simulateLifecycle } from "../shared/lifecycle";
import { StrategyInput } from "../shared/input";
import { Drawing, StrategyResult, TradeSetup } from "../shared/result";
import { activeWindow, fmtTime, isUntaken, item, nearestSwingBeyond, toSignalJson, volatilityRatio } from "../shared/common";
import { declutterZones, fvgDrawings, levelDrawings, obDrawings, sessionDrawings, structureDrawings, sweepDrawings, swingDrawings, tradeDrawings } from "../shared/drawings";
import { XAU_CONFIG, XauConfig } from "./config";

export function evaluateXauusd(input: StrategyInput, cfg: XauConfig = XAU_CONFIG): StrategyResult {
  const spec = cfg.spec;
  const d = spec.decimals;
  const f = (v: number) => v.toFixed(d);
  const now = input.nowSec;
  const m5 = closedOnly(input.candles.M5 || [], 300, now).slice(-600);
  const m15 = closedOnly(input.candles.M15 || [], 900, now).slice(-900);
  const h1 = closedOnly(input.candles.H1 || [], 3600, now).slice(-800);
  const h4 = closedOnly(input.candles.H4 || [], 14400, now).slice(-300);
  const last = m5.length - 1;
  const price = input.livePrice > 0 ? input.livePrice : m5[last]?.close ?? 0;
  const spread = input.spread ?? cfg.filters.assumedSpread;
  const S = cfg.structure;

  const result: StrategyResult = {
    symbol: spec.symbol,
    displaySymbol: spec.displaySymbol,
    strategy: cfg.strategy,
    strategyName: cfg.name,
    timeframes: cfg.timeframes,
    nowSec: now,
    price,
    spec,
    dataQuality: { ok: true, reason: "Live data OK", source: input.dataSource },
    market: { isOpen: input.isMarketOpen, window: null },
    bias: { direction: "NEUTRAL", detail: "" },
    status: "NO_TRADE",
    score: 0,
    checklist: [],
    rejection: null,
    headline: "",
    headlineAr: "",
    setup: null,
    signal: null,
    canNotify: false,
    news: { blocked: false, detail: "", next: null, source: input.news.source },
    day: input.day,
    drawings: [],
    facts: {},
  };

  // ---- Data quality ----
  const stale = input.isMarketOpen && m5.length > 0 && now - (m5[last].time + 300) > 3 * 300;
  if (!input.isRealData || m5.length < 150 || h1.length < cfg.bias.emaPeriod + 20 || h4.length < 40 || stale) {
    result.dataQuality = {
      ok: false,
      source: input.dataSource,
      reason: !input.isRealData ? "Live feed unavailable (synthetic candles): no analysis"
        : stale ? "Last M5 candle is stale (feed paused)"
        : `Not enough history (M5 ${m5.length}, H1 ${h1.length}, H4 ${h4.length})`,
    };
    return finish(result, "Data not usable", "البيانات غير صالحة");
  }

  // ---- Detectors ----
  const atr5 = atrSeries(m5, cfg.atrPeriod);
  const atrNow5 = lastValue(atr5);
  const swings5 = detectSwings(m5, S.swingN);
  const st5 = detectStructure(m5, swings5, avgBodySeries(m5, S.avgBodyPeriod), S.displacementMult);
  const fvgs5 = detectFvgs(m5, atr5, cfg.fvgMinAtr, "M5");
  const obs5 = detectOrderBlocks(m5, st5.events, "M5");

  const atrH1 = atrSeries(h1, cfg.atrPeriod);
  const swingsH1 = detectSwings(h1, S.htfSwingN);
  const stH1 = detectStructure(h1, swingsH1, avgBodySeries(h1, S.avgBodyPeriod), S.displacementMult);
  const fvgsH1 = detectFvgs(h1, atrH1, cfg.fvgMinAtr, "H1");
  const obsH1 = detectOrderBlocks(h1, stH1.events, "H1");
  const swingsH4 = detectSwings(h4, S.htfSwingN);
  const stH4 = detectStructure(h4, swingsH4, avgBodySeries(h4, S.avgBodyPeriod), S.displacementMult);

  // ---- Bias ----
  const ema200 = lastValue(emaSeries(h1.map(x => x.close), cfg.bias.emaPeriod));
  const h1Close = h1[h1.length - 1].close;
  const h1Dir = h1Close > ema200 ? "BULLISH" : "BEARISH";
  const lastH4 = stH4.events[stH4.events.length - 1];
  const h4Dir = lastH4?.direction ?? "NEUTRAL";
  const bias = h1Dir === h4Dir ? h1Dir : "NEUTRAL";
  const biasDetail = `H1 close ${f(h1Close)} ${h1Close > ema200 ? ">" : "<"} EMA200 ${f(ema200)} · H4 last ${lastH4 ? `${lastH4.type} ${lastH4.direction.toLowerCase()} at ${f(lastH4.level)}` : "break: none"}`;
  result.bias = { direction: bias, detail: biasDetail };

  // ---- Levels ----
  const todayKey = localDateKey(now, cfg.sessions.asia.tz);
  const asia = sessionRange(m5, 300, "Asia", todayKey, cfg.sessions.asia.tz, cfg.sessions.asia.start, cfg.sessions.asia.end, now);
  const londonKz = cfg.sessions.killzones[0];
  const londonRange = sessionRange(m5, 300, "London", todayKey, londonKz.tz, londonKz.start, londonKz.end, now);
  const levels: Level[] = [...dailyWeeklyLevels(m15)];
  if (asia?.complete) {
    levels.push({ id: `ASIA_H-${asia.dateKey}`, kind: "ASIA_H", label: "Asia H", price: asia.high, side: "HIGH", time: asia.startSec, availableFrom: asia.endSec, weight: 0.9 });
    levels.push({ id: `ASIA_L-${asia.dateKey}`, kind: "ASIA_L", label: "Asia L", price: asia.low, side: "LOW", time: asia.startSec, availableFrom: asia.endSec, weight: 0.9 });
  }
  if (londonRange?.complete) {
    levels.push({ id: `PSH-${londonRange.dateKey}`, kind: "PSH", label: "London H", price: londonRange.high, side: "HIGH", time: londonRange.startSec, availableFrom: londonRange.endSec, weight: 0.8 });
    levels.push({ id: `PSL-${londonRange.dateKey}`, kind: "PSL", label: "London L", price: londonRange.low, side: "LOW", time: londonRange.startSec, availableFrom: londonRange.endSec, weight: 0.8 });
  }
  const recentStart = m5[Math.max(0, last - cfg.setup.sweepLookbackBars * 3)].time;
  levels.push(...equalLevels(swings5, atrNow5, cfg.equalLevelTolAtr, last).filter(l => l.time >= recentStart));
  if (cfg.roundNumbers.enabled) levels.push(...roundNumberLevels(price, cfg.roundNumbers.steps, cfg.roundNumbers.count, m5[0].time));

  // ---- Filters (evaluated for every state) ----
  const vol = volatilityRatio(atrH1, cfg.filters.volatility.lookbackBars);
  const news = newsBlock(now, input.news.events, cfg.filters.news);
  result.news = {
    blocked: news.blocked,
    detail: news.event ? `${news.event.currency} ${news.event.title} at ${fmtTime(news.event.time)}` : "No high-impact USD news within ±30 min",
    next: news.next ? `${news.next.currency} ${news.next.title} ${new Date(news.next.time * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC` : null,
    source: input.news.source,
  };
  const win = activeWindow(now, cfg.sessions.killzones);
  result.market.window = win?.name ?? null;

  // ---- Setup search ----
  const W = cfg.scoring.weights;
  const checklist: ReturnType<typeof item>[] = [];
  checklist.push(item("bias", "H4 and H1 bias agree", "توافق اتجاه H4 و H1", bias !== "NEUTRAL", biasDetail, W.bias, true));

  let setup: TradeSetup | null = null;
  let progress = bias === "NEUTRAL" ? "H4 and H1 disagree: no trade" : "";
  let chosen: { sweep: Sweep; mss: StructureEvent; poi: { kind: "FVG" | "OB"; zone: Fvg | OrderBlock }; readyIdx: number } | null = null;

  if (bias !== "NEUTRAL") {
    const buy = bias === "BULLISH";
    const sweepable = levels.filter(l => l.side === (buy ? "LOW" : "HIGH") && cfg.setup.sweepKinds.includes(l.kind));
    const sweeps = findSweeps(m5, sweepable, Math.max(0, last - cfg.setup.sweepLookbackBars), last, atrNow5).reverse();
    if (!sweeps.length) progress = `Waiting for a sweep of ${buy ? "sell-side (Asia L / PDL / EQL)" : "buy-side (Asia H / PDH / EQH)"} liquidity`;

    for (const sw of sweeps) {
      const mss = st5.events.find(e => e.direction === bias && e.breakIndex > sw.index && e.breakIndex <= sw.index + cfg.setup.maxBarsSweepToMss);
      if (!mss) { progress ||= `Sweep of ${sw.level.label} ${f(sw.level.price)} at ${fmtTime(sw.time)}, waiting for an M5 MSS within ${cfg.setup.maxBarsSweepToMss} candles`; if (last - sw.index <= cfg.setup.maxBarsSweepToMss) break; continue; }
      let protectedOk = true;
      for (let i = sw.index + 1; i <= mss.breakIndex; i++) if (buy ? m5[i].low < sw.extreme : m5[i].high > sw.extreme) protectedOk = false;
      if (!protectedOk) { progress ||= `Sweep low/high at ${f(sw.extreme)} was broken before the MSS`; continue; }
      if (mss.displacementIndex === null || mss.displacementIndex <= sw.index) { progress ||= `MSS at ${fmtTime(mss.breakTime)} has no displacement (body ${mss.displacementMult.toFixed(2)}× avg < ${S.displacementMult}×)`; continue; }

      const breakTime = m5[mss.breakIndex].time;
      const fvg = fvgs5
        .filter(z => z.direction === bias && z.createdIndex > sw.index && z.createdIndex <= mss.breakIndex + 2 && !(z.filledTime !== null && z.filledTime <= breakTime))
        .sort((a, b) => (buy ? a.bottom - b.bottom : b.top - a.top))[0];
      const ob = obs5.find(o => o.breakTime === mss.breakTime && o.state !== "BROKEN");
      if (!fvg && !ob) { progress ||= `MSS at ${fmtTime(mss.breakTime)} left no FVG or order block`; continue; }
      const readyIdx = fvg ? Math.max(mss.breakIndex, fvg.createdIndex) : mss.breakIndex;
      if (readyIdx > last) { progress ||= "Waiting for the FVG candle to close"; break; }
      chosen = { sweep: sw, mss, poi: fvg ? { kind: "FVG", zone: fvg } : { kind: "OB", zone: ob! }, readyIdx };
      break;
    }

    if (chosen) {
      const { sweep: sw, mss, poi, readyIdx } = chosen;
      const zone = poi.zone;
      const entry = roundTo(poi.kind === "FVG" ? (zone as Fvg).ce : (zone as OrderBlock).mid, d);
      const buffer = cfg.risk.slAtrBuffer * (atr5[readyIdx] || atrNow5) + spread;
      const sl = roundTo(buy ? sw.extreme - buffer : sw.extreme + buffer, d);
      const slDist = Math.abs(entry - sl);
      const tp1 = roundTo(buy ? entry + cfg.risk.tp1R * slDist : entry - cfg.risk.tp1R * slDist, d);
      const targets = levels
        .filter(l => l.side === (buy ? "HIGH" : "LOW") && cfg.setup.targetKinds.includes(l.kind))
        .filter(l => (buy ? l.price > entry : l.price < entry) && isUntaken(l, m5, readyIdx))
        .sort((a, b) => (buy ? a.price - b.price : b.price - a.price));
      const tgt = targets[0];
      const tp2 = roundTo(tgt ? tgt.price : buy ? entry + cfg.risk.minRrTp2 * slDist : entry - cfg.risk.minRrTp2 * slDist, d);
      const rrTp2 = rr(entry, sl, tp2);
      const h1Next = nearestSwingBeyond(swingsH1, tp2, buy, h1.length - 1);
      let tp3 = roundTo(h1Next ? h1Next.price : buy ? entry + cfg.risk.tp3R * slDist : entry - cfg.risk.tp3R * slDist, d);
      if (buy ? tp3 <= tp2 : tp3 >= tp2) tp3 = roundTo(buy ? tp2 + slDist : tp2 - slDist, d);
      const signalTime = m5[readyIdx].time + 300;
      const expiresAt = signalTime + cfg.risk.orderExpiryMin * 60;
      const params = {
        side: (buy ? "BUY" : "SELL") as "BUY" | "SELL", entryType: "LIMIT" as const, entry, sl, tp1, tp2, tp3,
        expiryTime: expiresAt, cancelIfTp1BeforeFill: cfg.risk.cancelIfTp1First, partials: cfg.risk.partials,
        spread, slippage: cfg.filters.slippage,
      };
      const lifecycle = simulateLifecycle(m5, { ...params, startIndex: readyIdx + 1 });
      setup = {
        id: `XAUUSD-${sw.time}-${mss.breakTime}`,
        setup: "GOLD",
        direction: buy ? "BUY" : "SELL",
        entryType: "LIMIT",
        entry, sl, tp1, tp2, tp3,
        tp2Source: tgt ? `${tgt.label} (opposing liquidity)` : `${cfg.risk.minRrTp2}R (no opposing liquidity in range)`,
        tp3Source: h1Next ? "Next H1 swing level" : `${cfg.risk.tp3R}R`,
        rrTp2,
        slDistance: roundTo(slDist, d),
        slPips: toPips(spec, slDist),
        lots: lotTable(spec, entry, sl, cfg.risk.riskPct, cfg.risk.balances),
        signalTime,
        signalIndex: readyIdx,
        expiresAt,
        invalidation: `M5 close ${buy ? "below" : "above"} ${f(sl)} before entry, order not filled by ${fmtTime(expiresAt)}, or TP1 ${f(tp1)} reached first`,
        isFresh: readyIdx === last,
        lifecycle,
        params,
        anchors: { sweep: sw, mss, poi: { kind: poi.kind, top: (zone as Fvg).top, bottom: (zone as Fvg).bottom, time: poi.kind === "FVG" ? (zone as Fvg).startTime : (zone as OrderBlock).time } },
      };

      // ---- Checklist (in rule order) ----
      const sigWin = activeWindow(signalTime - 1, cfg.sessions.killzones);
      checklist.push(item("killzone", "Inside a kill zone (London 08:00–11:00 / NY 08:30–11:30)", "داخل نافذة السيولة (لندن / نيويورك)", sigWin !== null,
        sigWin ? `${sigWin.name} at ${fmtTime(signalTime)}` : `Setup completed at ${fmtTime(signalTime)}, outside both kill zones`, W.killzone, true));
      const depthQ = sw.depthAtr < 0.05 ? 0.6 : sw.depthAtr > 1.5 ? 0.7 : 1;
      checklist.push(item("sweep", "Liquidity sweep against the bias", "سحب سيولة عكس الاتجاه", true,
        `${sw.level.label} ${f(sw.level.price)} swept at ${fmtTime(sw.time)}, wick ${f(sw.extreme)} (${sw.depthAtr.toFixed(2)}× ATR), closed back inside`, W.sweep, true, sw.level.weight * depthQ));
      checklist.push(item("mss", `M5 MSS within ${cfg.setup.maxBarsSweepToMss} candles with displacement > ${S.displacementMult}× avg body`, "كسر هيكلي M5 مع اندفاع", true,
        `${mss.type === "CHOCH" ? "CHoCH" : "BOS"} close beyond ${f(mss.level)} at ${fmtTime(mss.breakTime + 300)}, ${mss.breakIndex - sw.index} candles after the sweep, displacement ${mss.displacementMult.toFixed(2)}× avg body`,
        W.displacement, true, 0.5 + (mss.displacementMult - S.displacementMult) / 3));
      const poiTop = (zone as Fvg).top, poiBottom = (zone as Fvg).bottom;
      checklist.push(item("poi", "Displacement left an FVG (else an OB)", "فجوة FVG أو بلوك أوامر", true,
        `${poi.kind} ${f(poiBottom)}–${f(poiTop)}, limit at 50% ${f(entry)}`, W.poi, true, poi.kind === "FVG" ? ((zone as Fvg).sizeAtr >= 0.5 ? 1 : 0.8) : 0.7));
      checklist.push(item("sl", `Stop $${cfg.risk.minSl}–$${cfg.risk.maxSl} beyond the sweep wick`, "وقف خسارة بين 2 و 8 دولار", slDist >= cfg.risk.minSl && slDist <= cfg.risk.maxSl,
        `SL ${f(sl)} = $${slDist.toFixed(2)} (wick ${f(sw.extreme)} + 0.2× ATR + spread)`, 0, true));
      checklist.push(item("rr", `R:R to TP2 >= 1:${cfg.risk.minRrTp2}`, "عائد للهدف الثاني 1:2 على الأقل", rrTp2 >= cfg.risk.minRrTp2,
        `TP2 ${f(tp2)} = ${setup.tp2Source}, 1:${rrTp2.toFixed(2)}`, W.rr, true, rrTp2 >= 3 ? 1 : 0.7));
      const htf = nearestSwingBeyond(swingsH1, entry, buy, h1.length - 1);
      const htfR = htf ? Math.abs(htf.price - entry) / slDist : 99;
      checklist.push(item("htf", "Room to the next H1 level", "مسافة كافية حتى مستوى H1", htfR >= 1,
        htf ? `Next H1 ${buy ? "high" : "low"} ${f(htf.price)} = ${htfR.toFixed(1)}R away` : "No H1 level in the way", W.htfDistance, false, htfR >= 2 ? 1 : htfR >= 1 ? 0.6 : 0.2));
    } else {
      checklist.push(item("setup", "Sweep → MSS → FVG sequence", "تسلسل سحب السيولة ← كسر الهيكل ← FVG", false, progress || "No setup in the lookback window", 0, true));
    }
  }

  const volOk = vol.ratio >= cfg.filters.volatility.min && vol.ratio <= cfg.filters.volatility.max;
  checklist.push(item("volatility", `ATR(14,H1) between ${cfg.filters.volatility.min * 100}% and ${cfg.filters.volatility.max * 100}% of its 20-day average`, "التقلب في المجال الطبيعي", volOk,
    `ATR H1 ${vol.now.toFixed(2)} = ${(vol.ratio * 100).toFixed(0)}% of 20-day average ${vol.avg.toFixed(2)}`, W.volatility, true, vol.ratio >= 0.8 && vol.ratio <= 1.8 ? 1 : 0.6));
  checklist.push(item("news", "No high-impact USD news ±30 min", "لا أخبار قوية للدولار ±30 دقيقة", !news.blocked, result.news.detail, 0, true));
  checklist.push(item("spread", `Spread <= $${cfg.filters.maxSpread}`, "السبريد مقبول", spread <= cfg.filters.maxSpread,
    `Spread $${spread.toFixed(2)}${input.spread === null ? " (assumed, no live spread in feed)" : ""}`, 0, true));
  const dayOk = input.day.trades < cfg.filters.maxTradesPerDay && input.day.losses < cfg.filters.maxLossesPerDay;
  checklist.push(item("daily", `Max ${cfg.filters.maxTradesPerDay} trades / stop after ${cfg.filters.maxLossesPerDay} losses per day`, "حد الصفقات اليومي", dayOk,
    `${input.day.trades} trade(s), ${input.day.losses} loss(es) today`, 0, true));

  result.checklist = checklist;
  result.setup = setup;
  result.score = setup ? scoreChecklist(checklist) : 0;
  const failed = checklist.filter(c => c.required && !c.passed);
  result.rejection = failed.length ? `${failed[0].rule}: ${failed[0].detail}` : null;
  result.status = setup ? classify(result.score, failed.length === 0, cfg.scoring.thresholds) : "NO_TRADE";
  if (setup && result.status === "SIGNAL") result.signal = toSignalJson(spec, cfg.strategy, setup, result.score, cfg.timeframes, checklist);
  result.canNotify = result.status === "SIGNAL" && !!setup?.isFresh && setup.lifecycle.state === "PENDING" && input.isMarketOpen;

  // ---- Drawings ----
  const max = cfg.drawings.maxPerType;
  const sessions: SessionRange[] = [];
  for (const dayOffset of [1, 0]) {
    const key = localDateKey(now - dayOffset * 86400, cfg.sessions.asia.tz);
    const a = sessionRange(m5, 300, "Asia", key, cfg.sessions.asia.tz, cfg.sessions.asia.start, cfg.sessions.asia.end, now);
    if (a) sessions.push(a);
    for (const kz of cfg.sessions.killzones) {
      const r = sessionRange(m5, 300, kz.name.startsWith("London") ? "London" : "NY", localDateKey(now - dayOffset * 86400, kz.tz), kz.tz, kz.start, kz.end, now);
      if (r) sessions.push(r);
    }
  }
  const shownLevels = levels.filter(l => l.kind !== "ROUND" || Math.abs(l.price - price) <= 12);
  const drawings: Drawing[] = [
    ...sessionDrawings(sessions),
    ...levelDrawings(shownLevels.filter(l => isUntaken(l, m5, last) || ["PDH", "PDL", "PWH", "PWL"].includes(l.kind))),
    ...structureDrawings(stH1.events, "H1", "M5", 3),
    ...structureDrawings(st5.events, "M5", "M5", max),
    ...swingDrawings(swings5, "M5", max),
    ...fvgDrawings(fvgsH1, "H1", "M5", 2),
    ...fvgDrawings(fvgs5, "M5", "M5", 3),
    ...obDrawings(obsH1, "H1", "M5", 2),
    ...obDrawings(obs5, "M5", "M5", 3),
    ...sweepDrawings(findSweeps(m5, levels, Math.max(0, last - 200), last, atrNow5), "M5", max),
  ];
  if (setup) drawings.push(...tradeDrawings(setup, "M5", `${setup.lots["1000$"] ?? 0} lot / $1k`));
  result.drawings = declutterZones(drawings);

  // ---- Facts for the AI agent (detector output only) ----
  result.facts = {
    price, spread, atrM5: roundTo(atrNow5, 2), atrH1: roundTo(vol.now, 2), volatilityRatio: roundTo(vol.ratio, 2),
    bias: { h1: h1Dir, h1Close, ema200: roundTo(ema200, d), h4: h4Dir, h4LastBreak: lastH4 ? { type: lastH4.type, direction: lastH4.direction, level: lastH4.level, time: lastH4.breakTime } : null },
    killzone: win?.name ?? "none",
    asianRange: asia ? { high: asia.high, low: asia.low, complete: asia.complete } : null,
    levels: shownLevels.map(l => ({ kind: l.kind, label: l.label, price: l.price, untaken: isUntaken(l, m5, last) })),
    m5Structure: st5.events.slice(-5).map(e => ({ type: e.type, direction: e.direction, level: e.level, time: e.breakTime, displacement: roundTo(e.displacementMult, 2) })),
    h1Structure: stH1.events.slice(-3).map(e => ({ type: e.type, direction: e.direction, level: e.level, time: e.breakTime })),
    fvgsM5: fvgs5.filter(z => z.state !== "FILLED").slice(-max).map(z => ({ direction: z.direction, top: z.top, bottom: z.bottom, state: z.state })),
    orderBlocksH1: obsH1.filter(o => o.state !== "BROKEN").slice(-3).map(o => ({ direction: o.direction, top: o.top, bottom: o.bottom, state: o.state })),
    progress,
  };

  const side = setup?.direction ?? "";
  const headline = !setup ? (progress || "No setup")
    : result.status === "SIGNAL" ? `${side} limit ${f(setup.entry)} · score ${result.score}`
    : result.status === "WATCH" ? `${side} watch · score ${result.score} (needs ${cfg.scoring.thresholds.signal})`
    : result.status === "IGNORE" ? `${side} setup scored ${result.score}: ignored`
    : `${side} setup rejected: ${failed[0]?.rule}`;
  return finish(result, headline, setup ? (result.status === "SIGNAL" ? `إشارة ${side} عند ${f(setup.entry)}` : "إعداد موجود لكنه غير مكتمل الشروط") : "لا توجد صفقة حالياً");
}

function finish(r: StrategyResult, headline: string, headlineAr: string): StrategyResult {
  r.headline = headline;
  r.headlineAr = headlineAr;
  return r;
}

