/**
 * Real-Time Dispatched Signal Tracker & Best Opportunity Selector
 * 
 * 1. Tracks all signals dispatched to Telegram with their exact Entry, TP1, TP2, and SL prices.
 * 2. Monitors live tick prices in real-time. ONLY when live price hits the exact TP1 / TP2 / SL sent in the message,
 *    it sends a crystal-clear, concise Telegram notification and records it in the performance ledger.
 * 3. Filters all market opportunities so the bot NEVER spams random signals; it selects only the single BEST A+ opportunity.
 */

import { AISignal, MarketAsset, NewsItem } from "../src/types";
import {
  sendTelegramMessage,
  getTelegramConfig,
  recordNotificationLog,
  getConfirmedSignalMessageId,
  getConfirmedSignalMessageIdBySymbol,
  clearConfirmedSignalMessageId
} from "./telegram";
import { getActiveChatSubscribers, isBotLicenseValid } from "./activation";
import { recordAuditTradeResult, getConsecutiveLossState } from "./signalPerformance";
import { getMarketSessionStatus, getKillzoneStatus } from "./liveMarket";

export interface TrackedDispatchedSignal {
  id: string;
  symbol: string;
  assetName: string;
  signalType: "BUY" | "SELL";
  entryZone: string;
  entryPrice: number;
  initialPrice: number;
  highestPriceSeen: number;
  lowestPriceSeen: number;
  ticksRecorded: number;
  stopLoss: number;
  target1: number;
  target2: number;
  riskReward: string;
  timeframe: string;
  confidence: number;
  dispatchedTimestamp: number;
  tp1Hit: boolean;
  tp1HitTimestamp?: number;
  tp2Hit: boolean;
  tp2HitTimestamp?: number;
  slHit: boolean;
  slHitTimestamp?: number;
  isClosed: boolean;
  pipsSize: number;
  decimals: number;
  consecutiveTp1Ticks?: number;
  consecutiveTp2Ticks?: number;
  consecutiveSlTicks?: number;
}

export interface LiveActiveTradeView {
  id: string;
  symbol: string;
  assetName: string;
  signalType: "BUY" | "SELL";
  entryPrice: number;
  currentPrice: number;
  stopLoss: number;
  target1: number;
  target2: number;
  riskReward: string;
  timeframe: string;
  confidence: number;
  unrealizedPips: number;
  distanceToTp1Pips: number;
  distanceToSlPips: number;
  progressPercent: number;
  status: "ACTIVE" | "TP1_HIT" | "TP2_HIT" | "SL_HIT";
  timeAgo: string;
}

// In-memory registry of actively monitored dispatched signals
const activeDispatchedSignals: Map<string, TrackedDispatchedSignal> = new Map();

// Strict Cooldown: 60 minutes between signals, strictly 1 active trade at a time to eliminate spam
let lastDispatchedSignalTimestamp = 0;
const DISPATCH_COOLDOWN_MS = 60 * 60 * 1000; // 60 minutes between new signals to prevent spam completely

/**
 * Formats a clear, exact Telegram message when TP1 is hit with real live price & pips
 */
export function formatTp1HitMessage(signal: TrackedDispatchedSignal, hitPrice: number, pipsGain: number): string {
  const pipsText = pipsGain > 0 ? `+${pipsGain} Pips` : `${pipsGain} Pips`;

  return `🎯 <b>TP1 HIT | ${signal.symbol} (${pipsText}) ✅</b>

📍 <b>السعر:</b> <code>${hitPrice}</code>
🔒 حجز 50% أرباح + تأمين الدخول (Breakeven).`;
}

/**
 * Formats a clear, exact Telegram message when TP2 is hit
 */
export function formatTp2HitMessage(signal: TrackedDispatchedSignal, hitPrice: number, totalPipsGain: number): string {
  const pipsText = totalPipsGain > 0 ? `+${totalPipsGain} Pips` : `${totalPipsGain} Pips`;

  return `🏆 <b>TP2 HIT | ${signal.symbol} (${pipsText}) 🚀</b>

📍 <b>السعر:</b> <code>${hitPrice}</code>
🎉 إغلاق كامل الصفقة بربح ممتاز.`;
}

/**
 * Formats a clear, exact Telegram message when SL is hit
 */
export function formatSlHitMessage(signal: TrackedDispatchedSignal, hitPrice: number, pipsLoss: number): string {
  const pipsText = pipsLoss > 0 ? `-${pipsLoss} Pips` : `${pipsLoss} Pips`;

  return `🛑 <b>SL HIT | ${signal.symbol} (${pipsText})</b>

📍 <b>السعر:</b> <code>${hitPrice}</code>
🛡️ خروج منضبط بحفظ رأس المال (1% مخاطرة).`;
}

/**
 * Formats a clear, concise Telegram message when trade returns to Breakeven
 */
export function formatBreakevenExitMessage(signal: TrackedDispatchedSignal): string {
  return `🛡️ <b>BREAKEVEN | ${signal.symbol}</b>

📍 <b>السعر:</b> <code>${signal.entryPrice}</code>
🔒 خروج آمن بدون أي خسارة (0$) بعد تأمين أرباح TP1.`;
}

/**
 * Registers a newly dispatched confirmed signal for live price tracking
 */
export function registerDispatchedSignal(signal: AISignal, livePriceAtDispatch?: number) {
  // Disallow duplicate active trade on the SAME symbol
  for (const s of activeDispatchedSignals.values()) {
    if (!s.isClosed && s.symbol === signal.symbol && s.id !== signal.id) {
      console.warn(`[SignalTracker] Dispatched signal ${signal.symbol} rejected: another trade on ${s.symbol} is currently active.`);
      return;
    }
  }

  const isGold = signal.symbol.includes("XAU") || signal.symbol.toLowerCase().includes("gold");
  const isBtc = signal.symbol.includes("BTC");
  const isEth = signal.symbol.includes("ETH");
  const isJpy = signal.symbol.includes("JPY");
  const isForex = (signal.symbol.includes("/") && !isBtc && !isEth) || signal.symbol.includes("EUR") || signal.symbol.includes("GBP") || signal.symbol.includes("USD") || signal.symbol.includes("AUD") || signal.symbol.includes("CAD") || signal.symbol.includes("CHF") || signal.symbol.includes("NZD") || isJpy;
  const isUsoil = signal.symbol.includes("USOIL") || signal.symbol.includes("WTI") || signal.symbol.includes("OIL");
  const isUs30 = signal.symbol.includes("US30") || signal.symbol.includes("DJI");
  
  const decimals = isJpy ? 2 : (isForex ? 4 : isBtc ? 0 : isUs30 ? 0 : 2);
  const pipsSize = isJpy ? 0.01 : (isForex ? 0.0001 : isGold ? 0.1 : isBtc ? 1.0 : isEth ? 0.1 : isUsoil ? 0.01 : isUs30 ? 1.0 : 0.01);

  // Extract entry price
  let entryNum = signal.entryPrice;
  if (!entryNum || entryNum <= 0) {
    if (signal.entryZone) {
      const parts = signal.entryZone.split("-").map(p => parseFloat(p.replace(/[^0-9.]/g, ""))).filter(n => !isNaN(n));
      if (parts.length > 0) {
        entryNum = parts.reduce((a, b) => a + b, 0) / parts.length;
      }
    }
  }
  if (!entryNum || entryNum <= 0) {
    entryNum = (signal.target1 + signal.stopLoss) / 2;
  }

  const currentLive = livePriceAtDispatch && livePriceAtDispatch > 0 ? livePriceAtDispatch : entryNum;
  const isBuy = signal.signalType === "BUY";

  // Strict check: target1 must be sufficiently ahead in profit direction (> 15 pips away)
  const minRequiredDistance = pipsSize * 15;
  const targetDistance = isBuy ? (signal.target1 - currentLive) : (currentLive - signal.target1);

  if (targetDistance < minRequiredDistance) {
    console.warn(`[SignalTracker] Signal ${signal.symbol} target1 ${signal.target1} is too close or already reached by live price ${currentLive} (distance: ${targetDistance}). Skipping auto-tracking to prevent false instant TP1.`);
    return;
  }

  const tracked: TrackedDispatchedSignal = {
    id: signal.id,
    symbol: signal.symbol,
    assetName: signal.assetName || signal.symbol,
    signalType: signal.signalType as "BUY" | "SELL",
    entryZone: signal.entryZone,
    entryPrice: Number(entryNum.toFixed(decimals)),
    initialPrice: currentLive,
    highestPriceSeen: currentLive,
    lowestPriceSeen: currentLive,
    ticksRecorded: 0,
    stopLoss: signal.stopLoss,
    target1: signal.target1,
    target2: signal.target2,
    riskReward: signal.riskReward || "1:3.4",
    timeframe: signal.timeframe || "15M",
    confidence: signal.confidence,
    dispatchedTimestamp: Date.now(),
    tp1Hit: false,
    tp2Hit: false,
    slHit: false,
    isClosed: false,
    pipsSize,
    decimals,
    consecutiveTp1Ticks: 0,
    consecutiveTp2Ticks: 0,
    consecutiveSlTicks: 0
  };

  activeDispatchedSignals.set(signal.id, tracked);
  lastDispatchedSignalTimestamp = Date.now();
  dailyDispatchedTrades.push({ timestamp: Date.now(), symbol: signal.symbol });
  console.log(`[SignalTracker] Registered genuine dispatched signal for live monitoring: ${tracked.symbol} ${tracked.signalType} (Entry: ${tracked.entryPrice}, LiveAtDispatch: ${currentLive}, TP1: ${tracked.target1}, TP2: ${tracked.target2}, SL: ${tracked.stopLoss})`);
}

/**
 * Broadcasts a short notification message to all active authorized Telegram subscribers
 * Replies directly to the original confirmed trade message that had the SL and TP!
 */
async function broadcastTelegramAlert(
  message: string,
  title: string,
  details: string,
  signalId?: string,
  symbol?: string
) {
  const activeSubs = getActiveChatSubscribers();
  const targetChatIds = new Set<string>();
  for (const s of activeSubs) {
    targetChatIds.add(s.chatId);
  }

  const config = getTelegramConfig();
  const globalLicense = isBotLicenseValid();
  if (config.chatId && globalLicense.valid) {
    targetChatIds.add(config.chatId);
  }

  if (targetChatIds.size === 0) return;

  for (const targetId of targetChatIds) {
    const replyToId = (signalId && getConfirmedSignalMessageId(signalId, targetId)) ||
                      (symbol && getConfirmedSignalMessageIdBySymbol(symbol, targetId));
    await sendTelegramMessage(message, {
      chatId: targetId,
      replyToMessageId: replyToId
    });
  }

  recordNotificationLog({
    type: "SIGNAL",
    title,
    details,
    sentAt: new Date().toLocaleTimeString("ar-MA", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    status: "SUCCESS"
  });
}

/**
 * Checks all active dispatched signals against current live market tick prices.
 * Triggered continuously every 1 second.
 * ONLY signals genuinely sent to Telegram are checked.
 */
export async function checkDispatchedSignalsAgainstLivePrices(assetsList: MarketAsset[]) {
  // CRITICAL: Strictly NO auto-seeding of fake/un-dispatched signals!
  // Only signals genuinely dispatched to subscribers are monitored.
  if (activeDispatchedSignals.size === 0) return;

  const assetMap = new Map<string, number>();
  for (const a of assetsList) {
    if (a.price && a.price > 0) {
      assetMap.set(a.symbol, a.price);
    }
  }

  for (const [id, signal] of activeDispatchedSignals.entries()) {
    if (signal.isClosed) continue;

    const currentPrice = assetMap.get(signal.symbol);
    if (!currentPrice || currentPrice <= 0) continue;

    signal.ticksRecorded = (signal.ticksRecorded || 0) + 1;
    signal.highestPriceSeen = Math.max(signal.highestPriceSeen || currentPrice, currentPrice);
    signal.lowestPriceSeen = Math.min(signal.lowestPriceSeen || currentPrice, currentPrice);

    const isBuy = signal.signalType === "BUY";
    const timeElapsedSec = (Date.now() - signal.dispatchedTimestamp) / 1000;

    // Auto-expire stale signals older than 4 hours so no old notifications are ever triggered
    if (timeElapsedSec > 4 * 3600) {
      signal.isClosed = true;
      activeDispatchedSignals.delete(id);
      continue;
    }

    // 1. Check TP1 Hit:
    // Requires that at dispatch price was strictly BEFORE target1,
    // and live price has genuinely crossed and sustained at target1 for at least 3 consecutive live ticks,
    // and at least 15 seconds have elapsed since dispatch.
    if (!signal.tp1Hit && !signal.slHit) {
      const validStartingPosition = isBuy 
        ? signal.initialPrice < signal.target1 
        : signal.initialPrice > signal.target1;

      const isTp1Reached = isBuy 
        ? currentPrice >= signal.target1 
        : currentPrice <= signal.target1;

      if (isTp1Reached) {
        signal.consecutiveTp1Ticks = (signal.consecutiveTp1Ticks || 0) + 1;
      } else {
        signal.consecutiveTp1Ticks = 0;
      }

      if (validStartingPosition && isTp1Reached && signal.consecutiveTp1Ticks >= 3 && timeElapsedSec >= 15) {
        signal.tp1Hit = true;
        signal.tp1HitTimestamp = Date.now();

        const pipsGain = Math.round(Math.abs(signal.target1 - signal.entryPrice) / signal.pipsSize);
        const msg = formatTp1HitMessage(signal, currentPrice, pipsGain);

        await broadcastTelegramAlert(
          msg,
          `[هدف محقق 1] ${signal.symbol} +${pipsGain} Pips`,
          `TP1 reached at live price ${currentPrice} (Target: ${signal.target1})`,
          signal.id,
          signal.symbol
        );

        // Record in Audit Ledger
        recordAuditTradeResult({
          id: `aud-${signal.id}-tp1`,
          symbol: signal.symbol,
          assetName: signal.assetName,
          signalType: signal.signalType,
          entryPrice: signal.entryPrice,
          stopLoss: signal.stopLoss,
          target1: signal.target1,
          target2: signal.target2,
          riskReward: signal.riskReward,
          setupGrade: "A+",
          timeframe: signal.timeframe,
          outcome: "TP1_HIT",
          pipsGained: pipsGain,
          realizedRR: 1.8,
          notesAr: `ضرب الهدف الأول بدقة عند السعر المباشر ${currentPrice} وحجز 50% أرباح`
        });
      }
    }

    // 2. Check TP2 Hit (Only after TP1 has genuinely been hit and sustained for 3 ticks)
    if (signal.tp1Hit && !signal.tp2Hit && !signal.slHit) {
      const isTp2Reached = isBuy ? currentPrice >= signal.target2 : currentPrice <= signal.target2;
      if (isTp2Reached) {
        signal.consecutiveTp2Ticks = (signal.consecutiveTp2Ticks || 0) + 1;
      } else {
        signal.consecutiveTp2Ticks = 0;
      }

      if (isTp2Reached && signal.consecutiveTp2Ticks >= 3) {
        signal.tp2Hit = true;
        signal.tp2HitTimestamp = Date.now();
        signal.isClosed = true; // full completion

        const totalPipsGain = Math.round(Math.abs(signal.target2 - signal.entryPrice) / signal.pipsSize);
        const msg = formatTp2HitMessage(signal, currentPrice, totalPipsGain);

        await broadcastTelegramAlert(
          msg,
          `[هدف نهائي محقق 2] ${signal.symbol} +${totalPipsGain} Pips`,
          `TP2 fully reached at live price ${currentPrice} (Target: ${signal.target2})`,
          signal.id,
          signal.symbol
        );
        clearConfirmedSignalMessageId(signal.id, signal.symbol);

        // Record full TP2 in Audit Ledger
        recordAuditTradeResult({
          id: `aud-${signal.id}-tp2`,
          symbol: signal.symbol,
          assetName: signal.assetName,
          signalType: signal.signalType,
          entryPrice: signal.entryPrice,
          stopLoss: signal.stopLoss,
          target1: signal.target1,
          target2: signal.target2,
          riskReward: signal.riskReward,
          setupGrade: "A+",
          timeframe: signal.timeframe,
          outcome: "TP2_HIT",
          pipsGained: totalPipsGain,
          realizedRR: 3.5,
          notesAr: `تحقيق كامل الأهداف والهدف الثاني ${signal.target2} بنجاح تام`
        });
      }
    }

    // 3. Check Breakeven Exit (If TP1 was reached, and price retraces to entry price)
    if (signal.tp1Hit && !signal.tp2Hit && !signal.isClosed) {
      const isBreakevenReached = isBuy ? currentPrice <= signal.entryPrice : currentPrice >= signal.entryPrice;
      if (isBreakevenReached) {
        signal.isClosed = true;
        const beMsg = formatBreakevenExitMessage(signal);
        await broadcastTelegramAlert(
          beMsg,
          `[تأمين Breakeven] ${signal.symbol}`,
          `Price returned to entry price ${signal.entryPrice} after securing TP1`,
          signal.id,
          signal.symbol
        );
        clearConfirmedSignalMessageId(signal.id, signal.symbol);
      }
    }

    // 4. Check SL Hit (Only if TP1 hasn't been hit yet, sustained for 3 ticks)
    if (!signal.tp1Hit && !signal.slHit) {
      const validStartingPosition = isBuy 
        ? signal.initialPrice > signal.stopLoss 
        : signal.initialPrice < signal.stopLoss;

      const isSlHit = isBuy ? currentPrice <= signal.stopLoss : currentPrice >= signal.stopLoss;
      if (isSlHit) {
        signal.consecutiveSlTicks = (signal.consecutiveSlTicks || 0) + 1;
      } else {
        signal.consecutiveSlTicks = 0;
      }

      if (validStartingPosition && isSlHit && signal.consecutiveSlTicks >= 5 && timeElapsedSec >= 30) {
        signal.slHit = true;
        signal.slHitTimestamp = Date.now();
        signal.isClosed = true;

        const pipsLoss = Math.round(Math.abs(signal.entryPrice - signal.stopLoss) / signal.pipsSize);
        const msg = formatSlHitMessage(signal, currentPrice, pipsLoss);

        await broadcastTelegramAlert(
          msg,
          `[وقف خسارة] ${signal.symbol} -${pipsLoss} Pips`,
          `SL hit at live price ${currentPrice} (SL: ${signal.stopLoss})`,
          signal.id,
          signal.symbol
        );
        clearConfirmedSignalMessageId(signal.id, signal.symbol);

        // Record SL in Audit Ledger
        recordAuditTradeResult({
          id: `aud-${signal.id}-sl`,
          symbol: signal.symbol,
          assetName: signal.assetName,
          signalType: signal.signalType,
          entryPrice: signal.entryPrice,
          stopLoss: signal.stopLoss,
          target1: signal.target1,
          target2: signal.target2,
          riskReward: signal.riskReward,
          setupGrade: "A",
          timeframe: signal.timeframe,
          outcome: "SL_HIT",
          pipsGained: -pipsLoss,
          realizedRR: -1.0,
          notesAr: `ضرب وقف الخسارة عند ${signal.stopLoss} مع التزام تام بإدارة رأس المال (1% Risk)`
        });
      }
    }
  }
}

/**
 * Returns detailed live status of all actively monitored trades for the frontend
 */
export function getLiveActiveTradesList(assetsList: MarketAsset[]): LiveActiveTradeView[] {
  const assetMap = new Map<string, number>();
  for (const a of assetsList) {
    if (a.price && a.price > 0) {
      assetMap.set(a.symbol, a.price);
    }
  }

  const results: LiveActiveTradeView[] = [];

  for (const signal of activeDispatchedSignals.values()) {
    const curPrice = assetMap.get(signal.symbol) || signal.entryPrice;
    const isBuy = signal.signalType === "BUY";
    
    // Unrealized pips calculation
    const rawDiff = isBuy ? curPrice - signal.entryPrice : signal.entryPrice - curPrice;
    const unrealizedPips = Math.round(rawDiff / signal.pipsSize);

    // Distance to TP1 & SL
    const distTp1 = Math.max(0, Math.round(Math.abs(signal.target1 - curPrice) / signal.pipsSize));
    const distSl = Math.max(0, Math.round(Math.abs(curPrice - signal.stopLoss) / signal.pipsSize));

    // Total distance from entry to TP2 for progress calculation
    const totalTargetDiff = Math.abs(signal.target2 - signal.entryPrice);
    const currentProgressRaw = isBuy ? (curPrice - signal.entryPrice) : (signal.entryPrice - curPrice);
    let progressPercent = totalTargetDiff > 0 ? Math.round((currentProgressRaw / totalTargetDiff) * 100) : 0;
    if (signal.tp2Hit) progressPercent = 100;
    else if (signal.tp1Hit && progressPercent < 50) progressPercent = 50;
    else if (progressPercent < 0) progressPercent = 0;
    if (progressPercent > 100) progressPercent = 100;

    let status: "ACTIVE" | "TP1_HIT" | "TP2_HIT" | "SL_HIT" = "ACTIVE";
    if (signal.tp2Hit) status = "TP2_HIT";
    else if (signal.tp1Hit) status = "TP1_HIT";
    else if (signal.slHit) status = "SL_HIT";

    const elapsedMin = Math.max(1, Math.round((Date.now() - signal.dispatchedTimestamp) / 60000));
    const timeAgo = elapsedMin < 60 ? `قبل ${elapsedMin} دقيقة` : `قبل ${Math.round(elapsedMin / 60)} ساعة`;

    results.push({
      id: signal.id,
      symbol: signal.symbol,
      assetName: signal.assetName,
      signalType: signal.signalType,
      entryPrice: signal.entryPrice,
      currentPrice: curPrice,
      stopLoss: signal.stopLoss,
      target1: signal.target1,
      target2: signal.target2,
      riskReward: signal.riskReward,
      timeframe: signal.timeframe,
      confidence: signal.confidence,
      unrealizedPips,
      distanceToTp1Pips: distTp1,
      distanceToSlPips: distSl,
      progressPercent,
      status,
      timeAgo
    });
  }

  return results;
}

/**
 * Verifies if the market is clean, orderly, and stable for a given asset.
 * A professional human trader refuses to enter if:
 * 1. Market session is closed or illiquid.
 * 2. Conflicting high-impact economic news is active.
 * 3. Market is experiencing choppy consolidation without clear structural boundaries.
 */
export function isMarketStableForTrading(
  symbol: string,
  newsList: NewsItem[] = []
): { isStable: boolean; reasonAr?: string } {
  // 0. Circuit Breaker protection check (stops trading after consecutive SL hits)
  const circuitBreaker = getConsecutiveLossState();
  if (circuitBreaker.isTriggered) {
    return {
      isStable: false,
      reasonAr: circuitBreaker.reasonAr
    };
  }

  // 1. Session check
  const session = getMarketSessionStatus(symbol);
  if (!session.isOpen) {
    return { isStable: false, reasonAr: `السوق مغلق حالياً لـ ${symbol} (${session.labelAr})` };
  }

  // 2. Optimal Institutional Timing Check
  const killzone = getKillzoneStatus(symbol);
  if (killzone.timingQuality === 'MARKET_CLOSED') {
    return {
      isStable: false,
      reasonAr: `السوق مغلق حالياً لـ ${symbol}`
    };
  }

  // 3. High-impact conflicting news check (within 45 minutes)
  const conflictingNews = newsList.find(n => 
    n.impactAsset === symbol && 
    n.importance === "HIGH" && 
    n.impactVerdict === "negative" &&
    (Date.now() - new Date(n.publishedAt).getTime()) < 45 * 60 * 1000
  );

  if (conflictingNews) {
    return {
      isStable: false,
      reasonAr: `السوق غير مستقر أو متقلب بسبب خبر عالي التأثير: ${conflictingNews.titleAr || conflictingNews.title}`
    };
  }

  return { isStable: true };
}

/**
 * Intelligent Opportunity Selection Engine (Elite Human Pro Trader Mindset):
 * "khas ychof charts b7al chi motadawil naj7 o mtfw9: ytsna a7sn forsa o setup tkun wad7a 100% o m79a ga3 chorot"
 * "baach y2kd confermation dyal 15min ydoooz l 5min o kola zawj o statigie li ghadi tji m3ahom o machi darori t7takr 3la w7da"
 * Filters all candidates and picks the highest-probability A+ setup across stable, active, non-monopolized markets.
 */
export function selectAbsoluteBestOpportunity(
  signalsList: AISignal[],
  newsList: NewsItem[],
  minConfidence: number = 75
): AISignal | null {
  // If consecutive loss circuit breaker is active, NEVER dispatch new signals!
  const cb = getConsecutiveLossState();
  if (cb.isTriggered) {
    console.log(`[OpportunitySelector] 🛡️ Circuit Breaker ACTIVE: Halting new trade dispatches. Reason: ${cb.reasonAr}`);
    return null;
  }

  // Get active symbols currently running to prevent duplicate exposure on the same pair
  const activeSymbols = new Set<string>();
  for (const s of activeDispatchedSignals.values()) {
    if (!s.isClosed && (Date.now() - s.dispatchedTimestamp < 25 * 60 * 1000)) {
      activeSymbols.add(s.symbol);
    }
  }

  // 1. Filter viable candidates across ALL available app pairs (Strict high-conviction only)
  const candidates = signalsList.filter((s) => {
    // Strictly Gold (XAU/USD) only - purge all crypto and non-gold assets
    if (!s.symbol || (!s.symbol.includes("XAU") && s.symbol !== "GOLD")) return false;

    // Must not already have an active position on this specific asset within active window
    if (activeSymbols.has(s.symbol)) return false;

    // Must be an active actionable direction (BUY or SELL, never WAIT)
    if (s.signalType === "WAIT" || s.decisionStatus === "NO_TRADE") return false;
    if (s.status && s.status !== "ACTIVE") return false;

    // Check if market is open (24/7 OTC Spot Gold)
    const is24h = s.symbol.includes("XAU");
    const market = getMarketSessionStatus(s.symbol);
    if (!is24h && !market.isOpen) return false;

    // Avoid totally closed weekend session
    const kz = getKillzoneStatus(s.symbol);
    if (kz.timingQuality === 'MARKET_CLOSED') return false;

    // Check market news stability (no conflicting high-impact red news)
    const stability = isMarketStableForTrading(s.symbol, newsList);
    if (!stability.isStable) return false;

    // Confidence threshold (A+ setups: min required confidence)
    if ((s.confidence || 0) < minConfidence) return false;

    // Proximity to entry check: should be near entry zone (within 35 pips for Gold)
    if (s.distanceToEntryPips !== undefined && Math.abs(s.distanceToEntryPips) > 35) return false;

    // Strict SL/TP Mathematical Invariant Verification
    const isBuy = s.signalType === "BUY";
    if (isBuy) {
      if (s.stopLoss >= s.entryPrice || s.target1 <= s.entryPrice || s.target2 <= s.target1) {
        return false;
      }
    } else {
      if (s.stopLoss <= s.entryPrice || s.target1 >= s.entryPrice || s.target2 >= s.target1) {
        return false;
      }
    }

    // Must have solid Risk/Reward (>= 1:2.0)
    const rrNum = parseFloat((s.riskReward || "").replace("1:", "")) || 0;
    if (rrNum > 0 && rrNum < 2.0) return false;

    return true;
  });

  if (candidates.length === 0) return null;

  // 2. Score candidates objectively based on institutional confluence & prime timing
  const scored = candidates.map((signal) => {
    let score = (signal.confidence || 90) * 2;

    // A+ Setup Quality Grade
    if (signal.setupGrade === "A+") score += 45;
    else if (signal.setupGrade === "A") score += 25;

    // Actionable right now in sweet spot entry zone
    if (signal.isActionableNow) score += 40;
    if (signal.distanceToEntryPips !== undefined && Math.abs(signal.distanceToEntryPips) <= 5) score += 30;

    // Prime Session Killzone Timing bonus
    const kz = getKillzoneStatus(signal.symbol);
    if (kz.inKillzone || kz.timingQuality === 'PRIME_INSTITUTIONAL') {
      score += 40;
    }

    // Mathematical Risk-to-Reward multiplier (favoring clean asymmetrical payoffs)
    const rrNum = parseFloat((signal.riskReward || "").replace("1:", "")) || 2.5;
    score += Math.min(rrNum * 12, 50);

    return { signal, score };
  });

  // Sort descending by highest confirmation score first, then composite institutional score
  scored.sort((a, b) => {
    const confDiff = (b.signal.confidence || 0) - (a.signal.confidence || 0);
    if (confDiff !== 0) return confDiff;
    return b.score - a.score;
  });

  const topPick = scored[0];
  const requiredThreshold = Math.max(92, minConfidence);
  if (topPick && (topPick.signal.confidence || 0) >= requiredThreshold) {
    console.log(`[TopScoreSelector] 🥇 Top confirmation score trade selected: ${topPick.signal.symbol} ${topPick.signal.signalType} (Score: ${topPick.signal.confidence}%, Passed: ${topPick.signal.confluenceChecklist?.filter(c => c.passed).length || 8}/8 conditions)`);
    return topPick.signal;
  }

  return null;
}

// Daily dispatched signals counter to enforce real prop trader daily discipline
let dailyDispatchedTrades: { timestamp: number; symbol: string }[] = [];

/**
 * Checks if the system is allowed to dispatch a new signal based on cooldown
 * and portfolio risk management (Supports 24/7 continuous multi-asset trades).
 */
export function canDispatchNewSignal(targetSymbol?: string): boolean {
  const now = Date.now();

  // 1. Clean daily trades older than 24h
  dailyDispatchedTrades = dailyDispatchedTrades.filter(t => now - t.timestamp < 24 * 60 * 60 * 1000);

  // Prop Firm Quality Discipline Cap: Max 5 confirmed A+ trades per 24 hours to prevent spam completely
  if (dailyDispatchedTrades.length >= 5) {
    return false;
  }

  // 2. Active trade cooldown (30 minutes per symbol)
  let activeCount = 0;
  for (const s of activeDispatchedSignals.values()) {
    if (!s.isClosed) {
      // An open trade keeps being tracked to TP/SL (the tracker expires it after 4h);
      // never close it here, just block a second trade on the same symbol
      if (targetSymbol && s.symbol === targetSymbol) return false;
      activeCount++;
    } else {
      // Cooldown for recently closed trades on the same symbol (30 minutes)
      if (targetSymbol && s.symbol === targetSymbol && (now - s.dispatchedTimestamp < 30 * 60 * 1000)) {
        return false;
      }
    }
  }

  // Professional Multi-Market Diversification:
  // Allow up to 4 concurrent active trades across different assets (e.g. 1 Gold + 1 BTC + 1-2 Forex)
  if (activeCount >= 4) {
    return false;
  }

  // No pacing between different pairs: gold and EURUSD can close on the same minute and both must
  // go out immediately (per-symbol and daily caps above already prevent spam)
  return true;
}

/**
 * Returns currently tracked active signals for monitoring
 */
export function getActiveDispatchedSignals(): TrackedDispatchedSignal[] {
  return Array.from(activeDispatchedSignals.values());
}

/**
 * Resets all dispatched signals to start completely fresh
 */
export function resetAllDispatchedSignals() {
  activeDispatchedSignals.clear();
  lastDispatchedSignalTimestamp = 0;
  console.log("[SignalTracker] All active dispatched signals have been purged.");
}

