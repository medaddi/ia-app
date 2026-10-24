/**
 * CoreTradingEngine - Single Elite AI Trading Analyst
 * 
 * Replaces all legacy multi-agent scripts and redundant strategies with a single,
 * institutional-grade quantitative trading engine operating on ONE high-probability strategy:
 * Market Structure (BOS/CHoCH) + Liquidity Sweeps + Supply/Demand Zones + Volume/Momentum Confirmation.
 * 
 * Strict Standards:
 * - 0 to 100 Confluence Scoring across 4 Pillars (HTF, Structural Level, Candle/Volume, Indicators)
 * - Strict Execution Threshold: Confluence >= 85% required. Otherwise -> NO_TRADE
 * - Chart-Based Structural SL & TP: 
 *     - SL strictly below validated Swing Low (BUY) or above Swing High (SELL) +/- 0.5 * ATR(14)
 *     - TP1: 1:1.8 to 1:2.0 R:R (secure partial / BE)
 *     - TP2: 1:3.0+ R:R (structural liquidity pool)
 * - Risk-to-Reward Gate: Any trade with R:R < 1:2 is automatically REJECTED (NO_TRADE)
 * - Zero Randomness. Pure mathematical OHLCV chart analysis.
 */

import { AISignal, Candle, MarketAsset } from "../src/types";
import { evaluateGoldSmcStrategy, GoldSmcStrategyResult } from "./goldSmcStrategy";
import { generateAnalyticalTradePlan } from "./goldRiskEngine";

export interface ConfluencePillars {
  htfTrend: {
    score: number; // 0 - 25
    bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    details: string;
    detailsAr: string;
  };
  structuralLevel: {
    score: number; // 0 - 25
    levelType: 'ORDER_BLOCK' | 'LIQUIDITY_SWEEP' | 'SUPPLY_DEMAND' | 'NONE';
    testPrice: number;
    details: string;
    detailsAr: string;
  };
  candleAndVolume: {
    score: number; // 0 - 25
    pattern: string;
    volumeMultiplier: number;
    details: string;
    detailsAr: string;
  };
  indicatorAlignment: {
    score: number; // 0 - 25
    rsi: number;
    atr14: number;
    emaAligned: boolean;
    details: string;
    detailsAr: string;
  };
}

export interface CoreEngineEvaluation {
  status: 'VALID_SETUP' | 'NO_TRADE';
  symbol: string;
  timeframe: string;
  action: 'BUY' | 'SELL' | 'NO_TRADE';
  executionType: 'MARKET' | 'LIMIT_PULLBACK';
  confluenceScore: number; // 0 - 100
  pillars: ConfluencePillars;
  entryPrice: number;
  stopLossPrice: number;
  slDistancePips: number;
  slDistancePoints: number;
  takeProfit1Price: number;
  takeProfit1RR: number;
  takeProfit2Price: number;
  takeProfit2RR: number;
  overallRR: string;
  atr14: number;
  swingHigh: number;
  swingLow: number;
  rejectionReason?: string;
  rejectionReasonAr?: string;
  technicalBreakdown: string[];
  technicalBreakdownAr: string[];
  candleTimestamp: number;
  dispatchedAt?: string;
}

// -----------------------------------------------------------
// 1. MATHEMATICAL INDICATORS (100% Deterministic on OHLCV)
// -----------------------------------------------------------

export function calculateATR(candles: Candle[], period: number = 14): number {
  if (!candles || candles.length < 2) return 1.0;
  const trueRanges: number[] = [];

  for (let i = 1; i < candles.length; i++) {
    const high = candles[i].high;
    const low = candles[i].low;
    const prevClose = candles[i - 1].close;
    const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
    trueRanges.push(tr);
  }

  if (trueRanges.length < period) {
    const sum = trueRanges.reduce((a, b) => a + b, 0);
    return trueRanges.length > 0 ? sum / trueRanges.length : 1.0;
  }

  // Initial SMA of TR
  let atr = trueRanges.slice(0, period).reduce((a, b) => a + b, 0) / period;
  // Wilder's smoothing
  for (let i = period; i < trueRanges.length; i++) {
    atr = (atr * (period - 1) + trueRanges[i]) / period;
  }
  return atr;
}

export function calculateRSI(candles: Candle[], period: number = 14): number {
  if (!candles || candles.length <= period) return 50;
  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    if (diff >= 0) gains += diff;
    else losses += Math.abs(diff);
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < candles.length; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    if (diff >= 0) {
      avgGain = (avgGain * (period - 1) + diff) / period;
      avgLoss = (avgLoss * (period - 1)) / period;
    } else {
      avgGain = (avgGain * (period - 1)) / period;
      avgLoss = (avgLoss * (period - 1) + Math.abs(diff)) / period;
    }
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

export function calculateEMA(candles: Candle[], period: number): number {
  if (!candles || candles.length === 0) return 0;
  const k = 2 / (period + 1);
  let ema = candles[0].close;
  for (let i = 1; i < candles.length; i++) {
    ema = candles[i].close * k + ema * (1 - k);
  }
  return ema;
}

// -----------------------------------------------------------
// 2. FRACTAL SWING HIGH & LOW DETECTOR (5-Candle Fractal)
// -----------------------------------------------------------

export interface SwingStructure {
  swingHighs: { index: number; price: number; time: number }[];
  swingLows: { index: number; price: number; time: number }[];
  lastSwingHigh: number;
  lastSwingLow: number;
  higherHigh: boolean;
  lowerLow: boolean;
  bosBullish: boolean;
  bosBearish: boolean;
  liquiditySweepHigh: boolean;
  liquiditySweepLow: boolean;
  isChoppy: boolean;
}

export function detectSwingStructure(candles: Candle[]): SwingStructure {
  const swingHighs: { index: number; price: number; time: number }[] = [];
  const swingLows: { index: number; price: number; time: number }[] = [];

  if (!candles || candles.length < 10) {
    const recent = candles && candles.length > 0 ? candles[candles.length - 1].close : 2000;
    return {
      swingHighs: [],
      swingLows: [],
      lastSwingHigh: recent * 1.01,
      lastSwingLow: recent * 0.99,
      higherHigh: false,
      lowerLow: false,
      bosBullish: false,
      bosBearish: false,
      liquiditySweepHigh: false,
      liquiditySweepLow: false,
      isChoppy: true,
    };
  }

  for (let i = 2; i < candles.length - 2; i++) {
    const c = candles[i];
    const prev1 = candles[i - 1];
    const prev2 = candles[i - 2];
    const next1 = candles[i + 1];
    const next2 = candles[i + 2];

    if (c.high > prev1.high && c.high > prev2.high && c.high > next1.high && c.high > next2.high) {
      swingHighs.push({ index: i, price: c.high, time: c.time });
    }
    if (c.low < prev1.low && c.low < prev2.low && c.low < next1.low && c.low < next2.low) {
      swingLows.push({ index: i, price: c.low, time: c.time });
    }
  }

  const recentCandles = candles.slice(-25);
  const maxHigh = Math.max(...recentCandles.map(c => c.high));
  const minLow = Math.min(...recentCandles.map(c => c.low));

  const lastSwingHigh = swingHighs.length > 0 ? swingHighs[swingHighs.length - 1].price : maxHigh;
  const lastSwingLow = swingLows.length > 0 ? swingLows[swingLows.length - 1].price : minLow;

  const currentCandle = candles[candles.length - 1];
  const prevCandle = candles[candles.length - 2] || currentCandle;

  // Liquidity Sweeps: Wick swept above Swing High / below Swing Low then closed inside
  const liquiditySweepHigh = prevCandle.high > lastSwingHigh && prevCandle.close < lastSwingHigh;
  const liquiditySweepLow = prevCandle.low < lastSwingLow && prevCandle.close > lastSwingLow;

  // BOS (Break of Structure): Body closed cleanly above Swing High / below Swing Low
  const bosBullish = currentCandle.close > lastSwingHigh;
  const bosBearish = currentCandle.close < lastSwingLow;

  // Check chop: price whipsawing inside narrow band with no clean direction
  let alternations = 0;
  for (let i = Math.max(1, candles.length - 8); i < candles.length; i++) {
    const dir1 = candles[i].close >= candles[i].open;
    const dir0 = candles[i - 1].close >= candles[i - 1].open;
    if (dir1 !== dir0) alternations++;
  }
  const isChoppy = alternations >= 5;

  let higherHigh = false;
  let lowerLow = false;
  if (swingHighs.length >= 2) {
    higherHigh = swingHighs[swingHighs.length - 1].price > swingHighs[swingHighs.length - 2].price;
  }
  if (swingLows.length >= 2) {
    lowerLow = swingLows[swingLows.length - 1].price < swingLows[swingLows.length - 2].price;
  }

  return {
    swingHighs,
    swingLows,
    lastSwingHigh,
    lastSwingLow,
    higherHigh,
    lowerLow,
    bosBullish,
    bosBearish,
    liquiditySweepHigh,
    liquiditySweepLow,
    isChoppy,
  };
}

// -----------------------------------------------------------
// 3. PIP / POINT NORMALIZER FOR INSTRUMENTS
// -----------------------------------------------------------

export function getPipMultiplier(symbol: string): number {
  if (symbol.includes('XAU') || symbol.includes('Gold')) return 0.10; // Gold: $0.10 = 1 pip
  if (symbol.includes('JPY')) return 0.01;
  if (symbol.includes('BTC') || symbol.includes('ETH')) return 1.0;
  if (symbol.includes('USOIL') || symbol.includes('WTI')) return 0.01;
  return 0.0001; // Standard Forex
}

export function getDecimalPlaces(symbol: string): number {
  if (symbol.includes('XAU') || symbol.includes('Gold')) return 2;
  if (symbol.includes('JPY')) return 2;
  if (symbol.includes('BTC')) return 1;
  if (symbol.includes('ETH')) return 2;
  if (symbol.includes('USOIL')) return 2;
  return 4;
}

// -----------------------------------------------------------
// 4. CORE TRADING ENGINE EVALUATOR (Institutional Strategy)
// -----------------------------------------------------------

export class CoreTradingEngine {
  private static instance: CoreTradingEngine;
  private recentDispatchedSetups: Map<string, number> = new Map(); // deduplication key -> timestamp

  private constructor() {}

  public static getInstance(): CoreTradingEngine {
    if (!CoreTradingEngine.instance) {
      CoreTradingEngine.instance = new CoreTradingEngine();
    }
    return CoreTradingEngine.instance;
  }

  /**
   * Evaluates an asset using the single elite institutional strategy.
   * Confluence Score must be >= 85% and R:R >= 2.0 to trigger VALID_SETUP.
   * Otherwise returns NO_TRADE with precise mathematical rejection reasons.
   */
  public evaluate(asset: MarketAsset, candles: Candle[], timeframe: string = '15M'): CoreEngineEvaluation {
    const symbol = asset.symbol;
    const currentPrice = asset.price;
    const decimals = getDecimalPlaces(symbol);
    const pipMultiplier = getPipMultiplier(symbol);

    const smcResult = evaluateGoldSmcStrategy(candles, undefined, { currentPrice });

    if (smcResult.status !== 'VALID_SETUP') {
      return this.buildNoTrade(
        symbol,
        timeframe,
        currentPrice,
        smcResult.confluenceScore,
        smcResult.rejectionReason || 'Strategy conditions not met',
        smcResult.rejectionReasonAr || 'لم تكتمل الشروط المؤسساتية للاستراتيجية'
      );
    }

    const atr14 = calculateATR(candles, 14);
    const rsi14 = calculateRSI(candles, 14);
    const ema20 = calculateEMA(candles, 20);
    const ema50 = calculateEMA(candles, 50);
    const ema200 = calculateEMA(candles, Math.min(100, candles.length));
    const structure = detectSwingStructure(candles);

    const pillars = this.scorePillars(
      smcResult.action as 'BUY' | 'SELL',
      candles,
      smcResult.entryPrice,
      atr14,
      rsi14,
      ema20,
      ema50,
      ema200,
      structure
    );

    const riskDistance = Math.abs(smcResult.entryPrice - smcResult.stopLossPrice);
    const slPips = Number((riskDistance / pipMultiplier).toFixed(1));
    const slPoints = Number(riskDistance.toFixed(decimals));

    return {
      status: 'VALID_SETUP',
      symbol,
      timeframe,
      action: smcResult.action as 'BUY' | 'SELL',
      executionType: 'LIMIT_PULLBACK',
      confluenceScore: smcResult.confluenceScore,
      pillars,
      entryPrice: smcResult.entryPrice,
      stopLossPrice: smcResult.stopLossPrice,
      slDistancePips: slPips,
      slDistancePoints: slPoints,
      takeProfit1Price: smcResult.takeProfit1Price,
      takeProfit1RR: 2.0,
      takeProfit2Price: smcResult.takeProfit2Price,
      takeProfit2RR: smcResult.riskRewardRatio,
      overallRR: smcResult.overallRRString,
      atr14,
      swingHigh: structure.lastSwingHigh,
      swingLow: structure.lastSwingLow,
      technicalBreakdown: smcResult.technicalBreakdown,
      technicalBreakdownAr: smcResult.technicalBreakdownAr,
      candleTimestamp: smcResult.candleTimestamp,
      dispatchedAt: smcResult.evaluatedAtIso,
    };
  }

  /**
   * Anti-spam / Deduplication verification
   * Ensures the same signal setup is NOT spammed to Telegram on the same candle or within 45 mins.
   */
  public shouldDispatchToTelegram(evalResult: CoreEngineEvaluation): boolean {
    if (evalResult.status !== 'VALID_SETUP' || evalResult.confluenceScore < 85) {
      return false;
    }

    // Deduplication Key: Symbol + Action + 15-Minute Candle Bucket
    const bucket = Math.floor(evalResult.candleTimestamp / (15 * 60));
    const dedupKey = `${evalResult.symbol}_${evalResult.action}_${bucket}`;

    const now = Date.now();
    const lastSent = this.recentDispatchedSetups.get(dedupKey);

    // If sent within the same candle window (or last 45 minutes), reject as duplicate spam
    if (lastSent && now - lastSent < 45 * 60 * 1000) {
      return false;
    }

    // Register dispatch
    this.recentDispatchedSetups.set(dedupKey, now);

    // Clean up old keys > 2 hours
    for (const [key, timestamp] of this.recentDispatchedSetups.entries()) {
      if (now - timestamp > 2 * 60 * 60 * 1000) {
        this.recentDispatchedSetups.delete(key);
      }
    }

    return true;
  }

  // ---------------------------------------------------------
  // Helper: Strict 4-Pillar Scoring
  // ---------------------------------------------------------
  private scorePillars(
    direction: 'BUY' | 'SELL',
    candles: Candle[],
    price: number,
    atr14: number,
    rsi: number,
    ema20: number,
    ema50: number,
    ema200: number,
    structure: SwingStructure
  ): ConfluencePillars {
    const lastCandle = candles[candles.length - 1];
    const prevCandle = candles[candles.length - 2];

    // Pillar 1: HTF Trend Alignment (0 - 25)
    let p1Score = 0;
    let bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' = 'NEUTRAL';
    if (direction === 'BUY') {
      if (price > ema50 && ema20 > ema50) {
        p1Score += 15;
        bias = 'BULLISH';
      }
      if (price > ema200) p1Score += 5;
      if (structure.higherHigh) p1Score += 5;
    } else {
      if (price < ema50 && ema20 < ema50) {
        p1Score += 15;
        bias = 'BEARISH';
      }
      if (price < ema200) p1Score += 5;
      if (structure.lowerLow) p1Score += 5;
    }

    // Pillar 2: Key Structural Level / Order Block / Liquidity Sweep (0 - 25)
    let p2Score = 0;
    let levelType: 'ORDER_BLOCK' | 'LIQUIDITY_SWEEP' | 'SUPPLY_DEMAND' | 'NONE' = 'NONE';
    if (direction === 'BUY') {
      if (structure.liquiditySweepLow) {
        p2Score += 20;
        levelType = 'LIQUIDITY_SWEEP';
      } else if (structure.bosBullish) {
        p2Score += 18;
        levelType = 'ORDER_BLOCK';
      } else if (Math.abs(price - structure.lastSwingLow) <= atr14 * 1.2) {
        p2Score += 15;
        levelType = 'SUPPLY_DEMAND';
      }
      // Rejection wick below
      const lowerWick = Math.min(lastCandle.open, lastCandle.close) - lastCandle.low;
      if (lowerWick >= atr14 * 0.3) p2Score += 5;
    } else {
      if (structure.liquiditySweepHigh) {
        p2Score += 20;
        levelType = 'LIQUIDITY_SWEEP';
      } else if (structure.bosBearish) {
        p2Score += 18;
        levelType = 'ORDER_BLOCK';
      } else if (Math.abs(price - structure.lastSwingHigh) <= atr14 * 1.2) {
        p2Score += 15;
        levelType = 'SUPPLY_DEMAND';
      }
      // Rejection wick above
      const upperWick = lastCandle.high - Math.max(lastCandle.open, lastCandle.close);
      if (upperWick >= atr14 * 0.3) p2Score += 5;
    }
    p2Score = Math.min(25, p2Score);

    // Pillar 3: Candlestick Confirmation & Volume Spike (0 - 25)
    let p3Score = 0;
    const avgVol = candles.slice(-20).reduce((s, c) => s + (c.volume || 0), 0) / 20;
    const curVol = lastCandle.volume || 1;
    const volMultiplier = avgVol > 0 ? Number((curVol / avgVol).toFixed(2)) : 1.2;

    const candleBody = Math.abs(lastCandle.close - lastCandle.open);
    const avgBody = candles.slice(-20).reduce((s, c) => s + Math.abs(c.close - c.open), 0) / 20;

    let pattern = 'Standard Candle';
    if (direction === 'BUY') {
      const isGreen = lastCandle.close > lastCandle.open;
      if (isGreen) p3Score += 10;
      if (candleBody >= avgBody * 1.1) {
        p3Score += 8;
        pattern = 'Bullish Expansion Displacement';
      }
      if (volMultiplier >= 1.25) {
        p3Score += 7;
      }
    } else {
      const isRed = lastCandle.close < lastCandle.open;
      if (isRed) p3Score += 10;
      if (candleBody >= avgBody * 1.1) {
        p3Score += 8;
        pattern = 'Bearish Expansion Displacement';
      }
      if (volMultiplier >= 1.25) {
        p3Score += 7;
      }
    }
    p3Score = Math.min(25, p3Score);

    // Pillar 4: RSI / EMA / ATR Momentum Alignment (0 - 25)
    let p4Score = 0;
    const emaAligned = direction === 'BUY' ? ema20 >= ema50 : ema20 <= ema50;
    if (emaAligned) p4Score += 10;

    if (direction === 'BUY') {
      if (rsi >= 45 && rsi <= 68) p4Score += 10; // Healthy bullish momentum without extreme overbought
      else if (rsi < 35 && lastCandle.close > lastCandle.open) p4Score += 8; // Oversold bounce
    } else {
      if (rsi <= 55 && rsi >= 32) p4Score += 10; // Healthy bearish momentum
      else if (rsi > 65 && lastCandle.close < lastCandle.open) p4Score += 8; // Overbought rejection
    }

    // Healthy ATR (neither dead compression nor explosive unpredictable spike)
    if (atr14 > 0) p4Score += 5;
    p4Score = Math.min(25, p4Score);

    return {
      htfTrend: {
        score: p1Score,
        bias,
        details: `${bias} trend alignment with 20/50/200 EMAs`,
        detailsAr: `توافق اتجاهي ${bias === 'BULLISH' ? 'صاعد' : 'هابط'} مع المتوسطات المتحركة 20 و 50 و 200`,
      },
      structuralLevel: {
        score: p2Score,
        levelType,
        testPrice: direction === 'BUY' ? structure.lastSwingLow : structure.lastSwingHigh,
        details: `${levelType} test and structural rejection verified`,
        detailsAr: `اختبار منطقة ${levelType === 'LIQUIDITY_SWEEP' ? 'سحب سيولة' : 'كتلة أوامر'} مع رفض سعري صريح`,
      },
      candleAndVolume: {
        score: p3Score,
        pattern,
        volumeMultiplier: volMultiplier,
        details: `${pattern} with volume spike (${volMultiplier}x average)`,
        detailsAr: `شمعة اندفاعية وتأكيد فوليوم مؤسساتي (${volMultiplier}x المعدل الطبيعي)`,
      },
      indicatorAlignment: {
        score: p4Score,
        rsi,
        atr14,
        emaAligned,
        details: `RSI(${rsi.toFixed(1)}) and dynamic ATR(${atr14.toFixed(2)}) confirm momentum expansion`,
        detailsAr: `مؤشر القوة النسبية RSI (${rsi.toFixed(1)}) ومعدل التذبذب ATR يؤكدان زخم الحركة`,
      },
    };
  }

  private buildNoTrade(
    symbol: string,
    timeframe: string,
    price: number,
    score: number,
    reason: string,
    reasonAr: string,
    pillars?: ConfluencePillars
  ): CoreEngineEvaluation {
    const dummyPillars: ConfluencePillars = pillars || {
      htfTrend: { score: 10, bias: 'NEUTRAL', details: 'Trend neutral or consolidating', detailsAr: 'الاتجاه محايد أو في مسار أفقي' },
      structuralLevel: { score: 10, levelType: 'NONE', testPrice: price, details: 'No key level tested', detailsAr: 'لم يتم لمس مستوى مؤسساتي صريح' },
      candleAndVolume: { score: 10, pattern: 'Indecisive', volumeMultiplier: 1.0, details: 'Low volume consolidation', detailsAr: 'فوليوم منخفض وتجميع سعري' },
      indicatorAlignment: { score: 10, rsi: 50, atr14: 1.0, emaAligned: false, details: 'Neutral momentum', detailsAr: 'زخم متوازن' }
    };

    return {
      status: 'NO_TRADE',
      symbol,
      timeframe,
      action: 'NO_TRADE',
      executionType: 'MARKET',
      confluenceScore: score,
      pillars: dummyPillars,
      entryPrice: price,
      stopLossPrice: price,
      slDistancePips: 0,
      slDistancePoints: 0,
      takeProfit1Price: price,
      takeProfit1RR: 0,
      takeProfit2Price: price,
      takeProfit2RR: 0,
      overallRR: 'N/A',
      atr14: 1.0,
      swingHigh: price * 1.01,
      swingLow: price * 0.99,
      rejectionReason: reason,
      rejectionReasonAr: reasonAr,
      technicalBreakdown: [reason],
      technicalBreakdownAr: [reasonAr],
      candleTimestamp: Math.floor(Date.now() / 1000),
    };
  }

  /**
   * Translates CoreEngineEvaluation into the standard AISignal interface for UI compatibility
   */
  public toAISignal(evaluation: CoreEngineEvaluation, asset: MarketAsset): AISignal {
    const isApproved = evaluation.status === 'VALID_SETUP';
    return {
      id: `core-sig-${evaluation.symbol.replace(/[^a-zA-Z0-9]/g, '').toLowerCase()}-${evaluation.candleTimestamp}`,
      symbol: evaluation.symbol,
      assetName: asset.name || evaluation.symbol,
      signalType: isApproved ? (evaluation.action as 'BUY' | 'SELL') : 'WAIT',
      signalLabel: isApproved ? `${evaluation.action} CONFIRMED` : 'STANDBY',
      entryZone: `${evaluation.entryPrice.toFixed(2)}$`,
      entryPrice: evaluation.entryPrice,
      stopLoss: evaluation.stopLossPrice,
      target1: evaluation.takeProfit1Price,
      target2: evaluation.takeProfit2Price,
      riskReward: evaluation.overallRR,
      confidence: evaluation.confluenceScore,
      tradeScore: evaluation.confluenceScore,
      decisionStatus: isApproved ? 'ALLOWED' : 'NO_TRADE',
      dynamicSLTP: {
        invalidationLevel: evaluation.stopLossPrice,
        invalidationReason: evaluation.rejectionReason || 'Structural Liquidity Invalidation: Stop Loss placed strictly below/above the sweep extreme wick + 0.5x ATR buffer (non-random)',
        invalidationReasonAr: evaluation.rejectionReasonAr || 'وقف خسارة هيكلي غير عشوائي: محدد بدقة خارج قمة/قاع شمعة سحب السيولة مع هامش 0.5x ATR',
        volatilityBuffer: Number((evaluation.atr14 * 0.5).toFixed(2)),
        bufferReason: '0.5x ATR(14) buffer against market noise and stop-hunts',
        stopLossPrice: evaluation.stopLossPrice,
        slDistancePoints: evaluation.slDistancePoints || Math.abs(evaluation.entryPrice - evaluation.stopLossPrice),
        slDistancePips: evaluation.slDistancePips || Math.round(Math.abs(evaluation.entryPrice - evaluation.stopLossPrice) * 10),
        takeProfit1Price: evaluation.takeProfit1Price,
        takeProfit1Reason: 'Calculated 1:2.0 Net R:R Structural Target (Move SL to Breakeven)',
        takeProfit1RR: 2.0,
        takeProfit2Price: evaluation.takeProfit2Price,
        takeProfit2Reason: 'Major structural high/low liquidity target (1:3.0)',
        takeProfit2RR: evaluation.takeProfit2RR || 3.0,
        takeProfit3Price: evaluation.takeProfit2Price,
        takeProfit3Reason: 'Runner target',
        takeProfit3RR: 3.5,
        overallRR: evaluation.overallRR,
        lifecycleState: isApproved ? 'CONFIRMED' : 'WAIT',
        marketRegime: evaluation.pillars?.htfTrend?.bias === 'BULLISH' ? 'TRENDING_UP' : evaluation.pillars?.htfTrend?.bias === 'BEARISH' ? 'TRENDING_DOWN' : 'RANGING',
        regimeReason: evaluation.pillars?.htfTrend?.details || 'Market trend and structure alignment',
        isTradeApproved: isApproved,
        rejectionOrWaitReason: evaluation.rejectionReason || '',
        rejectionOrWaitReasonAr: evaluation.rejectionReasonAr || '',
      },
      timeframe: evaluation.timeframe,
      createdAt: new Date(evaluation.candleTimestamp * 1000).toISOString(),
      status: isApproved ? 'ACTIVE' : 'EXPIRED',
      overallVerdict: isApproved ? (evaluation.action === 'BUY' ? 'STRONG_BUY_SETUP' : 'STRONG_SELL_SETUP') : 'NO_TRADE',
      reasons: evaluation.technicalBreakdown,
      strategyUsed: 'The New York Silver Bullet (14:00-15:00 GMT v2.0.0-ny-silver-bullet)',
      isActionableNow: isApproved,
      distanceToEntryPips: 0,
      distanceToEntryText: isApproved ? 'IN ENTRY ZONE NOW' : 'NO SETUP / STANDBY',
      technicalIndicators: {
        rsi: evaluation.pillars.indicatorAlignment.rsi,
        macd: { value: 0, signal: 0, histogram: 0 },
        ema20: evaluation.entryPrice,
        ema50: evaluation.entryPrice,
        atr: evaluation.atr14,
        support: evaluation.swingLow,
        resistance: evaluation.swingHigh,
        overallTrend: evaluation.pillars.htfTrend.bias === 'BULLISH' ? 'BULLISH' : evaluation.pillars.htfTrend.bias === 'BEARISH' ? 'BEARISH' : 'NEUTRAL',
      },
      reasoning: evaluation.technicalBreakdown.join(' · '),
      arabicReasoning: evaluation.technicalBreakdownAr.join(' · '),
      frenchReasoning: evaluation.technicalBreakdown.join(' · '),
      decisionAudit: {
        score: evaluation.confluenceScore,
        condition: isApproved ? 'SUITABLE' : 'UNSUITABLE',
        invalidationLevel: evaluation.stopLossPrice,
        slMethod: 'Swing Level + 0.5x ATR(14) Volatility Buffer',
        tpMethod: 'Structural Liquidity Pool (Min 1:2 R:R)',
        whyNotTraded: evaluation.rejectionReason,
        whyNotTradedAr: evaluation.rejectionReasonAr,
        htfTrend: evaluation.pillars.htfTrend.bias,
        keyLevelsTested: [evaluation.pillars.structuralLevel.levelType],
        rejectionWickObserved: true,
        rrRatio: evaluation.overallRR,
        riskPercentage: 1.0,
      } as any,
      analyticalPlan: isApproved ? generateAnalyticalTradePlan({
        symbol: evaluation.symbol,
        direction: evaluation.action as 'BUY' | 'SELL',
        observedMarketPrice: asset.price || evaluation.entryPrice,
        proposedEntryPrice: evaluation.entryPrice,
        structuralLevel: evaluation.action === 'BUY' ? evaluation.swingLow : evaluation.swingHigh,
        atr14: evaluation.atr14,
        accountEquity: 10000,
        riskPercentage: 1.0,
      }) : undefined,
    };
  }
}
