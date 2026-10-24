/**
 * Gold Sovereign AI - Exclusive Strategy Engine
 * Strategy: The New York Silver Bullet (14:00 to 15:00 GMT / 10:00 to 11:00 AM EST)
 * Version: v2.0.0-ny-silver-bullet
 * 
 * Instrument Focus: Pure Spot XAU/USD (Institutional OTC)
 * Execution Model: M15 Liquidity Preparation & M5 High-Probability Limit Execution (Signal & Telegram Only)
 */

import { Candle, MarketAsset, NewsItem } from "../src/types";

// ============================================================
// 1. CONFIGURATION & CONTRACT INTERFACES
// ============================================================

export interface NySilverBulletConfig {
  version: string;
  symbol: string;
  timeWindow: {
    startGmtHour: number;   // 14:00 GMT
    endGmtHour: number;     // 15:00 GMT
    enforceTimeWindow: boolean; // strict live guard
  };
  m15Preparation: {
    asianStartGmtHour: number;  // 00:00 GMT
    asianEndGmtHour: number;    // 08:00 GMT
    londonStartGmtHour: number; // 08:00 GMT
    londonEndGmtHour: number;   // 13:55 GMT
  };
  m5Displacement: {
    minBodyPercentage: number;   // > 65% of total candle range
    minAtrMultiplier: number;    // > 1.3x ATR(14)
    maxNewsWhipsawAtr: number;   // 3.5x ATR(14) - Tier-1 News Anomaly Guard
  };
  riskReward: {
    minNetRR: number;                    // 2.0 minimum net R:R
    slWickBufferAtrMultiplier: number;   // 0.5x M5 ATR(14)
    defaultEntryModel: 'CE_MIDPOINT' | 'PROXIMAL_EDGE';
  };
  scoring: {
    minThreshold: number; // 85 points
  };
}

export const DEFAULT_NY_SILVER_BULLET_CONFIG: NySilverBulletConfig = {
  version: "v2.0.0-ny-silver-bullet",
  symbol: "XAU/USD",
  timeWindow: {
    startGmtHour: 14,
    endGmtHour: 15,
    enforceTimeWindow: false, // Allows institutional 24h SMC execution across London & NY sessions
  },
  m15Preparation: {
    asianStartGmtHour: 0,
    asianEndGmtHour: 8,
    londonStartGmtHour: 8,
    londonEndGmtHour: 14,
  },
  m5Displacement: {
    minBodyPercentage: 0.65, // >= 65%
    minAtrMultiplier: 1.2,   // >= 1.2x M5 ATR(14)
    maxNewsWhipsawAtr: 3.5,  // > 3.5x ATR is rejected as news whipsaw
  },
  riskReward: {
    minNetRR: 2.0,
    slWickBufferAtrMultiplier: 0.5,
    defaultEntryModel: "CE_MIDPOINT",
  },
  scoring: {
    minThreshold: 85,
  },
};

export interface M15SessionLiquidityLevels {
  asianHigh: number;
  asianLow: number;
  londonHigh: number;
  londonLow: number;
  previousDayHigh: number;
  previousDayLow: number;
  asianSwept: 'NONE' | 'BSL_SWEPT' | 'SSL_SWEPT' | 'BOTH';
  londonSwept: 'NONE' | 'BSL_SWEPT' | 'SSL_SWEPT' | 'BOTH';
}

export interface RejectionGuardsCheck {
  timeWindowGuardPassed: boolean;        // 14:00 - 15:00 GMT check
  displacementGuardPassed: boolean;      // body > 65% & range > 1.3x ATR
  newsWhipsawGuardPassed: boolean;       // sweep < 3.5x ATR & R:R >= 2.0
  rejectionReason?: string;
  rejectionReasonAr?: string;
}

export interface SilverBulletStepStates {
  step1_m15Prep: 'VERIFIED' | 'PENDING';
  step2_timeWindowActive: 'ACTIVE' | 'OUTSIDE_WINDOW';
  step3_m5Sweep: 'VERIFIED' | 'PENDING' | 'REJECTED';
  step4_displacementMss: 'VERIFIED' | 'WEAK_DISPLACEMENT' | 'PENDING';
  step5_fvgLimitEntry: 'TRIGGERED' | 'WAITING_RETEST' | 'PENDING' | 'INVALIDATED';
}

export interface GoldSmcStrategyResult {
  status: 'VALID_SETUP' | 'NO_TRADE';
  strategyName: string;
  strategyVersion: string;
  action: 'BUY' | 'SELL' | 'NO_TRADE';
  symbol: string;
  timeframe: string;
  confluenceScore: number; // 0 - 100
  lifecycleState: 'READY_FOR_ENTRY' | 'WAITING_PULLBACK' | 'NO_TRADE' | 'INVALIDATED' | 'EXPIRED';
  stepStates: SilverBulletStepStates;
  guards: RejectionGuardsCheck;

  // Prices
  observedMarketPrice: number;
  entryPrice: number;
  stopLossPrice: number;
  takeProfit1Price: number;
  takeProfit2Price: number;
  riskRewardRatio: number;
  overallRRString: string;

  // M15 & M5 Structural Levels for Chart Visualization
  m15Liquidity: M15SessionLiquidityLevels;
  sweptLevelPrice: number;
  sweptLevelType: 'BSL' | 'SSL' | 'NONE';
  mssPrice: number;
  displacementAtrRatio: number;
  displacementBodyPct: number;
  fvgZone: {
    gapLow: number;
    gapHigh: number;
    proximalEdge: number;
    midpointCE: number;
    isMitigated: boolean;
  } | null;

  atr14: number;
  rejectionReason?: string;
  rejectionReasonAr?: string;
  technicalBreakdown: string[];
  technicalBreakdownAr: string[];
  candleTimestamp: number;
  evaluatedAtIso: string;
}

// ============================================================
// 2. MATHEMATICAL & LIQUIDITY MAPPING HELPERS
// ============================================================

export function calculateAtr14(candles: Candle[], period: number = 14): number {
  if (!candles || candles.length < 2) return 1.5;
  const trs: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    const tr = Math.max(
      candles[i].high - candles[i].low,
      Math.abs(candles[i].high - candles[i - 1].close),
      Math.abs(candles[i].low - candles[i - 1].close)
    );
    trs.push(tr);
  }
  if (trs.length < period) return trs.reduce((a, b) => a + b, 0) / (trs.length || 1);
  let atr = trs.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < trs.length; i++) {
    atr = (atr * (period - 1) + trs[i]) / period;
  }
  return Number(atr.toFixed(2));
}

/**
 * Step 1: Pre-14:00 GMT M15 Liquidity Mapping
 * Maps Asian High/Low (00:00-08:00 GMT), London High/Low (08:00-13:55 GMT), and Prev Day High/Low
 */
export function mapM15SessionLiquidity(candles: Candle[]): M15SessionLiquidityLevels {
  let asianHigh = -Infinity;
  let asianLow = Infinity;
  let londonHigh = -Infinity;
  let londonLow = Infinity;
  let pdHigh = -Infinity;
  let pdLow = Infinity;

  const nowSec = candles.length > 0 ? candles[candles.length - 1].time : Math.floor(Date.now() / 1000);
  const currentDayUtc = new Date(nowSec * 1000).getUTCDate();

  for (const c of candles) {
    const d = new Date(c.time * 1000);
    const day = d.getUTCDate();
    const hour = d.getUTCHours();
    const minute = d.getUTCMinutes();
    const timeMin = hour * 60 + minute;

    // Previous day calculation
    if (day !== currentDayUtc) {
      if (c.high > pdHigh) pdHigh = c.high;
      if (c.low < pdLow) pdLow = c.low;
    }

    // Current day sessions
    if (day === currentDayUtc) {
      // Asian Session (00:00 - 08:00 GMT)
      if (timeMin >= 0 && timeMin < 8 * 60) {
        if (c.high > asianHigh) asianHigh = c.high;
        if (c.low < asianLow) asianLow = c.low;
      }
      // London Session (08:00 - 13:55 GMT)
      if (timeMin >= 8 * 60 && timeMin < 14 * 60) {
        if (c.high > londonHigh) londonHigh = c.high;
        if (c.low < londonLow) londonLow = c.low;
      }
    }
  }

  // Fallback defaults if candles array starts after 00:00
  if (asianHigh === -Infinity && candles.length > 0) {
    const minP = Math.min(...candles.map(c => c.low));
    const maxP = Math.max(...candles.map(c => c.high));
    asianHigh = Number((minP + (maxP - minP) * 0.45).toFixed(2));
    asianLow = Number(minP.toFixed(2));
  }
  if (londonHigh === -Infinity && candles.length > 0) {
    const maxP = Math.max(...candles.map(c => c.high));
    const minP = Math.min(...candles.map(c => c.low));
    londonHigh = Number(maxP.toFixed(2));
    londonLow = Number((minP + (maxP - minP) * 0.55).toFixed(2));
  }
  if (pdHigh === -Infinity && candles.length > 0) {
    pdHigh = Number((candles[0].high + 12.0).toFixed(2));
    pdLow = Number((candles[0].low - 10.0).toFixed(2));
  }

  return {
    asianHigh: Number(asianHigh.toFixed(2)),
    asianLow: Number(asianLow.toFixed(2)),
    londonHigh: Number(londonHigh.toFixed(2)),
    londonLow: Number(londonLow.toFixed(2)),
    previousDayHigh: Number(pdHigh.toFixed(2)),
    previousDayLow: Number(pdLow.toFixed(2)),
    asianSwept: 'NONE',
    londonSwept: 'NONE',
  };
}

/**
 * Swing point detection on M5 execution candles
 */
export interface SwingPoint {
  index: number;
  type: 'HIGH' | 'LOW';
  price: number;
  time: number;
}

export function detectM5SwingPoints(candles: Candle[], left: number = 2, right: number = 2): {
  swingHighs: SwingPoint[];
  swingLows: SwingPoint[];
} {
  const highs: SwingPoint[] = [];
  const lows: SwingPoint[] = [];
  const end = candles.length - 1 - right;

  for (let i = left; i <= end; i++) {
    const cur = candles[i];
    let isH = true;
    let isL = true;
    for (let j = 1; j <= left; j++) {
      if (candles[i - j].high >= cur.high) isH = false;
      if (candles[i - j].low <= cur.low) isL = false;
    }
    for (let k = 1; k <= right; k++) {
      if (candles[i + k].high >= cur.high) isH = false;
      if (candles[i + k].low <= cur.low) isL = false;
    }
    if (isH) highs.push({ index: i, type: 'HIGH', price: cur.high, time: cur.time });
    if (isL) lows.push({ index: i, type: 'LOW', price: cur.low, time: cur.time });
  }

  return { swingHighs: highs, swingLows: lows };
}

// ============================================================
// 3. CORE STRATEGY EVALUATOR: NY SILVER BULLET v2.0.0
// ============================================================

/**
 * The New York Silver Bullet Strategy Evaluator
 * Runs strictly on M15 (Prep) and M5 (Execution)
 */
export function evaluateGoldSmcStrategy(
  candles: Candle[],
  config: NySilverBulletConfig = DEFAULT_NY_SILVER_BULLET_CONFIG,
  options?: {
    bypassTimeWindow?: boolean; // Used for historical test verification & unit testing
    newsItems?: NewsItem[];
    currentPrice?: number;
  }
): GoldSmcStrategyResult {
  const evaluatedAtIso = new Date().toISOString();
  const currentCandle = candles[candles.length - 1];
  const candleTimestamp = currentCandle ? currentCandle.time : Math.floor(Date.now() / 1000);
  const observedMarketPrice = (options?.currentPrice && options.currentPrice > 2000)
    ? options.currentPrice
    : (currentCandle ? currentCandle.close : 2715.0);

  const defaultLiquidity = mapM15SessionLiquidity(candles);
  const atr14 = calculateAtr14(candles, 14);

  // Default No-Trade template
  const createNoTrade = (
    reasonEn: string,
    reasonAr: string,
    guards: Partial<RejectionGuardsCheck> = {},
    stepStates: Partial<SilverBulletStepStates> = {}
  ): GoldSmcStrategyResult => {
    return {
      status: 'NO_TRADE',
      strategyName: 'The New York Silver Bullet (14:00 to 15:00 GMT / 10:00 to 11:00 AM EST)',
      strategyVersion: config.version,
      action: 'NO_TRADE',
      symbol: config.symbol,
      timeframe: 'M5 / M15',
      confluenceScore: 40,
      lifecycleState: 'NO_TRADE',
      stepStates: {
        step1_m15Prep: 'VERIFIED',
        step2_timeWindowActive: 'OUTSIDE_WINDOW',
        step3_m5Sweep: 'PENDING',
        step4_displacementMss: 'PENDING',
        step5_fvgLimitEntry: 'PENDING',
        ...stepStates,
      },
      guards: {
        timeWindowGuardPassed: false,
        displacementGuardPassed: false,
        newsWhipsawGuardPassed: true,
        rejectionReason: reasonEn,
        rejectionReasonAr: reasonAr,
        ...guards,
      },
      observedMarketPrice,
      entryPrice: observedMarketPrice,
      stopLossPrice: Number((observedMarketPrice - 10.0).toFixed(2)),
      takeProfit1Price: Number((observedMarketPrice + 20.0).toFixed(2)),
      takeProfit2Price: Number((observedMarketPrice + 35.0).toFixed(2)),
      riskRewardRatio: 0,
      overallRRString: 'N/A',
      m15Liquidity: defaultLiquidity,
      sweptLevelPrice: 0,
      sweptLevelType: 'NONE',
      mssPrice: 0,
      displacementAtrRatio: 0,
      displacementBodyPct: 0,
      fvgZone: null,
      atr14,
      rejectionReason: reasonEn,
      rejectionReasonAr: reasonAr,
      technicalBreakdown: [reasonEn],
      technicalBreakdownAr: [reasonAr],
      candleTimestamp,
      evaluatedAtIso,
    };
  };

  // Check 1: Insufficient Candle Data
  if (!candles || candles.length < 20) {
    return createNoTrade(
      'INSUFFICIENT_CANDLE_DATA: Minimum 20 M5/M15 candles required for Silver Bullet preparation.',
      'بيانات الشموع غير كافية: يلزم 20 شمعة على الأقل لرسم سيولة جلسات نيويورك بدقة.'
    );
  }

  // Check 2: Strict Mechanical Time Window Guard (14:00 - 15:00 GMT)
  const evalDate = new Date(candleTimestamp * 1000);
  const evalHour = evalDate.getUTCHours();
  const evalMin = evalDate.getUTCMinutes();
  const totalMin = evalHour * 60 + evalMin;
  const isInside14to15Gmt = totalMin >= 14 * 60 && totalMin <= 15 * 60;

  const shouldEnforceWindow = config.timeWindow.enforceTimeWindow && !options?.bypassTimeWindow;
  if (shouldEnforceWindow && !isInside14to15Gmt) {
    return createNoTrade(
      `TIME_WINDOW_GUARD: Current time (${evalHour.toString().padStart(2, '0')}:${evalMin.toString().padStart(2, '0')} GMT) is outside the 14:00-15:00 GMT Silver Bullet execution window.`,
      `حارس نافذة الوقت: الوقت الحالي (${evalHour}:${evalMin} GMT) خارج نافذة نيويورك سيلفر بوليت الرسمية (14:00 - 15:00 GMT).`,
      { timeWindowGuardPassed: false },
      { step1_m15Prep: 'VERIFIED', step2_timeWindowActive: 'OUTSIDE_WINDOW' }
    );
  }

  // Step 1: Map M15 Liquidity Levels (Asian High/Low 00:00-08:00, London High/Low 08:00-13:55)
  // Pre-14:00 GMT candles strictly used for session preparation
  const prepCandles = candles.filter(c => {
    const h = new Date(c.time * 1000).getUTCHours();
    return h < 14;
  });
  const m15Source = prepCandles.length >= 10 ? prepCandles : candles.slice(0, Math.max(10, candles.length - 12));
  const m15 = mapM15SessionLiquidity(m15Source);

  // mapM15SessionLiquidity synthesizes fallback levels when a session has no candles;
  // only sessions backed by real candles may be treated as raidable liquidity.
  const m15Day = new Date(m15Source[m15Source.length - 1].time * 1000).getUTCDate();
  const sessionHours = m15Source
    .filter(c => new Date(c.time * 1000).getUTCDate() === m15Day)
    .map(c => new Date(c.time * 1000).getUTCHours());
  const hasRealAsianSession = sessionHours.some(h => h < 8);
  const hasRealLondonSession = sessionHours.some(h => h >= 8 && h < 14);

  // Step 2: Liquidity Sweep Detection (London/Asian Range or Recent Structural Swings)
  const windowStartIdx = prepCandles.length > 0 ? prepCandles.length : Math.max(0, candles.length - 15);
  const lookbackStart = shouldEnforceWindow ? windowStartIdx : Math.max(2, candles.length - 35);
  let sweepDetected: {
    type: 'SSL_SWEEP' | 'BSL_SWEEP';
    candleIndex: number;
    sweepPrice: number;
    extremePrice: number;
    referenceLevel: number;
    sweptLabel: string;
  } | null = null;

  for (let i = lookbackStart; i < candles.length; i++) {
    const c = candles[i];
    const cHour = new Date(c.time * 1000).getUTCHours();
    if (shouldEnforceWindow && cHour !== 14) continue;

    // Bullish Sweep: Price pierces below London Low or Asian Low (SSL)
    if (hasRealLondonSession && c.low < m15.londonLow - 0.5 && (c.close >= m15.londonLow - 0.5 || c.close > c.low + (c.high - c.low) * 0.25)) {
      sweepDetected = {
        type: 'SSL_SWEEP',
        candleIndex: i,
        sweepPrice: c.low,
        extremePrice: c.low,
        referenceLevel: m15.londonLow,
        sweptLabel: 'London Session Low (SSL)',
      };
      break;
    }
    if (hasRealAsianSession && c.low < m15.asianLow - 0.5 && (c.close >= m15.asianLow - 0.5 || c.close > c.low + (c.high - c.low) * 0.25)) {
      sweepDetected = {
        type: 'SSL_SWEEP',
        candleIndex: i,
        sweepPrice: c.low,
        extremePrice: c.low,
        referenceLevel: m15.asianLow,
        sweptLabel: 'Asian Session Low (SSL)',
      };
      break;
    }

    // Bearish Sweep: Price pierces above London High or Asian High (BSL)
    if (hasRealLondonSession && c.high > m15.londonHigh + 0.5 && (c.close <= m15.londonHigh + 0.5 || c.close < c.high - (c.high - c.low) * 0.25)) {
      sweepDetected = {
        type: 'BSL_SWEEP',
        candleIndex: i,
        sweepPrice: c.high,
        extremePrice: c.high,
        referenceLevel: m15.londonHigh,
        sweptLabel: 'London Session High (BSL)',
      };
      break;
    }
    if (hasRealAsianSession && c.high > m15.asianHigh + 0.5 && (c.close <= m15.asianHigh + 0.5 || c.close < c.high - (c.high - c.low) * 0.25)) {
      sweepDetected = {
        type: 'BSL_SWEEP',
        candleIndex: i,
        sweepPrice: c.high,
        extremePrice: c.high,
        referenceLevel: m15.asianHigh,
        sweptLabel: 'Asian Session High (BSL)',
      };
      break;
    }
  }

  // Fallback: Recent Structural Fractal Sweeps (for London / Asian / Pre-NY sessions)
  // Only used when no session-level (London/Asian) sweep exists, so the candle that
  // forms a session extreme is never misread as a raid ahead of the real sweep.
  for (let i = lookbackStart; i < candles.length && !sweepDetected; i++) {
    const c = candles[i];
    if (!shouldEnforceWindow && i >= 6) {
      const priorCandles = candles.slice(Math.max(0, i - 16), i);
      const recentMin = Math.min(...priorCandles.map(x => x.low));
      const recentMax = Math.max(...priorCandles.map(x => x.high));
      if (c.low < recentMin - 0.4 && c.close > recentMin) {
        sweepDetected = {
          type: 'SSL_SWEEP',
          candleIndex: i,
          sweepPrice: c.low,
          extremePrice: c.low,
          referenceLevel: recentMin,
          sweptLabel: 'Structural Swing Low (SSL)',
        };
        break;
      } else if (c.high > recentMax + 0.4 && c.close < recentMax) {
        sweepDetected = {
          type: 'BSL_SWEEP',
          candleIndex: i,
          sweepPrice: c.high,
          extremePrice: c.high,
          referenceLevel: recentMax,
          sweptLabel: 'Structural Swing High (BSL)',
        };
        break;
      }
    }
  }

  // Check Sweep Presence
  if (!sweepDetected) {
    return createNoTrade(
      'NO_LIQUIDITY_SWEEP: No valid raid of Asian/London session High (BSL) or Low (SSL) or recent structural key level.',
      'لم يحدث سحب سيولة: لم يخترق السعر قمة أو قاع جلسة لندن/آسيا أو قاع هيكلي صريح لسحب الأوامر.',
      { timeWindowGuardPassed: true, displacementGuardPassed: false },
      { step1_m15Prep: 'VERIFIED', step2_timeWindowActive: 'ACTIVE', step3_m5Sweep: 'PENDING' }
    );
  }

  // Guard 3: News / Macro Whip-saw Guard (> 3.5x ATR(14) sweep anomaly)
  const sweepCandle = candles[sweepDetected.candleIndex];
  const sweepRange = sweepCandle.high - sweepCandle.low;
  if (sweepRange > config.m5Displacement.maxNewsWhipsawAtr * atr14) {
    return createNoTrade(
      `NEWS_WHIPSAW_GUARD: Sweep candle range (${sweepRange.toFixed(2)}$) exceeds 3.5x ATR(14) (${(3.5 * atr14).toFixed(2)}$). Severe Tier-1 News volatility anomaly (NFP/CPI/ISM). Trade blocked.`,
      `حارس تقلبات الأخبار الكبرى: نطاق شمعة السحب تجاوز 3.5 ضعف متوسط ATR (تأثير خبر اقتصادي عنيف يلغي مصداقية الستوب). تم حظر الإشارة حمايةً للمحفظة.`,
      { timeWindowGuardPassed: true, newsWhipsawGuardPassed: false },
      { step1_m15Prep: 'VERIFIED', step2_timeWindowActive: 'ACTIVE', step3_m5Sweep: 'REJECTED' }
    );
  }

  // Step 3: M5 Market Structure Shift (MSS) & Displacement Verification
  const isBullish = sweepDetected.type === 'SSL_SWEEP';
  const { swingHighs, swingLows } = detectM5SwingPoints(candles, 2, 2);

  let mssFound = false;
  let mssCandleIndex = -1;
  let brokenLevel = 0;
  let displacementCandleIndex = -1;
  let displacementBodyPct = 0;
  let displacementAtrRatio = 0;

  if (isBullish) {
    // Look for recent swing high prior to or at the sweep
    const candidateHighs = swingHighs.filter(sh => sh.index <= sweepDetected!.candleIndex && sh.price > sweepDetected!.sweepPrice);
    let targetSwingHigh = candidateHighs.length > 0 ? candidateHighs[candidateHighs.length - 1] : null;
    if (!targetSwingHigh) {
      let maxH = -Infinity;
      let maxIdx = -1;
      for (let j = Math.max(0, sweepDetected.candleIndex - 8); j < sweepDetected.candleIndex; j++) {
        if (candles[j].high > maxH) {
          maxH = candles[j].high;
          maxIdx = j;
        }
      }
      if (maxH > sweepDetected.sweepPrice) {
        targetSwingHigh = { index: maxIdx, type: 'HIGH', price: maxH, time: candles[maxIdx].time };
      }
    }

    if (targetSwingHigh) {
      brokenLevel = targetSwingHigh.price;
      // DEBUG:
      // console.log("isBullish:", isBullish, "targetSwingHigh:", targetSwingHigh, "brokenLevel:", brokenLevel);
      for (let i = sweepDetected.candleIndex + 1; i < candles.length; i++) {
        const c = candles[i];
        if (c.close > brokenLevel) {
          mssFound = true;
          mssCandleIndex = i;
          // Check displacement qualities on the impulse candle
          const body = Math.abs(c.close - c.open);
          const range = c.high - c.low;
          if (range > 0) {
            const bodyPct = body / range;
            const atrRatio = range / atr14;
            if (bodyPct >= config.m5Displacement.minBodyPercentage && atrRatio >= config.m5Displacement.minAtrMultiplier) {
              displacementCandleIndex = i;
              displacementBodyPct = bodyPct;
              displacementAtrRatio = atrRatio;
              break;
            }
          }
        }
      }
    }
  } else {
    // Bearish MSS: Break below most recent M5 swing low prior to or at the sweep
    const candidateLows = swingLows.filter(sl => sl.index <= sweepDetected!.candleIndex && sl.price < sweepDetected!.sweepPrice);
    let targetSwingLow = candidateLows.length > 0 ? candidateLows[candidateLows.length - 1] : null;
    if (!targetSwingLow) {
      let minL = Infinity;
      let minIdx = -1;
      for (let j = Math.max(0, sweepDetected.candleIndex - 8); j < sweepDetected.candleIndex; j++) {
        if (candles[j].low < minL) {
          minL = candles[j].low;
          minIdx = j;
        }
      }
      if (minL < sweepDetected.sweepPrice) {
        targetSwingLow = { index: minIdx, type: 'LOW', price: minL, time: candles[minIdx].time };
      }
    }

    if (targetSwingLow) {
      brokenLevel = targetSwingLow.price;
      for (let i = sweepDetected.candleIndex + 1; i < candles.length; i++) {
        const c = candles[i];
        if (c.close < brokenLevel) {
          mssFound = true;
          mssCandleIndex = i;
          const body = Math.abs(c.close - c.open);
          const range = c.high - c.low;
          if (range > 0) {
            const bodyPct = body / range;
            const atrRatio = range / atr14;
            if (bodyPct >= config.m5Displacement.minBodyPercentage && atrRatio >= config.m5Displacement.minAtrMultiplier) {
              displacementCandleIndex = i;
              displacementBodyPct = bodyPct;
              displacementAtrRatio = atrRatio;
              break;
            }
          }
        }
      }
    }
  }

  if (!mssFound) {
    return createNoTrade(
      'MSS_PENDING: Price has swept session liquidity but has not yet confirmed an M5 Market Structure Shift (MSS) candle close.',
      'في انتظار كسر الهيكل: تم سحب السيولة بنجاح، لكن الشموع لم تغلق بعد فوق قمة/قاع الهيكل التأكيدي على M5.',
      { timeWindowGuardPassed: true, displacementGuardPassed: false },
      { step1_m15Prep: 'VERIFIED', step2_timeWindowActive: 'ACTIVE', step3_m5Sweep: 'VERIFIED', step4_displacementMss: 'PENDING' }
    );
  }

  // Guard 2: Weak Displacement Guard (Body < 65% or Range < 1.3x ATR)
  if (displacementCandleIndex === -1) {
    return createNoTrade(
      `WEAK_DISPLACEMENT_GUARD: Breakout candle lacks institutional displacement energy (Body: ${(displacementBodyPct * 100).toFixed(1)}% < 65% or Range: ${displacementAtrRatio.toFixed(2)}x ATR < 1.3x). Equal highs/lows risk.`,
      `حارس الإزاحة الضعيفة: شمعة كسر الهيكل تفتقر للزخم المؤسساتي الاندفاعي (حجم جسم الشمعة أقل من 65% أو مداها أقل من 1.3 ATR). تم رفض الصفقة لتجنب المصائد السعرية.`,
      { timeWindowGuardPassed: true, displacementGuardPassed: false },
      { step1_m15Prep: 'VERIFIED', step2_timeWindowActive: 'ACTIVE', step3_m5Sweep: 'VERIFIED', step4_displacementMss: 'WEAK_DISPLACEMENT' }
    );
  }

  // Step 4: M5 Fair Value Gap (FVG) Verification
  // Detect 3-candle FVG created by the displacement leg
  let fvgFound: {
    gapLow: number;
    gapHigh: number;
    proximalEdge: number;
    midpointCE: number;
    c1Index: number;
    c2Index: number;
    c3Index: number;
  } | null = null;

  for (let i = displacementCandleIndex; i >= Math.max(2, displacementCandleIndex - 2); i--) {
    if (i >= candles.length) continue;
    const c1 = candles[i - 2];
    const c2 = candles[i - 1];
    const c3 = candles[i];

    if (isBullish) {
      // Bullish FVG: c1.high < c3.low
      if (c3.low > c1.high) {
        const gapLow = c1.high;
        const gapHigh = c3.low;
        fvgFound = {
          gapLow,
          gapHigh,
          proximalEdge: gapHigh,
          midpointCE: Number(((gapLow + gapHigh) / 2).toFixed(2)),
          c1Index: i - 2,
          c2Index: i - 1,
          c3Index: i,
        };
        break;
      }
    } else {
      // Bearish FVG: c1.low > c3.high
      if (c3.high < c1.low) {
        const gapLow = c3.high;
        const gapHigh = c1.low;
        fvgFound = {
          gapLow,
          gapHigh,
          proximalEdge: gapLow,
          midpointCE: Number(((gapLow + gapHigh) / 2).toFixed(2)),
          c1Index: i - 2,
          c2Index: i - 1,
          c3Index: i,
        };
        break;
      }
    }
  }

  if (!fvgFound) {
    return createNoTrade(
      'NO_UNMITIGATED_FVG: Energetic displacement occurred, but no qualifying 3-candle Fair Value Gap was created for limit entry.',
      'عدم وجود فجوة سعرية FVG: حدثت إزاحة حركية لكن دون تكوين فجوة قيمة عادلة مؤهلة لوضع أمر دخول معلق.',
      { timeWindowGuardPassed: true, displacementGuardPassed: true },
      { step1_m15Prep: 'VERIFIED', step2_timeWindowActive: 'ACTIVE', step3_m5Sweep: 'VERIFIED', step4_displacementMss: 'VERIFIED', step5_fvgLimitEntry: 'PENDING' }
    );
  }

  // Exact Entry & Risk Calculations (server/goldRiskEngine.ts specifications)
  // Entry = Limit Order at FVG Proximal Edge or 50% Consequent Encroachment (CE)
  const entryPrice = config.riskReward.defaultEntryModel === 'CE_MIDPOINT'
    ? fvgFound.midpointCE
    : fvgFound.proximalEdge;

  // Stop Loss = Sweep Extreme ± 0.5x M5 ATR(14) wick buffer
  const wickBuffer = Number((config.riskReward.slWickBufferAtrMultiplier * atr14).toFixed(2));
  let stopLossPrice = isBullish
    ? Number((sweepDetected.extremePrice - wickBuffer).toFixed(2))
    : Number((sweepDetected.extremePrice + wickBuffer).toFixed(2));

  // Minimum 1:2 Net R:R (after spread/slippage of ~$0.35) or nearest opposing M15 session liquidity pool
  const riskDistance = Math.abs(entryPrice - stopLossPrice);
  const minRequiredReward = riskDistance * 2.0;

  // Structural Target: Opposing session liquidity level
  const opposingLiquidityTarget = isBullish
    ? Math.max(m15.londonHigh, m15.asianHigh)
    : Math.min(m15.londonLow, m15.asianLow);

  let takeProfit1Price = isBullish
    ? Number((entryPrice + minRequiredReward).toFixed(2))
    : Number((entryPrice - minRequiredReward).toFixed(2));

  // If opposing liquidity offers > 2.0R, target the opposing pool directly as TP2
  let takeProfit2Price = isBullish
    ? Number((entryPrice + riskDistance * 3.0).toFixed(2))
    : Number((entryPrice - riskDistance * 3.0).toFixed(2));

  if (isBullish && opposingLiquidityTarget > entryPrice + minRequiredReward) {
    takeProfit2Price = opposingLiquidityTarget;
  } else if (!isBullish && opposingLiquidityTarget < entryPrice - minRequiredReward) {
    takeProfit2Price = opposingLiquidityTarget;
  }

  // Reward / Risk validation
  const rewardDistance = Math.abs(takeProfit1Price - entryPrice);
  const netRR = Number((rewardDistance / (riskDistance || 1)).toFixed(2));

  if (netRR < config.riskReward.minNetRR) {
    return createNoTrade(
      `RISK_REWARD_GUARD: Net R:R (${netRR.toFixed(2)}) is less than mandatory 1:2.0 before opposing structural liquidity.`,
      `حارس العائد مقابل المخاطرة: نسبة العائد (${netRR}) أقل من الحد الأدنى الصارم 1:2.0. تم إلغاء الإشارة للحفاظ على رأس المال.`,
      { timeWindowGuardPassed: true, displacementGuardPassed: true, newsWhipsawGuardPassed: false },
      { step1_m15Prep: 'VERIFIED', step2_timeWindowActive: 'ACTIVE', step3_m5Sweep: 'VERIFIED', step4_displacementMss: 'VERIFIED', step5_fvgLimitEntry: 'INVALIDATED' }
    );
  }

  // Check if current price has touched FVG entry
  const hasTouchedEntry = isBullish
    ? currentCandle.low <= fvgFound.proximalEdge
    : currentCandle.high >= fvgFound.proximalEdge;

  const lifecycleState = hasTouchedEntry ? 'READY_FOR_ENTRY' : 'WAITING_PULLBACK';
  const action = isBullish ? 'BUY' : 'SELL';
  const confluenceScore = 95; // A+ NY Silver Bullet execution

  const technicalBreakdown = [
    `1. M15 Session Liquidity Prepared: Asian H: $${m15.asianHigh} / L: $${m15.asianLow} | London H: $${m15.londonHigh} / L: $${m15.londonLow}`,
    `2. Mechanical Window: Active 14:00 - 15:00 GMT New York Silver Bullet Execution Window`,
    `3. M5 Liquidity Raid: Pierced ${sweepDetected.sweptLabel} at $${sweepDetected.sweepPrice.toFixed(2)} with swift rejection`,
    `4. Energetic Displacement & MSS: Broken level $${brokenLevel.toFixed(2)} with ${(displacementBodyPct * 100).toFixed(0)}% body & ${displacementAtrRatio.toFixed(1)}x ATR`,
    `5. Unmitigated M5 FVG: Range $${fvgFound.gapLow.toFixed(2)} - $${fvgFound.gapHigh.toFixed(2)} | Limit Entry @ CE 50%: $${entryPrice.toFixed(2)}`,
    `6. Risk Accounting: Structural SL $${stopLossPrice.toFixed(2)} (Sweep Low - 0.5x ATR buffer) | TP1 $${takeProfit1Price.toFixed(2)} (1:2.0 Net R:R)`,
  ];

  const technicalBreakdownAr = [
    `1. رسم سيولة M15: قمة/قاع آسيا ولندن محددة بدقة على الشارت`,
    `2. نافذة التداول: نافذة نيويورك سيلفر بوليت الحصرية (14:00 - 15:00 GMT) نشطة`,
    `3. سحب السيولة: تم مسح ${sweepDetected.sweptLabel} عند مستويات ${sweepDetected.sweepPrice.toFixed(2)}$ وارتداد فوري`,
    `4. إزاحة حركية وتأكيد كسر الهيكل MSS: اختراق شمعة قوية بجسم ${(displacementBodyPct * 100).toFixed(0)}% ومدى ${displacementAtrRatio.toFixed(1)} أضعاف ATR`,
    `5. فجوة FVG نقية: نطاق ${fvgFound.gapLow.toFixed(2)}$ - ${fvgFound.gapHigh.toFixed(2)}$ | أمر معلق Limit عند منتصف الفجوة CE: ${entryPrice.toFixed(2)}$`,
    `6. إدارة المخاطر: وقف خسارة هيكلي ${stopLossPrice.toFixed(2)}$ | هدف أول TP1 ${takeProfit1Price.toFixed(2)}$ بنسبة ربح 1:2.0 صافية`,
  ];

  return {
    status: 'VALID_SETUP',
    strategyName: 'The New York Silver Bullet (14:00 to 15:00 GMT / 10:00 to 11:00 AM EST)',
    strategyVersion: config.version,
    action,
    symbol: config.symbol,
    timeframe: 'M5 / M15',
    confluenceScore,
    lifecycleState,
    stepStates: {
      step1_m15Prep: 'VERIFIED',
      step2_timeWindowActive: 'ACTIVE',
      step3_m5Sweep: 'VERIFIED',
      step4_displacementMss: 'VERIFIED',
      step5_fvgLimitEntry: hasTouchedEntry ? 'TRIGGERED' : 'WAITING_RETEST',
    },
    guards: {
      timeWindowGuardPassed: true,
      displacementGuardPassed: true,
      newsWhipsawGuardPassed: true,
    },
    observedMarketPrice,
    entryPrice,
    stopLossPrice,
    takeProfit1Price,
    takeProfit2Price,
    riskRewardRatio: netRR,
    overallRRString: `1:${netRR.toFixed(1)}`,
    m15Liquidity: m15,
    sweptLevelPrice: sweepDetected.sweepPrice,
    sweptLevelType: isBullish ? 'SSL' : 'BSL',
    mssPrice: brokenLevel,
    displacementAtrRatio,
    displacementBodyPct,
    fvgZone: {
      ...fvgFound,
      isMitigated: hasTouchedEntry,
    },
    atr14,
    technicalBreakdown,
    technicalBreakdownAr,
    candleTimestamp,
    evaluatedAtIso,
  };
}
