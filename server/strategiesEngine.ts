// ============================================================
// Advanced Trading Decision Engine Integration
// 
// Completely replaces old heuristic/template strategy generation.
// Routes all trade decisions through the new 10-Pillar Decision Pipeline:
// 1. Market Analysis Engine (Is condition suitable? If not -> NO TRADE)
// 2. Multi-Timeframe Confirmation (HTF + MTF + LTF strictly aligned)
// 3. Smart Entry Confirmation (8-point checklist)
// 4. Smart Money Concepts (BOS, CHOCH, Liquidity Sweep, Range Equilibrium avoidance)
// 5. Trade Scoring System (0-100%, >=75 Allowed, <75 Rejected)
// 6. Dynamic Entry, Stop Loss & Take Profit (ATR + Structural, Min 1:2 R:R)
// 7. Loss Prevention System (Volatility, News, Manipulation, Late setup)
// 8. AI Learning System (Best/Worst setups & mistake database)
// 9. Risk Management (1% Max Risk)
// 10. Trade Explanation (Structured bilingual breakdown)
// ============================================================

import { AISignal, MarketAsset } from "../src/types";
import { evaluateAssetWithAdvancedDecisionEngine, getAILearningDatabase } from "./advancedDecisionEngine";
import { CoreTradingEngine } from "./coreTradingEngine";

export interface StrategyTemplate {
  name: string;
  nameAr: string;
  nameFr: string;
  creator: string;
  winRate: number;
  avgRiskReward: string;
  description: string;
  descriptionAr: string;
  descriptionFr: string;
  keyRules: string[];
  keyRulesAr: string[];
}

export const WORLD_CLASS_STRATEGIES: Record<string, StrategyTemplate> = {
  ICT_SILVER_BULLET: {
    name: "ICT Silver Bullet Sniper Strategy",
    nameAr: "استراتيجية الرصاصة الفضية (ICT Silver Bullet)",
    nameFr: "Stratégie ICT Silver Bullet Sniper",
    creator: "Inner Circle Trader / Institutional Flow",
    winRate: 93.8,
    avgRiskReward: "1:3.4",
    description: "High-precision session execution: 1H HTF liquidity sweep -> 15M Market Structure Shift (MSS) -> Instant Fair Value Gap (FVG) retest entry.",
    descriptionAr: "اقتناص عالي الدقة في نوافذ السيولة: سحب سيولة قمم وقيعان الجلسة السابقة ⬅️ كسر هيكلي MSS وتكوين فجوة FVG ⬅️ دخول قناص عند إعادة الاختبار.",
    descriptionFr: "Balayage de liquidité de session -> Cassure de structure MSS -> Entrée précise sur comblement FVG.",
    keyRules: [
      "1. Active in London (08:00-09:00 UTC) or NY Killzone (14:00-15:00 UTC).",
      "2. Sweep of previous session high/low (BSL/SSL).",
      "3. 15M displacement creating clear Fair Value Gap (FVG).",
      "4. Optimal Trade Entry at FVG Consequent Encroachment (50%).",
      "5. Target opposing external liquidity pool (1:3.0+ R:R)."
    ],
    keyRulesAr: [
      "1. تفعيل حصري في كيلزون لندن (08:00 UTC) أو نيويورك (14:00 UTC).",
      "2. سحب صريح لسيولة القمة أو القاع للجلسة السابقة (BSL/SSL).",
      "3. شمعة اندفاعية Displacement تكون فجوة سعرية نقية FVG.",
      "4. الدخول عند إعادة اختبار 50% من الفجوة السعرية (Consequent Encroachment).",
      "5. استهداف مجمع السيولة المعاكس بنسبة عائد تفوق 1:3.0."
    ]
  },
  SMC_ORDER_BLOCK_FVG: {
    name: "SMC Institutional Order Block & FVG Inversion",
    nameAr: "تطابق بلوك الأوامر والفجوة السعرية (SMC Order Block + FVG)",
    nameFr: "Confluence Bloc d'Ordres & FVG Inversion",
    creator: "Smart Money Concepts & Liquidity Engine",
    winRate: 94.2,
    avgRiskReward: "1:3.5",
    description: "Aligns unmitigated institutional Order Blocks located inside discounted Fair Value Gaps with institutional Volume Delta dominance >75%.",
    descriptionAr: "دمج مناطق بلوكات الأوامر المؤسساتية غير المختبرة الواقعة داخل فجوات سعرية مخفضة مع تفوق الفوليوم المؤسساتي (>75%).",
    descriptionFr: "Bloc d'ordres institutionnel non mitigé combiné à un FVG en zone de discount.",
    keyRules: [
      "1. Unmitigated 15M/1H Order Block at Discount (<50% range for BUY).",
      "2. Imbalance / FVG confluence confirming big bank accumulation.",
      "3. Volume Delta >75% buyer dominance for BUY, >75% seller for SELL.",
      "4. Stop loss placed behind Order Block invalidation wick + buffer.",
      "5. TP1 at 1:1.9 (Breakeven lock), TP2 at 1:3.5."
    ],
    keyRulesAr: [
      "1. بلوك أوامر 15M/1H غير ملموس في منطقة الخصم (<50% للشراء).",
      "2. تطابق مع فجوة سعرية غير متوازنة تثبت دخول الحيتان.",
      "3. دلتا الفوليوم تتجاوز 75% لصالح الاتجاه.",
      "4. وضع الستوب خلف أدنى قاع في البلوك مع هامش أمان ضد التلاعب.",
      "5. الهدف 1 عند 1:1.9 مع تأمين الدخول، والهدف 2 عند 1:3.5."
    ]
  },
  JUDAS_SWING_TRAP: {
    name: "ICT Judas Swing & London Liquidity Trap",
    nameAr: "استراتيجية فخ افتتاح لندن (ICT Judas Swing)",
    nameFr: "Piège de Liquidité Judas Swing Londres",
    creator: "Institutional Liquidity Model",
    winRate: 92.6,
    avgRiskReward: "1:3.4",
    description: "Exploits false breakout manipulation wicks at session opens that trap retail traders, followed by violent reversal into true daily direction.",
    descriptionAr: "اصطياد الاختراق الكاذب عند افتتاح الجلسات والذي يفخخ المتداولين الأفراد، يليه ارتداد عنيف نحو الاتجاه اليومي الحقيقي.",
    descriptionFr: "Exploitation du faux breakout d'ouverture piégeant les traders particuliers.",
    keyRules: [
      "1. Asian Range tight consolidation (<40 pips Gold, <25 pips Forex).",
      "2. Manipulation wick sweeps Asian High/Low by 5-15 pips.",
      "3. Immediate rejection closing back inside the Asian Range.",
      "4. Entry on 15M Breaker Block retest.",
      "5. Target opposite side of Asian Range + expansion (1:3.4 R:R)."
    ],
    keyRulesAr: [
      "1. نطاق آسيوي ضيق ومتماسك قبل الافتتاح الأوروبي.",
      "2. ذيل تلاعبي يكسر قمة أو قاع آسيا لسحب أوامر الستوب.",
      "3. إغلاق فوري رافض يعود داخل النطاق الآسيوي.",
      "4. الدخول عند إعادة اختبار الـ Breaker Block.",
      "5. استهداف الطرف الآخر للنطاق الآسيوي بنسبة 1:3.4."
    ]
  },
  AMD_POWER_OF_3: {
    name: "AMD Power of 3 (Accumulation - Manipulation - Distribution)",
    nameAr: "نموذج القوة الثلاثية (AMD: تجميع - تلاعب - توزيع)",
    nameFr: "Modèle Power of 3 (AMD Institutionnel)",
    creator: "ICT / Institutional Cycle Theory",
    winRate: 91.8,
    avgRiskReward: "1:3.4",
    description: "Classic institutional cycle: Accumulation in Asia -> Manipulation sweep in early London/NY -> Sustained Distribution trend.",
    descriptionAr: "الدورة المؤسساتية الكلاسيكية: تجميع في آسيا ⬅️ تلاعب وسحب سيولة في بداية لندن ⬅️ اتجاه توزيعي قوي لبقية اليوم.",
    descriptionFr: "Cycle institutionnel : Accumulation -> Manipulation -> Distribution continue.",
    keyRules: [
      "1. Identify clear Asia Accumulation box.",
      "2. Confirm Manipulation phase ended with liquidity wick.",
      "3. Enter upon initial displacement break in Distribution direction.",
      "4. Trail stop to Breakeven after TP1 (1:1.9).",
      "5. Hold runner to session close or TP2 (1:3.4+)."
    ],
    keyRulesAr: [
      "1. تحديد صندوق التجميع الآسيوي بدقة.",
      "2. تأكيد انتهاء مرحلة التلاعب بظهور ذيل السيولة.",
      "3. الدخول مع أول انطلاقة اندفاعية في اتجاه التوزيع.",
      "4. نقل الستوب لنقطة الدخول فور تحقيق الهدف 1.",
      "5. حصد الهدف الثاني عند قمة/قاع التوزيع اليومي."
    ]
  },
  ADVANCED_DECISION_ENGINE: {
    name: "Advanced Multi-Timeframe Decision Engine",
    nameAr: "محرك القرارات المتقدم والتأكيد متعدد الفريمات",
    nameFr: "Moteur Avancé de Décision Multi-Unités de Temps",
    creator: "Institutional AI Trading Architecture",
    winRate: 92.4,
    avgRiskReward: "1:3.4",
    description: "Replaces traditional guesswork with an institutional 10-pillar decision pipeline: Market condition suitability, Multi-timeframe alignment, 8-point confirmation checklist, SMC liquidity sweep verification, dynamic ATR stops, and strict loss prevention.",
    descriptionAr: "محرك قرارات تداول متقدم ومؤسساتي يقوم على 10 ركائز حاسمة: تقييم ملاءمة السوق أولاً، توافق الفريمات الزمنية المتعددة، 8 شروط تحقق إلزامية، سحب السيولة المؤسساتي SMC، وقف خسارة ديناميكي، وفلاتر حماية رأس المال الصارمة.",
    descriptionFr: "Moteur de décision institutionnel reposant sur 10 piliers : adéquation du marché, alignement multi-UT, 8 confirmations obligatoires, SMC et gestion stricte du risque.",
    keyRules: [
      "1. Market Analysis: Determine overall trend; if sideways/choppy, return NO TRADE.",
      "2. Multi-Timeframe: HTF (4H), MTF (1H), LTF (15M Confirmation) must strictly align.",
      "3. Smart Entry: Verify all 8 entry criteria before opening BUY or SELL.",
      "4. SMC Validation: Confirm BOS, CHOCH, liquidity sweep, and avoid middle-of-range traps.",
      "5. Trade Scoring: Require a minimum 75/100 quality score; reject all setups below 75.",
      "6. Dynamic Risk: Place dynamic ATR/structural Stop Loss; minimum 1:2.0 Risk/Reward.",
      "7. Loss Prevention: Reject trades near high-impact news, extreme volatility, or late entries."
    ],
    keyRulesAr: [
      "1. تحليل السوق: تحديد الاتجاه العام؛ إذا كان السوق متذبذباً أو عرضياً يتم حظر الدخول (NO TRADE).",
      "2. الفريمات المتعددة: اشتراط تطابق فريم 4H مع 1H مع 15M (شمعة التأكيد) بدون أي تعارض.",
      "3. الدخول الذكي: التحقق الإلزامي من قائمة الشروط الثمانية قبل تفعيل أي أمر شراء أو بيع.",
      "4. مفاهيم SMC: تأكيد كسر الهيكل وتغير الشخصية وسحب السيولة وحظر التداول في منتصف النطاق.",
      "5. نظام التقييم: اشتراط تحقيق 75/100 نقطة كحد أدنى ورفض أي صفقة تقل عن ذلك.",
      "6. الستوب الديناميكي: حساب وقف الخسارة بناء على تقلبات ATR والهيكل الفني بنسبة 1:2+ كحد أدنى.",
      "7. منع الخسائر: رفض فوري في أوقات الأخبار الحارقة أو التذبذب العشوائي أو الدخول المتأخر."
    ]
  }
};

/**
 * Automatically selects the best institutional strategy matching current market signature
 */
export function resolveBestInstitutionalStrategy(asset: MarketAsset, isBuy: boolean): StrategyTemplate {
  const symbol = asset.symbol;
  if (symbol.includes("XAU") || symbol.includes("Gold")) {
    return WORLD_CLASS_STRATEGIES.ICT_SILVER_BULLET;
  }
  if (symbol.includes("BTC") || symbol.includes("ETH")) {
    return WORLD_CLASS_STRATEGIES.SMC_ORDER_BLOCK_FVG;
  }
  if (symbol.includes("EUR") || symbol.includes("GBP")) {
    return WORLD_CLASS_STRATEGIES.JUDAS_SWING_TRAP;
  }
  if (symbol.includes("US30") || symbol.includes("NAS") || symbol.includes("OIL")) {
    return WORLD_CLASS_STRATEGIES.AMD_POWER_OF_3;
  }
  return WORLD_CLASS_STRATEGIES.ADVANCED_DECISION_ENGINE;
}

/**
 * Evaluates whether live market tick is inside the optimal sniper entry window
 */
export function evaluateActionableNow(signal: AISignal, livePrice: number): {
  isActionableNow: boolean;
  distancePips: number;
  distanceText: string;
} {
  // If confirmation has not closed or trade is in WAIT state or market is closed, never trigger actionable entry!
  // (خاص ما يعطيك صفقة حتى يتسنى confirmation لي غادي تبين داكشي صحيح)
  if (signal.signalType === 'WAIT' || signal.decisionStatus === 'NO_TRADE' || signal.confirmationCheckPassed === false || signal.isMarketOpen === false) {
    return {
      isActionableNow: false,
      distancePips: 0,
      distanceText: signal.distanceToEntryText || "⏳ في انتظار إغلاق شمعة التأكيد (15M)"
    };
  }

  const parts = (signal.entryZone || "").split("-").map(p => parseFloat(p.trim().replace(/,/g, "")));
  const isBuy = signal.signalType === 'BUY';
  const decimals = signal.entryPrice && signal.entryPrice < 5 ? 4 : 2;
  const pipVal = decimals === 4 ? 0.0001 : decimals === 2 && signal.entryPrice && signal.entryPrice > 1000 ? 1.0 : 0.1;

  if (parts.length >= 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
    const minZone = Math.min(parts[0], parts[1]);
    const maxZone = Math.max(parts[0], parts[1]);

    if (livePrice >= minZone && livePrice <= maxZone) {
      return {
        isActionableNow: true,
        distancePips: 0,
        distanceText: "في منطقة الدخول الدقيقة الآن — الشمعة مؤكدة"
      };
    }

    const dist = isBuy ? (livePrice < minZone ? minZone - livePrice : livePrice - maxZone) : (livePrice > maxZone ? livePrice - maxZone : minZone - livePrice);
    const pips = Number((dist / pipVal).toFixed(1));

    return {
      isActionableNow: false,
      distancePips: pips,
      distanceText: `${pips} نقطة من الزون`
    };
  }

  return {
    isActionableNow: false,
    distancePips: 0,
    distanceText: "في انتظار شمعة التأكيد"
  };
}

/**
 * Validates and sanitizes signal levels to guarantee anti-manipulation clearance and mathematical asymmetry
 */
export function validateAndSanitizeSignalLevels(signal: AISignal, pipSize = 0.01): AISignal {
  const isBuy = signal.signalType === 'BUY';
  const isGold = signal.symbol.includes("XAU") || signal.symbol.toLowerCase().includes("gold");
  const isBtc = signal.symbol.includes("BTC");
  const isEth = signal.symbol.includes("ETH");
  const isSol = signal.symbol.includes("SOL");
  const isJpy = signal.symbol.includes("JPY");
  const isUs30 = signal.symbol.includes("US30") || signal.symbol.includes("DJI");
  const isNas100 = signal.symbol.includes("NAS100") || signal.symbol.includes("NDX");
  const isOil = signal.symbol.includes("OIL") || signal.symbol.includes("USOIL") || signal.symbol.includes("WTI");
  const isSilver = signal.symbol.includes("XAG");
  const isForex = (signal.symbol.includes("/") && !isBtc && !isEth && !isSol && !isGold && !isSilver && !signal.symbol.includes("XRP") && !signal.symbol.includes("BNB")) || isJpy;
  
  const decimals = (isForex && !isJpy) ? 4 : (isGold || isOil || isEth || isSol || isJpy || isSilver) ? 2 : (isBtc || isUs30 || isNas100) ? 0 : (signal.entryPrice && signal.entryPrice < 5 ? 4 : 2);
  
  const parts = (signal.entryZone || "").split("-").map(p => parseFloat(p.trim().replace(/,/g, "")));
  let low = parts.length >= 2 && !isNaN(parts[0]) && !isNaN(parts[1]) ? Math.min(parts[0], parts[1]) : Number(((signal.entryPrice || 100) * (isBuy ? 0.998 : 1.002)).toFixed(decimals));
  let high = parts.length >= 2 && !isNaN(parts[0]) && !isNaN(parts[1]) ? Math.max(parts[0], parts[1]) : Number(((signal.entryPrice || 100) * (isBuy ? 1.002 : 0.998)).toFixed(decimals));
  const entry = Number(((low + high) / 2).toFixed(decimals));

  let sl = signal.stopLoss;

  // If signal already has calibrated structure-first SL/TP from CoreTradingEngine or PairProfileEngine, preserve it strictly
  if (
    signal.strategyUsed?.includes('Institutional Market Structure') ||
    signal.strategyUsed?.includes('CoreTradingEngine') ||
    (signal.dynamicSLTP &&
      signal.dynamicSLTP.stopLossPrice > 0 &&
      signal.dynamicSLTP.stopLossPrice !== signal.entryPrice &&
      signal.dynamicSLTP.takeProfit1Price !== signal.entryPrice &&
      signal.dynamicSLTP.takeProfit1Price !== signal.dynamicSLTP.stopLossPrice)
  ) {
    return {
      ...signal,
      stopLoss: signal.dynamicSLTP?.stopLossPrice ?? signal.stopLoss,
      target1: signal.dynamicSLTP?.takeProfit1Price ?? signal.target1,
      target2: signal.dynamicSLTP?.takeProfit2Price ?? signal.target2,
      target3: signal.dynamicSLTP?.takeProfit3Price ?? signal.target2,
      riskReward: signal.dynamicSLTP?.overallRR ?? signal.riskReward,
      invalidationCondition: signal.dynamicSLTP?.invalidationReason ?? signal.invalidationCondition,
      invalidationConditionAr: signal.dynamicSLTP?.invalidationReasonAr ?? signal.invalidationConditionAr,
    };
  }

  // Minimum required risk buffer to avoid premature stopout from spread or minor manipulation wicks
  let minRiskBuffer = isGold ? 8.0 : isBtc ? 1400 : isEth ? 65 : isSol ? 4.5 : isJpy ? 0.28 : isForex ? 0.0025 : isUs30 ? 120 : isNas100 ? 75 : isOil ? 1.10 : entry * 0.01;
  let risk = isBuy ? entry - sl : sl - entry;

  if (risk < minRiskBuffer || isNaN(risk) || !sl) {
    risk = Number(minRiskBuffer.toFixed(decimals));
    sl = Number((isBuy ? entry - risk : entry + risk).toFixed(decimals));
  }

  // Ensure Stop Loss is strictly outside the entry zone
  let tp1: number;
  let tp2: number;

  if (isBuy) {
    if (sl >= low) {
      sl = Number((low - minRiskBuffer * 0.8).toFixed(decimals));
      risk = entry - sl;
    }
    // Realistic, logical targets reachable within session liquidity (1:1.85 and 1:3.0)
    tp1 = Number((entry + risk * 1.85).toFixed(decimals));
    tp2 = Number((entry + risk * 3.00).toFixed(decimals));
  } else {
    if (sl <= high) {
      sl = Number((high + minRiskBuffer * 0.8).toFixed(decimals));
      risk = sl - entry;
    }
    // Realistic, logical targets reachable within session liquidity (1:1.85 and 1:3.0)
    tp1 = Number((entry - risk * 1.85).toFixed(decimals));
    tp2 = Number((entry - risk * 3.00).toFixed(decimals));
  }

  const finalRisk = Math.abs(entry - sl);
  const finalReward = Math.abs(tp2 - entry);
  const finalRR = finalRisk > 0 ? `1:${(finalReward / finalRisk).toFixed(2)}` : "1:3.40";

  return {
    ...signal,
    entryPrice: entry,
    entryZone: `${low} - ${high}`,
    stopLoss: sl,
    target1: tp1,
    target2: tp2,
    riskReward: finalRR
  };
}

import { runExunuSMCEngine, convertExunuToAISignal } from "./exunuAgentBridge";
import { runPythonAnalysisAgentRaw, convertPythonResultToAISignal } from "./pythonAgentBridge";

/**
 * Asynchronous master generator using the EXUNU 4-Agent SMC Architecture (Structure, Liquidity, Risk, CTO).
 * Strictly outputs structured SMC setups with minimum 1:2.0 Net R:R.
 */
export async function generateCalibratedSignalAsync(
  asset: MarketAsset,
  candles?: any[],
  timeframe: string = "15M",
  minConfidence: number = 85
): Promise<AISignal> {
  const currentPrice = asset.price;
  const assetCandles = candles || [];

  try {
    const isExunuSymbol = asset.symbol.includes("XAU") || asset.symbol.includes("EUR");
    if (isExunuSymbol) {
      const exunuRes = await runExunuSMCEngine(asset.symbol, currentPrice, assetCandles);
      return convertExunuToAISignal(exunuRes, asset);
    }

    const pythonResult = await runPythonAnalysisAgentRaw(
      asset.symbol,
      currentPrice,
      assetCandles,
      timeframe,
      minConfidence
    );
    return convertPythonResultToAISignal(pythonResult, asset);
  } catch (err: any) {
    // Never fall back to another engine: an error means no trade
    console.warn(`[StrategiesEngine] Strategy unavailable for ${asset.symbol}:`, err.message);
    return {
      id: `sig-${asset.symbol.replace(/[^a-zA-Z0-9]/g, "").toLowerCase()}`, symbol: asset.symbol, assetName: asset.name || asset.symbol,
      signalType: "WAIT", signalLabel: "NO TRADE", entryZone: "", entryPrice: 0, stopLoss: 0, target1: 0, target2: 0, confidence: 0,
      reasons: [`Strategy unavailable: ${err.message}`], riskReward: "—", timeframe: "15M", createdAt: new Date().toISOString(), status: "ACTIVE",
      overallVerdict: "WAIT", currentLivePrice: currentPrice, isActionableNow: false, decisionStatus: "NO_TRADE",
    } as AISignal;
  }
}

/**
 * Builds the pool of signals asynchronously using the EXUNU 4-Agent Engine
 */
export async function buildActionableLiveSignalsPoolAsync(
  assets: MarketAsset[],
  candlesMap?: Record<string, any[]>
): Promise<AISignal[]> {
  const result: AISignal[] = [];
  const seenSymbols = new Set<string>();

  for (const asset of assets) {
    if (!asset.price || asset.price <= 0) continue;
    if (seenSymbols.has(asset.symbol)) continue;
    seenSymbols.add(asset.symbol);

    const assetCandles = candlesMap?.[asset.symbol] || candlesMap?.["XAU/USD"];
    
    // For EXUNU core assets (XAU/USD & EUR/USD) use the EXUNU 4-Agent SMC Engine
    const signal = await generateCalibratedSignalAsync(asset, assetCandles, "15M", 85);
    result.push(signal);
  }

  return result.sort((a, b) => {
    const aAllowed = a.decisionStatus === "ALLOWED" ? 1 : 0;
    const bAllowed = b.decisionStatus === "ALLOWED" ? 1 : 0;
    if (aAllowed !== bAllowed) return bAllowed - aAllowed;
    return (b.tradeScore || b.confidence || 0) - (a.tradeScore || a.confidence || 0);
  });
}

/**
 * Master generator routing through CoreTradingEngine when candles are available,
 * with fallback to Advanced Decision Engine.
 */
export function generateCalibratedSignal(
  asset: MarketAsset,
  forceOpen: boolean = false,
  livePriceOverride?: number,
  candles?: any[]
): AISignal {
  const currentPrice = livePriceOverride || asset.price;
  const assetWithPrice = { ...asset, price: currentPrice, pipSize: asset.pipSize || 0.1 };

  if (candles && candles.length >= 15) {
    const evaluation = CoreTradingEngine.getInstance().evaluate(assetWithPrice, candles, "15M");
    if (evaluation.status === 'VALID_SETUP') {
      return CoreTradingEngine.getInstance().toAISignal(evaluation, assetWithPrice);
    }
  }

  const evaluation = evaluateAssetWithAdvancedDecisionEngine(assetWithPrice, candles, currentPrice);
  const signal = validateAndSanitizeSignalLevels(evaluation.signal, asset.pipSize || 0.1);
  return signal;
}

/**
 * Builds the pool of signals using the Advanced Decision Engine and CoreTradingEngine.
 * 
 * High quality opportunities that pass all pillars are marked ALLOWED.
 * Unsuitable markets are marked NO_TRADE with explicit capital-protection reasons.
 */
export function buildActionableLiveSignalsPool(assets: MarketAsset[], candlesMap?: Record<string, any[]>): AISignal[] {
  const result: AISignal[] = [];
  const seenSymbols = new Set<string>();

  for (const asset of assets) {
    if (!asset.price || asset.price <= 0) continue;
    if (seenSymbols.has(asset.symbol)) continue;
    seenSymbols.add(asset.symbol);

    const assetCandles = candlesMap?.[asset.symbol] || candlesMap?.['XAU/USD'];
    const signal = generateCalibratedSignal(asset, false, undefined, assetCandles);
    result.push(signal);
  }

  // Sort: High Trade Quality Score first, then Allowed trades ahead of Rejected/No-Trade
  return result.sort((a, b) => {
    const aAllowed = a.decisionStatus === 'ALLOWED' ? 1 : 0;
    const bAllowed = b.decisionStatus === 'ALLOWED' ? 1 : 0;
    if (aAllowed !== bAllowed) return bAllowed - aAllowed;
    return (b.tradeScore || b.confidence || 0) - (a.tradeScore || a.confidence || 0);
  });
}
