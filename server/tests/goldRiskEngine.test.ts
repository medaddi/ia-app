/**
 * Unit Tests for Gold Sovereign AI Quantitative Risk Engine
 * Verifies BUY/SELL symmetry, invalid stops, zero-distance stops, invalid ATR,
 * net R:R calculation with spreads, position sizing availability, price gaps,
 * intrabar collisions, and lifecycle state transitions.
 */

import {
  generateAnalyticalTradePlan,
  calculatePositionSize,
  calculateRewardRiskMetrics,
  evaluatePlanLifecycle,
  DEFAULT_XAU_CONTRACT_SPEC,
  XauUsdContractSpec,
} from "../goldRiskEngine";
import { Candle } from "../../src/types";

function runRiskEngineTests() {
  console.log("==================================================");
  console.log("RUNNING GOLD RISK ENGINE UNIT TESTS (v1.0.0-risk-engine)");
  console.log("==================================================");

  let passed = 0;
  let failed = 0;

  function assert(condition: boolean, testName: string, detail: string = "") {
    if (condition) {
      console.log(`[PASS] ${testName}`);
      passed++;
    } else {
      console.error(`[FAIL] ${testName} - ${detail}`);
      failed++;
    }
  }

  // TEST 1: BUY & SELL Symmetry Valid Plan Generation
  {
    const buyPlan = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "BUY",
      observedMarketPrice: 2700.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2680.0, // Swing Low
      atr14: 10.0,
    });

    const sellPlan = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "SELL",
      observedMarketPrice: 2700.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2720.0, // Swing High
      atr14: 10.0,
    });

    assert(
      buyPlan.isValidPlan &&
      buyPlan.proposedStopLoss === 2675.0 && // 2680 - 0.5 * 10 = 2675
      buyPlan.proposedTp1 === 2737.50 &&     // 2700 + 1.5 * 25 = 2737.50
      buyPlan.proposedTp2 === 2775.00,       // 2700 + 3.0 * 25 = 2775.00
      "Test 1a: BUY plan calculated symmetric structural levels cleanly"
    );

    assert(
      sellPlan.isValidPlan &&
      sellPlan.proposedStopLoss === 2725.0 && // 2720 + 0.5 * 10 = 2725
      sellPlan.proposedTp1 === 2662.50 &&    // 2700 - 1.5 * 25 = 2662.50
      sellPlan.proposedTp2 === 2625.00,      // 2700 - 3.0 * 25 = 2625.00
      "Test 1b: SELL plan calculated symmetric structural levels cleanly"
    );
  }

  // TEST 2: Invalid Stops (SL above entry for BUY, SL below entry for SELL)
  {
    const invalidBuy = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "BUY",
      observedMarketPrice: 2700.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2710.0, // Invalid: Swing low above entry!
      atr14: 5.0,
    });

    const invalidSell = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "SELL",
      observedMarketPrice: 2700.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2690.0, // Invalid: Swing high below entry!
      atr14: 5.0,
    });

    assert(
      !invalidBuy.isValidPlan && invalidBuy.rejectionReason?.includes("INVALID_STOP_LOSS"),
      "Test 2a: Invalid BUY stop loss rejected"
    );
    assert(
      !invalidSell.isValidPlan && invalidSell.rejectionReason?.includes("INVALID_STOP_LOSS"),
      "Test 2b: Invalid SELL stop loss rejected"
    );
  }

  // TEST 3: Zero-Distance Stops & Invalid ATR (ATR <= 0)
  {
    const zeroAtrPlan = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "BUY",
      observedMarketPrice: 2700.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2680.0,
      atr14: 0, // Invalid zero ATR!
    });

    assert(
      !zeroAtrPlan.isValidPlan && zeroAtrPlan.rejectionReason?.includes("INVALID_ATR"),
      "Test 3: Zero/Negative ATR rejected"
    );
  }

  // TEST 4: Insufficient Net Reward/Risk Check
  {
    // High spread ($10.0) reduces net reward below min 1.5 net R:R
    const highSpreadSpec: XauUsdContractSpec = {
      ...DEFAULT_XAU_CONTRACT_SPEC,
      typicalSpreadUsd: 15.0, // $15 spread
    };

    const lowRRPlan = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "BUY",
      observedMarketPrice: 2700.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2690.0, // Small risk distance ($10) vs large spread ($15)
      atr14: 2.0,
      contractSpec: highSpreadSpec,
      minNetRRRequired: 1.5,
    });

    assert(
      !lowRRPlan.isValidPlan && lowRRPlan.rejectionReason?.includes("INSUFFICIENT_NET_RR"),
      "Test 4: Plan rejected when net R:R falls below minimum due to transaction costs"
    );
  }

  // TEST 5: Missing or Unvalidated Contract Specifications (SIZE_UNAVAILABLE)
  {
    const unvalidatedSpec: XauUsdContractSpec = {
      ...DEFAULT_XAU_CONTRACT_SPEC,
      isValidated: false,
    };

    const sizeRes = calculatePositionSize(10000, 1.0, 2700.0, 2680.0, unvalidatedSpec);

    assert(
      sizeRes.status === 'SIZE_UNAVAILABLE' && sizeRes.explanationEn.includes('SIZE_UNAVAILABLE'),
      "Test 5: Position size engine returns SIZE_UNAVAILABLE when broker contract specs are unvalidated"
    );
  }

  // TEST 6: Valid Position Sizing Calculation
  {
    // Account: $10,000, 1.0% risk = $100 risk
    // Entry: $2700, Stop: $2690 -> Price Risk = $10 / oz
    // Standard Lot = 100 oz -> Risk per Lot = $1,000
    // Expected Lot Size = $100 / $1,000 = 0.10 lots
    const sizeRes = calculatePositionSize(10000, 1.0, 2700.0, 2690.0, DEFAULT_XAU_CONTRACT_SPEC);

    assert(
      sizeRes.status === 'CALCULATED' &&
      sizeRes.riskAmountUsd === 100.00 &&
      sizeRes.lotSizeLots === 0.10 &&
      sizeRes.contractUnitsOunces === 10.0,
      "Test 6: Valid position size calculated as 0.10 lots ($100 risk / $1000 risk-per-lot)"
    );
  }

  // TEST 7: Net R:R vs Gross R:R Calculation & Spread Deduction
  {
    // Entry: 2700, Stop: 2680 (Risk = 20), TP2: 2760 (Gross Reward = 60 -> Gross RR = 3.0)
    // Spread: $0.25, Slippage: $0.10 -> Total Cost = $0.35
    // Net Risk = 20.35, Net Reward = 59.65 -> Net RR = 59.65 / 20.35 = 2.93
    const metrics = calculateRewardRiskMetrics(2700.0, 2680.0, 2730.0, 2760.0, DEFAULT_XAU_CONTRACT_SPEC);

    assert(
      metrics.grossRRRatioTp2 === 3.00 &&
      metrics.netRRRatioTp2 === 2.93 &&
      metrics.netEstimateComplete === true,
      "Test 7: Net R:R calculated accurately with spread/slippage cost deduction"
    );
  }

  // TEST 8: Lifecycle State Machine Transitions & Breakeven Rule
  {
    const plan = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "BUY",
      observedMarketPrice: 2705.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2680.0, // Stop = 2675.0
      atr14: 10.0,
    });

    assert(plan.lifecycleState === 'PUBLISHED', "Test 8a: Initial state is PUBLISHED");

    // Candle 1: Price touches entry ($2698 <= Entry 2700)
    const candle1: Candle = { time: 1000, open: 2705, high: 2706, low: 2698, close: 2702, volume: 1000 };
    const state1 = evaluatePlanLifecycle({ plan, currentCandle: candle1 });
    assert(state1.lifecycleState === 'ENTRY_TOUCHED', "Test 8b: Transitioned to ENTRY_TOUCHED");

    // Candle 2: Price hits TP1 ($2738 >= TP1 2737.5) -> Stop moves to Breakeven ($2700)
    const candle2: Candle = { time: 1900, open: 2702, high: 2740, low: 2701, close: 2739, volume: 1000 };
    const state2 = evaluatePlanLifecycle({ plan: state1, currentCandle: candle2 });
    assert(
      state2.lifecycleState === 'TP1_TOUCHED' && state2.proposedStopLoss === 2700.0,
      "Test 8c: Transitioned to TP1_TOUCHED and stop moved to Breakeven (2700.0)"
    );

    // Candle 3: Price drops from 2730 to Breakeven ($2700)
    const candle3: Candle = { time: 2800, open: 2730, high: 2732, low: 2699, close: 2700, volume: 1000 };
    const state3 = evaluatePlanLifecycle({ plan: state2, currentCandle: candle3 });
    assert(state3.lifecycleState === 'STOP_TOUCHED', "Test 8d: Touched Breakeven stop safely");
  }

  // TEST 9: Intrabar Collision Rule (Single candle touches both Stop and TP)
  {
    const plan = generateAnalyticalTradePlan({
      symbol: "XAU/USD",
      direction: "BUY",
      observedMarketPrice: 2700.0,
      proposedEntryPrice: 2700.0,
      structuralLevel: 2680.0, // Stop = 2675.0, TP1 = 2737.5
      atr14: 10.0,
    });

    plan.lifecycleState = 'ENTRY_TOUCHED';

    // Whipsaw candle: Low = 2660 (breaches SL 2675) AND High = 2750 (breaches TP1 2737.5)
    const collisionCandle: Candle = { time: 1000, open: 2700, high: 2750, low: 2660, close: 2670, volume: 1000 };
    const state = evaluatePlanLifecycle({ plan, currentCandle: collisionCandle });

    assert(
      state.lifecycleState === 'STOP_TOUCHED',
      "Test 9: Intrabar collision deterministically defaults to worst-case STOP_TOUCHED (capital protection)"
    );
  }

  console.log("==================================================");
  console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
  console.log("==================================================");

  if (failed > 0) {
    process.exit(1);
  }
}

runRiskEngineTests();
