/**
 * Gold Sovereign AI - Quantitative Risk Engine
 * Instrument: XAU/USD (Spot Gold)
 * Version: 1.0.0-risk-engine
 * 
 * Analytical Trade Plan Generator & Risk Metrics Engine.
 * IMPORTANT: No real order execution. All calculations represent analytical trade plans.
 */

import { Candle } from "../src/types";

// ============================================================
// 1. CONTRACT SPECIFICATIONS & CONFIGURATION
// ============================================================

export interface XauUsdContractSpec {
  symbol: string;               // "XAU/USD"
  contractSizeOunces: number;   // e.g. 100 oz per standard lot
  tickSize: number;             // e.g. 0.01 ($0.01)
  tickValueUsd: number;         // e.g. $1.00 per $0.01 move for 100 oz lot
  typicalSpreadUsd: number;     // e.g. $0.25 ($0.25/oz = 2.5 pips)
  estimatedSlippageUsd: number; // e.g. $0.10
  accountCurrency: string;      // "USD"
  isValidated: boolean;         // true only when broker specs are verified
}

export const DEFAULT_XAU_CONTRACT_SPEC: XauUsdContractSpec = {
  symbol: "XAU/USD",
  contractSizeOunces: 100,
  tickSize: 0.01,
  tickValueUsd: 1.00,
  typicalSpreadUsd: 0.25,
  estimatedSlippageUsd: 0.10,
  accountCurrency: "USD",
  isValidated: true,
};

export interface PositionSizeEstimate {
  status: 'CALCULATED' | 'SIZE_UNAVAILABLE';
  riskAmountUsd: number;
  riskPercentage: number;
  accountEquity: number;
  lotSizeLots?: number;
  contractUnitsOunces?: number;
  explanationAr: string;
  explanationEn: string;
}

export interface RewardRiskMetrics {
  grossRiskDistance: number;         // |Entry - Stop|
  grossRewardDistanceTp1: number;    // |TP1 - Entry|
  grossRewardDistanceTp2: number;    // |TP2 - Entry|
  grossRRRatioTp1: number;           // gross TP1 R:R
  grossRRRatioTp2: number;           // gross TP2 R:R

  estimatedSpreadCostUsd: number;    // spread in $
  estimatedSlippageCostUsd: number;  // slippage in $
  estimatedNetRiskDistance: number;  // grossRisk + costs
  estimatedNetRewardDistanceTp1: number; // max(0, grossReward - costs)
  estimatedNetRewardDistanceTp2: number; // max(0, grossReward - costs)
  netRRRatioTp1: number;             // net TP1 R:R
  netRRRatioTp2: number;             // net TP2 R:R
  netEstimateComplete: boolean;      // true if validated costs were available
}

export type TradePlanLifecycleState =
  | 'CANDIDATE'
  | 'CONFIRMED'
  | 'PUBLISHED'
  | 'ENTRY_TOUCHED'
  | 'TP1_TOUCHED'
  | 'STOP_TOUCHED'
  | 'CLOSED_OR_EXPIRED';

export interface AnalyticalTradePlan {
  planId: string;
  strategyVersion: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  lifecycleState: TradePlanLifecycleState;

  // Explicit price distinctions
  observedMarketPrice: number;
  proposedEntryPrice: number;
  actualExecutableFillPrice: 'UNKNOWN_NO_REAL_EXECUTION';

  // Structural SL
  structuralInvalidationLevel: number;
  volatilityBufferAtr: number;
  proposedStopLoss: number;

  // Structural TP
  proposedTp1: number;
  proposedTp2: number;
  structuralLiquidityTarget: number;

  // Risk & Position Sizing
  metrics: RewardRiskMetrics;
  positionSize: PositionSizeEstimate;

  // Validation
  isValidPlan: boolean;
  rejectionReason?: string;
  rejectionReasonAr?: string;

  // Frozen Audit Inputs
  publishedAtIso: string;
  inputsFrozen: {
    atr14: number;
    spreadUsd: number;
    swingLevel: number;
    proposedEntry: number;
    proposedStop: number;
    proposedTp1: number;
    proposedTp2: number;
    netRR: number;
  };
}

// Memory ledger of published analytical trade plans
const publishedPlanRegistry = new Map<string, AnalyticalTradePlan>();

export function getPublishedPlanRegistry(): Map<string, AnalyticalTradePlan> {
  return publishedPlanRegistry;
}

// ============================================================
// 2. POSITION SIZE CALCULATOR
// ============================================================

export function calculatePositionSize(
  accountEquity: number,
  riskPercentage: number,
  entryPrice: number,
  stopLossPrice: number,
  contractSpec: XauUsdContractSpec | null
): PositionSizeEstimate {
  const riskAmountUsd = Number((accountEquity * (riskPercentage / 100)).toFixed(2));

  if (!contractSpec || !contractSpec.isValidated) {
    return {
      status: 'SIZE_UNAVAILABLE',
      riskAmountUsd,
      riskPercentage,
      accountEquity,
      explanationAr: "حجم اللوت غير متاح: مواصفات العقد لدى البروكر غير محددة أو غير مؤكدة.",
      explanationEn: "SIZE_UNAVAILABLE: Broker-specific contract specifications are unavailable or unvalidated.",
    };
  }

  const priceRiskDistance = Math.abs(entryPrice - stopLossPrice);
  if (priceRiskDistance <= 0 || isNaN(priceRiskDistance)) {
    return {
      status: 'SIZE_UNAVAILABLE',
      riskAmountUsd,
      riskPercentage,
      accountEquity,
      explanationAr: "حجم اللوت غير متاح: مسافة الستوب لاغية أو تساوي صفر.",
      explanationEn: "SIZE_UNAVAILABLE: Invalid or zero stop distance.",
    };
  }

  // Contract risk per standard lot = priceRiskDistance * contractSizeOunces
  // Example: $10 risk on 100 oz lot = $1,000 risk per 1.0 lot
  const riskPerLotUsd = priceRiskDistance * contractSpec.contractSizeOunces;
  const rawLots = riskAmountUsd / riskPerLotUsd;
  const lotSizeLots = Number(Math.max(0.01, Math.floor(rawLots * 100) / 100).toFixed(2));
  const contractUnitsOunces = Number((lotSizeLots * contractSpec.contractSizeOunces).toFixed(1));

  return {
    status: 'CALCULATED',
    riskAmountUsd,
    riskPercentage,
    accountEquity,
    lotSizeLots,
    contractUnitsOunces,
    explanationAr: `الحجم التقديري: ${lotSizeLots} لوت (${contractUnitsOunces} أونصة) بمخاطرة $${riskAmountUsd} (${riskPercentage}%)`,
    explanationEn: `Estimated size: ${lotSizeLots} lots (${contractUnitsOunces} oz) with $${riskAmountUsd} risk (${riskPercentage}%)`,
  };
}

// ============================================================
// 3. REWARD / RISK METRICS CALCULATOR
// ============================================================

export function calculateRewardRiskMetrics(
  entryPrice: number,
  stopLossPrice: number,
  tp1Price: number,
  tp2Price: number,
  contractSpec: XauUsdContractSpec | null
): RewardRiskMetrics {
  const grossRiskDistance = Number(Math.abs(entryPrice - stopLossPrice).toFixed(2));
  const grossRewardDistanceTp1 = Number(Math.abs(tp1Price - entryPrice).toFixed(2));
  const grossRewardDistanceTp2 = Number(Math.abs(tp2Price - entryPrice).toFixed(2));

  const grossRRRatioTp1 = grossRiskDistance > 0 ? Number((grossRewardDistanceTp1 / grossRiskDistance).toFixed(2)) : 0;
  const grossRRRatioTp2 = grossRiskDistance > 0 ? Number((grossRewardDistanceTp2 / grossRiskDistance).toFixed(2)) : 0;

  if (!contractSpec || !contractSpec.isValidated) {
    return {
      grossRiskDistance,
      grossRewardDistanceTp1,
      grossRewardDistanceTp2,
      grossRRRatioTp1,
      grossRRRatioTp2,
      estimatedSpreadCostUsd: 0,
      estimatedSlippageCostUsd: 0,
      estimatedNetRiskDistance: grossRiskDistance,
      estimatedNetRewardDistanceTp1: grossRewardDistanceTp1,
      estimatedNetRewardDistanceTp2: grossRewardDistanceTp2,
      netRRRatioTp1: grossRRRatioTp1,
      netRRRatioTp2: grossRRRatioTp2,
      netEstimateComplete: false,
    };
  }

  const spreadCost = contractSpec.typicalSpreadUsd;
  const slippageCost = contractSpec.estimatedSlippageUsd;
  const totalCostUsd = Number((spreadCost + slippageCost).toFixed(2));

  const estimatedNetRiskDistance = Number((grossRiskDistance + totalCostUsd).toFixed(2));
  const estimatedNetRewardDistanceTp1 = Number(Math.max(0, grossRewardDistanceTp1 - totalCostUsd).toFixed(2));
  const estimatedNetRewardDistanceTp2 = Number(Math.max(0, grossRewardDistanceTp2 - totalCostUsd).toFixed(2));

  const netRRRatioTp1 = estimatedNetRiskDistance > 0 ? Number((estimatedNetRewardDistanceTp1 / estimatedNetRiskDistance).toFixed(2)) : 0;
  const netRRRatioTp2 = estimatedNetRiskDistance > 0 ? Number((estimatedNetRewardDistanceTp2 / estimatedNetRiskDistance).toFixed(2)) : 0;

  return {
    grossRiskDistance,
    grossRewardDistanceTp1,
    grossRewardDistanceTp2,
    grossRRRatioTp1,
    grossRRRatioTp2,
    estimatedSpreadCostUsd: spreadCost,
    estimatedSlippageCostUsd: slippageCost,
    estimatedNetRiskDistance,
    estimatedNetRewardDistanceTp1,
    estimatedNetRewardDistanceTp2,
    netRRRatioTp1,
    netRRRatioTp2,
    netEstimateComplete: true,
  };
}

// ============================================================
// 4. ANALYTICAL TRADE PLAN GENERATOR
// ============================================================

export interface PlanGenerationInput {
  symbol: string;                     // "XAU/USD"
  direction: 'BUY' | 'SELL';
  observedMarketPrice: number;
  proposedEntryPrice: number;
  structuralLevel: number;            // Confirmed Swing Low/High
  atr14: number;
  structuralTarget?: number;          // Major opposing liquidity level
  accountEquity?: number;             // Default $10,000
  riskPercentage?: number;            // Default 1.0%
  contractSpec?: XauUsdContractSpec | null;
  minNetRRRequired?: number;          // Default 1.5
  volatilityBufferAtrMultiplier?: number; // Default 0.5
}

export function generateAnalyticalTradePlan(input: PlanGenerationInput): AnalyticalTradePlan {
  const {
    symbol = "XAU/USD",
    direction,
    observedMarketPrice,
    proposedEntryPrice,
    structuralLevel,
    atr14,
    structuralTarget,
    accountEquity = 10000,
    riskPercentage = 1.0,
    contractSpec = DEFAULT_XAU_CONTRACT_SPEC,
    minNetRRRequired = 2.0,
    volatilityBufferAtrMultiplier = 0.5,
  } = input;

  const publishedAtIso = new Date().toISOString();
  const planId = `plan-${symbol.replace(/[^a-zA-Z0-9]/g, '').toLowerCase()}-${Date.now()}`;

  const isBuy = direction === 'BUY';

  // 1. VALIDATE ATR & STRUCTURAL LEVEL
  if (atr14 <= 0 || isNaN(atr14)) {
    return buildRejectedPlan(
      planId,
      symbol,
      direction,
      observedMarketPrice,
      proposedEntryPrice,
      "INVALID_ATR: ATR(14) must be greater than zero.",
      "معدل ATR(14) غير صالح أو يساوي صفر."
    );
  }

  const volatilityBufferAtr = Number((volatilityBufferAtrMultiplier * atr14).toFixed(2));

  // 2. STRUCTURAL STOP LOSS CALCULATION
  const proposedStopLoss = isBuy
    ? Number((structuralLevel - volatilityBufferAtr).toFixed(2))
    : Number((structuralLevel + volatilityBufferAtr).toFixed(2));

  // Validate Stop Loss relative to Entry
  const isStopValid = isBuy ? proposedStopLoss < proposedEntryPrice : proposedStopLoss > proposedEntryPrice;
  const grossRiskDistance = Math.abs(proposedEntryPrice - proposedStopLoss);

  if (!isStopValid || grossRiskDistance <= 0) {
    return buildRejectedPlan(
      planId,
      symbol,
      direction,
      observedMarketPrice,
      proposedEntryPrice,
      `INVALID_STOP_LOSS: Proposed stop ($${proposedStopLoss}) must be ${isBuy ? 'below' : 'above'} proposed entry ($${proposedEntryPrice}).`,
      `مستوى الستوب ($${proposedStopLoss}) غير صالح مقارنة بسعر الدخول ($${proposedEntryPrice}).`
    );
  }

  // 3. TARGET CALCULATION & STRUCTURAL LIQUIDITY VALIDATION
  let proposedTp1 = isBuy
    ? Number((proposedEntryPrice + grossRiskDistance * 1.5).toFixed(2))
    : Number((proposedEntryPrice - grossRiskDistance * 1.5).toFixed(2));

  let proposedTp2 = isBuy
    ? Number((proposedEntryPrice + grossRiskDistance * 3.0).toFixed(2))
    : Number((proposedEntryPrice - grossRiskDistance * 3.0).toFixed(2));

  const defaultStructuralLiquidityTarget = isBuy
    ? Number((proposedEntryPrice + grossRiskDistance * 3.5).toFixed(2))
    : Number((proposedEntryPrice - grossRiskDistance * 3.5).toFixed(2));

  const liquidityTarget = structuralTarget || defaultStructuralLiquidityTarget;

  // Validate targets against opposing structural liquidity level
  const targetConflict = isBuy ? liquidityTarget < proposedTp1 : liquidityTarget > proposedTp1;
  if (targetConflict) {
    return buildRejectedPlan(
      planId,
      symbol,
      direction,
      observedMarketPrice,
      proposedEntryPrice,
      `STRUCTURAL_TARGET_CONFLICT: Major liquidity target ($${liquidityTarget}) is closer than TP1 ($${proposedTp1}).`,
      `تعارض مع هيكل السوق: سيولة المقاومة ($${liquidityTarget}) أقرب من الهدف الأول ($${proposedTp1}).`
    );
  }

  // 4. REWARD / RISK METRICS & NET R:R VALIDATION
  const metrics = calculateRewardRiskMetrics(
    proposedEntryPrice,
    proposedStopLoss,
    proposedTp1,
    proposedTp2,
    contractSpec
  );

  const effectiveNetRR = metrics.netEstimateComplete ? metrics.netRRRatioTp2 : metrics.grossRRRatioTp2;
  if (effectiveNetRR < minNetRRRequired) {
    return buildRejectedPlan(
      planId,
      symbol,
      direction,
      observedMarketPrice,
      proposedEntryPrice,
      `INSUFFICIENT_NET_RR: Estimated net R:R (1:${effectiveNetRR}) is below minimum required 1:${minNetRRRequired}.`,
      `صافي نسبة العائد إلى المخاطرة (1:${effectiveNetRR}) أقل من الحد الأدنى المقبول (1:${minNetRRRequired}).`
    );
  }

  // 5. POSITION SIZING ESTIMATE
  const positionSize = calculatePositionSize(
    accountEquity,
    riskPercentage,
    proposedEntryPrice,
    proposedStopLoss,
    contractSpec
  );

  // BUILD VALID PUBLISHED ANALYTICAL PLAN
  const plan: AnalyticalTradePlan = {
    planId,
    strategyVersion: "v2.0.0-ny-silver-bullet",
    symbol,
    direction,
    lifecycleState: 'PUBLISHED',
    observedMarketPrice,
    proposedEntryPrice,
    actualExecutableFillPrice: 'UNKNOWN_NO_REAL_EXECUTION',
    structuralInvalidationLevel: structuralLevel,
    volatilityBufferAtr,
    proposedStopLoss,
    proposedTp1,
    proposedTp2,
    structuralLiquidityTarget: liquidityTarget,
    metrics,
    positionSize,
    isValidPlan: true,
    publishedAtIso,
    inputsFrozen: {
      atr14,
      spreadUsd: contractSpec?.typicalSpreadUsd || 0,
      swingLevel: structuralLevel,
      proposedEntry: proposedEntryPrice,
      proposedStop: proposedStopLoss,
      proposedTp1,
      proposedTp2,
      netRR: metrics.netRRRatioTp2,
    },
  };

  publishedPlanRegistry.set(planId, plan);
  return plan;
}

function buildRejectedPlan(
  planId: string,
  symbol: string,
  direction: 'BUY' | 'SELL',
  observedMarketPrice: number,
  proposedEntryPrice: number,
  rejectionReason: string,
  rejectionReasonAr: string
): AnalyticalTradePlan {
  return {
    planId,
    strategyVersion: "1.0.0-gold-smc",
    symbol,
    direction,
    lifecycleState: 'CLOSED_OR_EXPIRED',
    observedMarketPrice,
    proposedEntryPrice,
    actualExecutableFillPrice: 'UNKNOWN_NO_REAL_EXECUTION',
    structuralInvalidationLevel: 0,
    volatilityBufferAtr: 0,
    proposedStopLoss: 0,
    proposedTp1: 0,
    proposedTp2: 0,
    structuralLiquidityTarget: 0,
    metrics: {
      grossRiskDistance: 0,
      grossRewardDistanceTp1: 0,
      grossRewardDistanceTp2: 0,
      grossRRRatioTp1: 0,
      grossRRRatioTp2: 0,
      estimatedSpreadCostUsd: 0,
      estimatedSlippageCostUsd: 0,
      estimatedNetRiskDistance: 0,
      estimatedNetRewardDistanceTp1: 0,
      estimatedNetRewardDistanceTp2: 0,
      netRRRatioTp1: 0,
      netRRRatioTp2: 0,
      netEstimateComplete: false,
    },
    positionSize: {
      status: 'SIZE_UNAVAILABLE',
      riskAmountUsd: 0,
      riskPercentage: 0,
      accountEquity: 0,
      explanationAr: rejectionReasonAr,
      explanationEn: rejectionReason,
    },
    isValidPlan: false,
    rejectionReason,
    rejectionReasonAr,
    publishedAtIso: new Date().toISOString(),
    inputsFrozen: {
      atr14: 0,
      spreadUsd: 0,
      swingLevel: 0,
      proposedEntry: 0,
      proposedStop: 0,
      proposedTp1: 0,
      proposedTp2: 0,
      netRR: 0,
    },
  };
}

// ============================================================
// 5. LIFECYCLE STATE MACHINE & TICK EVALUATION
// ============================================================

export interface LifecycleEvaluationInput {
  plan: AnalyticalTradePlan;
  currentCandle: Candle;
  previousCandle?: Candle;
  candlesSincePublished?: number; // expiry check (max 20)
}

export function evaluatePlanLifecycle(input: LifecycleEvaluationInput): AnalyticalTradePlan {
  const { plan, currentCandle, previousCandle, candlesSincePublished = 0 } = input;

  if (!plan.isValidPlan || plan.lifecycleState === 'CLOSED_OR_EXPIRED' || plan.lifecycleState === 'STOP_TOUCHED') {
    return plan;
  }

  const updatedPlan = { ...plan };
  const isBuy = plan.direction === 'BUY';
  const entry = plan.proposedEntryPrice;
  const stop = plan.proposedStopLoss;
  const tp1 = plan.proposedTp1;
  const tp2 = plan.proposedTp2;

  // 1. EXPIRY CHECK
  if (plan.lifecycleState === 'PUBLISHED' && candlesSincePublished > 20) {
    updatedPlan.lifecycleState = 'CLOSED_OR_EXPIRED';
    return updatedPlan;
  }

  // 2. CHECK PRE-ENTRY CANCELLATION / INVALIDATION
  if (plan.lifecycleState === 'PUBLISHED') {
    const isSlBreachedBeforeEntry = isBuy
      ? currentCandle.low <= stop
      : currentCandle.high >= stop;

    const isEntryTouched = isBuy
      ? currentCandle.low <= entry
      : currentCandle.high >= entry;

    if (isSlBreachedBeforeEntry && !isEntryTouched) {
      updatedPlan.lifecycleState = 'CLOSED_OR_EXPIRED';
      return updatedPlan;
    }

    if (isEntryTouched) {
      updatedPlan.lifecycleState = 'ENTRY_TOUCHED';
    }
  }

  // 3. CHECK ACTIVE TRADE TRANSITIONS AFTER ENTRY TOUCHED
  if (updatedPlan.lifecycleState === 'ENTRY_TOUCHED' || updatedPlan.lifecycleState === 'TP1_TOUCHED') {
    const activeStop = updatedPlan.lifecycleState === 'TP1_TOUCHED' ? entry : stop; // Breakeven after TP1

    // Intrabar Collision Check (Single candle touches both Stop and TP)
    const isStopTouched = isBuy ? currentCandle.low <= activeStop : currentCandle.high >= activeStop;
    const isTp1Touched = isBuy ? currentCandle.high >= tp1 : currentCandle.low <= tp1;
    const isTp2Touched = isBuy ? currentCandle.high >= tp2 : currentCandle.low <= tp2;

    if (isStopTouched && isTp1Touched) {
      // Intrabar Collision Rule: Assume worst-case capital preservation execution -> STOP_TOUCHED
      // (Unless candle open gap clearly triggered TP first)
      if (isBuy && currentCandle.open >= tp1) {
        updatedPlan.lifecycleState = 'TP1_TOUCHED';
      } else {
        updatedPlan.lifecycleState = 'STOP_TOUCHED';
      }
      return updatedPlan;
    }

    if (isStopTouched) {
      updatedPlan.lifecycleState = 'STOP_TOUCHED';
      return updatedPlan;
    }

    if (isTp2Touched) {
      updatedPlan.lifecycleState = 'CLOSED_OR_EXPIRED';
      return updatedPlan;
    }

    if (isTp1Touched && updatedPlan.lifecycleState === 'ENTRY_TOUCHED') {
      updatedPlan.lifecycleState = 'TP1_TOUCHED';
      // Deterministic Breakeven Rule: Proposed Stop moves to Entry Price
      updatedPlan.proposedStopLoss = entry;
      return updatedPlan;
    }
  }

  return updatedPlan;
}
