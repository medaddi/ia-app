/**
 * Unit Tests for The New York Silver Bullet Strategy (v2.0.0-ny-silver-bullet)
 * Verifies M15 Liquidity Mapping, 14:00-15:00 GMT Time Window Guard,
 * M5 Sweep, MSS Energetic Displacement (>65% body, >1.3x ATR),
 * Unmitigated FVG, News Whip-saw Guard (>3.5x ATR), and Minimum 1:2 Net R:R.
 */

import { evaluateGoldSmcStrategy, DEFAULT_NY_SILVER_BULLET_CONFIG, mapM15SessionLiquidity } from "../goldSmcStrategy";
import { Candle } from "../../src/types";

function createBaseCandles(count: number = 35, basePrice: number = 2715): Candle[] {
  const candles: Candle[] = [];
  const d = new Date();
  d.setUTCHours(14, 0, 0, 0); // Exactly 14:00 GMT at index 21
  const fourteenGmtSec = Math.floor(d.getTime() / 1000);
  const stepSec = 300; // 5-minute candles

  let p = basePrice;
  for (let i = 0; i < count; i++) {
    // i = 21 will be 14:00:00 GMT
    // i < 21 will be before 14:00 GMT (London preparation session)
    // i >= 21 will be inside 14:00-15:00 GMT (Silver Bullet window)
    const time = fourteenGmtSec + (i - 21) * stepSec;
    const open = p;
    const high = open + 1.2;
    const low = open - 1.2;
    const close = open + 0.3;
    candles.push({ time, open, high, low, close, volume: 1500 });
    p = close;
  }
  return candles;
}

function runTests() {
  console.log("==================================================");
  console.log("RUNNING NY SILVER BULLET UNIT TESTS (v2.0.0-ny-silver-bullet)");
  console.log("==================================================");

  let passed = 0;
  let failed = 0;

  function assert(condition: boolean, testName: string, detail: string = "", res?: any) {
    if (condition) {
      console.log(`[PASS] ${testName}`);
      passed++;
    } else {
      console.error(`[FAIL] ${testName} - ${detail}`);
      if (res) {
        console.error("  Status:", res.status, "Score:", res.confluenceScore);
        console.error("  Rejection:", res.rejectionReason);
      }
      failed++;
    }
  }

  // TEST 1: Insufficient Candles (<20 candles)
  {
    const shortCandles = createBaseCandles(12, 2715);
    const res = evaluateGoldSmcStrategy(shortCandles);
    assert(
      res.status === 'NO_TRADE' && res.rejectionReason?.includes('INSUFFICIENT_CANDLE_DATA') === true,
      "Test 1: Insufficient candles returns NO_TRADE"
    );
  }

  // TEST 2: Strict Time Window Guard (e.g. 11:30 GMT outside 14:00-15:00 GMT)
  {
    const candles = createBaseCandles(25, 2715);
    // Alter timestamps to 11:30 GMT (outside Silver Bullet window)
    const outD = new Date();
    outD.setUTCHours(11, 30, 0, 0);
    const outTime = Math.floor(outD.getTime() / 1000);
    for (let i = 0; i < candles.length; i++) {
      candles[i].time = outTime - (candles.length - 1 - i) * 300;
    }

    // Default config runs 24h (enforceTimeWindow: false), so enable the strict guard explicitly
    const strictConfig = {
      ...DEFAULT_NY_SILVER_BULLET_CONFIG,
      timeWindow: { ...DEFAULT_NY_SILVER_BULLET_CONFIG.timeWindow, enforceTimeWindow: true },
    };
    const res = evaluateGoldSmcStrategy(candles, strictConfig);
    assert(
      res.status === 'NO_TRADE' && res.guards.timeWindowGuardPassed === false && res.rejectionReason?.includes('TIME_WINDOW_GUARD') === true,
      "Test 2: Time Window Guard rejects evaluation outside 14:00-15:00 GMT"
    );
  }

  // TEST 3: Step 1 Pre-14:00 M15 Liquidity Mapping
  {
    const candles = createBaseCandles(30, 2715);
    const m15 = mapM15SessionLiquidity(candles);
    assert(
      m15.asianHigh > 0 && m15.asianLow > 0 && m15.londonHigh >= m15.londonLow,
      "Test 3: M15 Session Liquidity correctly maps Asian & London High/Low"
    );
  }

  // TEST 4: Valid BUY Setup (SSL Sweep + MSS Energetic Displacement + Unmitigated FVG)
  {
    const candles = createBaseCandles(35, 2710);
    // In candles 0..20 (pre-14:00 GMT London session), establish clean levels:
    for (let i = 0; i <= 21; i++) {
      candles[i].open = 2710.0;
      candles[i].close = 2710.5;
      candles[i].high = 2712.0;
      candles[i].low = 2709.0;
    }
    // Set London Low at index 5: 2708.0
    candles[5].low = 2708.0;
    // Set London High at index 10: 2716.0
    candles[10].high = 2716.0;

    // Index 15: Established M5 Swing High at 2713.0
    candles[15].open = 2710.0;
    candles[15].high = 2713.0; // Swing High
    candles[15].low = 2709.5;
    candles[15].close = 2711.0;

    // Index 22 (inside 14:00-15:00 GMT window): M5 SSL Sweep Candle
    // Sweeps below London Low 2708.0 to 2706.5, closes back inside at 2708.5
    candles[22].open = 2709.0;
    candles[22].high = 2710.0;
    candles[22].low = 2706.5; // Swept SSL!
    candles[22].close = 2708.5; // Closed back inside

    // Index 23: Consolidation candle below swing high 2713.0
    candles[23].open = 2708.5;
    candles[23].high = 2711.0;
    candles[23].low = 2708.0;
    candles[23].close = 2710.0;

    // Index 24: MSS Energetic Displacement Candle (Body > 65%, Range > 1.3x ATR)
    // Breaks above Swing High 2713.0 and London High 2716.0
    candles[24].open = 2711.0;
    candles[24].low = 2710.5;
    candles[24].high = 2722.0;
    candles[24].close = 2721.0; // Body = 10.0, Range = 11.5 (87% body, > 5x ATR)

    // Index 25-27: Create Bullish FVG (c1.high < c3.low)
    candles[25].open = 2717.0;
    candles[25].high = 2718.0; // c1 high
    candles[25].low = 2716.0;
    candles[25].close = 2717.5;

    candles[26].open = 2718.0;
    candles[26].high = 2727.0; // impulse
    candles[26].low = 2717.5;
    candles[26].close = 2726.5;

    candles[27].open = 2726.5;
    candles[27].high = 2730.0;
    candles[27].low = 2721.0; // c3 low (> c1.high 2718 -> FVG 2718 to 2721, CE = 2719.5)
    candles[27].close = 2729.0;

    // Current candle 28: Pullback touching FVG proximal edge (low dips to 2720.5 <= 2721.0)
    candles[28].open = 2729.0;
    candles[28].high = 2730.0;
    candles[28].low = 2720.5; // Touched FVG!
    candles[28].close = 2727.0;

    const res = evaluateGoldSmcStrategy(candles, DEFAULT_NY_SILVER_BULLET_CONFIG, { bypassTimeWindow: true });
    assert(
      res.status === 'VALID_SETUP' && res.action === 'BUY' && res.riskRewardRatio >= 2.0 && res.fvgZone !== null,
      "Test 4: M5 BUY Silver Bullet Setup successfully validated with SSL Sweep + MSS + FVG",
      res.rejectionReason,
      res
    );
  }

  // TEST 5: Weak Displacement Guard (Rejection when candle body <= 65% or range <= 1.3x ATR)
  {
    const candles = createBaseCandles(35, 2710);
    for (let i = 0; i <= 21; i++) {
      candles[i].open = 2710.0;
      candles[i].close = 2710.5;
      candles[i].high = 2712.0;
      candles[i].low = 2709.0;
    }
    candles[5].low = 2708.0; // London Low
    candles[10].high = 2725.0; // London High
    candles[15].high = 2713.0; // Swing High

    // Sweep candle
    candles[22].open = 2709.0;
    candles[22].high = 2710.0;
    candles[22].low = 2706.5; // Swept SSL!
    candles[22].close = 2708.5;

    // Candle 23 consolidation
    candles[23].open = 2708.5;
    candles[23].high = 2711.0;
    candles[23].low = 2708.0;
    candles[23].close = 2710.0;

    // Weak displacement breakout: candle breaks 2713.0, but with tiny body and long wicks (body < 65%)
    candles[24].open = 2712.0;
    candles[24].high = 2715.0;
    candles[24].low = 2711.0;
    candles[24].close = 2713.8; // Body = 1.8, Range = 4.0 (45% body < 65%)

    const res = evaluateGoldSmcStrategy(candles, DEFAULT_NY_SILVER_BULLET_CONFIG, { bypassTimeWindow: true });
    assert(
      res.status === 'NO_TRADE' && res.guards.displacementGuardPassed === false && res.rejectionReason?.includes('WEAK_DISPLACEMENT_GUARD') === true,
      "Test 5: Weak Displacement Guard rejects breakout candle with body <= 65%"
    );
  }

  // TEST 6: News / Macro Whip-saw Guard (> 3.5x ATR(14) sweep anomaly)
  {
    const candles = createBaseCandles(35, 2710);
    for (let i = 0; i <= 21; i++) {
      candles[i].open = 2710.0;
      candles[i].close = 2710.5;
      candles[i].high = 2712.0;
      candles[i].low = 2709.0;
    }
    candles[5].low = 2708.0; // London Low
    candles[10].high = 2725.0; // London High

    // Create huge 30.0$ sweep spike (e.g. 13:30 NFP / CPI anomaly > 3.5x ATR of ~1.2)
    candles[22].open = 2709.0;
    candles[22].high = 2715.0;
    candles[22].low = 2685.0; // 30.0$ spike range!
    candles[22].close = 2708.5;

    const res = evaluateGoldSmcStrategy(candles, DEFAULT_NY_SILVER_BULLET_CONFIG, { bypassTimeWindow: true });
    assert(
      res.status === 'NO_TRADE' && res.guards.newsWhipsawGuardPassed === false && res.rejectionReason?.includes('NEWS_WHIPSAW_GUARD') === true,
      "Test 6: News / Macro Whip-saw Guard rejects sweep candle exceeding 3.5x ATR(14)"
    );
  }

  // TEST 7: Deterministic Consistency Test
  {
    const candles = createBaseCandles(30, 2715);
    const res1 = evaluateGoldSmcStrategy(candles, DEFAULT_NY_SILVER_BULLET_CONFIG, { bypassTimeWindow: true });
    const res2 = evaluateGoldSmcStrategy(candles, DEFAULT_NY_SILVER_BULLET_CONFIG, { bypassTimeWindow: true });
    assert(
      res1.status === res2.status &&
      res1.confluenceScore === res2.confluenceScore &&
      res1.action === res2.action &&
      res1.strategyVersion === "v2.0.0-ny-silver-bullet",
      "Test 7: Strategy execution is 100% deterministic with zero randomness"
    );
  }

  console.log("==================================================");
  console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
  console.log("==================================================");

  if (failed > 0) {
    process.exit(1);
  }
}

runTests();
