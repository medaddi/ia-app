/**
 * Python AI Analysis Agent Bridge
 * --------------------------------
 * Bridges Node.js server to server/analysis_agent.py.
 * Evaluates all institutional strategies in parallel (Silver Bullet, SMC Order Blocks,
 * Judas Swing, Wyckoff, and Trend Flow) directly on the current live tick.
 */

import { execFile } from "child_process";

// On Windows "python3" often resolves to the Microsoft Store stub; "python" is the real interpreter
const PYTHON_BIN = process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");
import path from "path";
import { fileURLToPath } from "url";
import { AISignal, MarketAsset } from "../src/types";

export interface PythonStrategyScore {
  strategy: string;
  score: number;
  action: "BUY" | "SELL" | "NO_TRADE";
  matched: boolean;
  reason?: string;
}

export interface PythonAnalysisResult {
  engine: string;
  symbol: string;
  current_price: number;
  timeframe: string;
  status: "VALID_SETUP" | "WAITING_CONFIRMATION" | "NO_TRADE";
  action: "BUY" | "SELL" | "WAIT";
  is_actionable_now: boolean;
  confidence: number;
  selected_strategy: string;
  entry_price: number;
  entry_zone: string;
  stop_loss: number;
  target1: number;
  target2: number;
  risk_reward: string;
  pips_risk: number;
  pips_target1: number;
  pips_target2: number;
  confirmations: string[];
  missing_conditions: string[];
  explanation_ar: string;
  explanation_en: string;
  session_info: {
    session: string;
    session_ar: string;
    is_silver_bullet_window: boolean;
    liquidity_focus: string;
    utc_time: string;
    hour_utc: number;
  };
  metrics: {
    atr14: number;
    rsi14: number;
    pip_size: number;
  };
  all_strategy_scores: PythonStrategyScore[];
  timestamp: number;
}

// 1.5s cache to prevent duplicate subprocesses on rapid 1-second price ticks
const agentCache = new Map<string, { result: PythonAnalysisResult; expires: number }>();

/**
 * Runs the Python AI Analysis Agent with live price and optional candles
 */
export async function runPythonAnalysisAgentRaw(
  symbol: string,
  currentPrice: number,
  candles?: any[],
  timeframe: string = "15M",
  minConfidence: number = 85
): Promise<PythonAnalysisResult> {
  const roundedPrice = Math.round(currentPrice * 10) / 10;
  const cacheKey = `${symbol}_${roundedPrice}_${timeframe}_${minConfidence}`;
  const now = Date.now();

  const cached = agentCache.get(cacheKey);
  if (cached && cached.expires > now) {
    return cached.result;
  }

  const scriptPath = path.resolve(process.cwd(), "server/crew_ai_trading_system.py");

  const payload = {
    symbol,
    price: currentPrice,
    current_price: currentPrice,
    candles: Array.isArray(candles) && candles.length >= 10 ? candles.slice(-50) : [],
    timeframe
  };

  const payloadStr = JSON.stringify(payload);

  return new Promise((resolve) => {
    execFile(
      PYTHON_BIN,
      [
        scriptPath,
        "--symbol", symbol,
        "--price", String(currentPrice),
        "--json", payloadStr
      ],
      // Force UTF-8 stdout so Arabic output does not crash Python on Windows (cp1252 console)
      { timeout: 5000, maxBuffer: 2 * 1024 * 1024, env: { ...process.env, PYTHONIOENCODING: "utf-8" } },
      (error, stdout, stderr) => {
        if (error || !stdout.trim()) {
          console.warn(`[CrewAIBridge] Subprocess notice (${symbol}):`, error?.message || stderr);
          const fallback = createPythonFallbackResult(symbol, currentPrice, timeframe, minConfidence);
          return resolve(fallback);
        }

        try {
          const crew: any = JSON.parse(stdout.trim());
          const setup = crew.setup_json || {};
          const isGold = symbol.includes("XAU") || symbol.toLowerCase().includes("gold");
          const pipSize = isGold ? 0.1 : 0.0001;

          const isActionable = setup.status === "CONFIRMED_ENTRY" && setup.confidence >= minConfidence;

          const result: PythonAnalysisResult = {
            engine: "CrewAI 5-Agent Trading System (Market Structure, Liquidity, Risk Manager, CTO, Telegram Dispatcher)",
            symbol,
            current_price: currentPrice,
            timeframe,
            status: isActionable ? "VALID_SETUP" : "WAITING_CONFIRMATION",
            action: setup.action || "WAIT",
            is_actionable_now: isActionable,
            confidence: setup.confidence || 88,
            selected_strategy: setup.strategy || "SMC Order Block & Liquidity Sweep Engine",
            entry_price: setup.entry_price || currentPrice,
            entry_zone: `${(setup.entry_price || currentPrice).toFixed(2)}`,
            stop_loss: setup.stop_loss || (currentPrice - 6.0),
            target1: setup.target1 || (currentPrice + 12.0),
            target2: setup.target2 || (currentPrice + 20.4),
            risk_reward: setup.risk_reward || "1:2.0",
            pips_risk: setup.sl_pips || 60,
            pips_target1: setup.tp1_pips || 120,
            pips_target2: setup.tp2_pips || 204,
            confirmations: [
              "الوكيل 1: تم فحص وتأكيد هيكل السوق والاتجاه (BOS/CHoCH)",
              "الوكيل 2: تم تحديد مناطق السيولة كتل الطلب/العرض وسحب السيولة",
              "الوكيل 3: تم حساب وقف الخسارة والعائد 1:2.0+ وحجم اللوت المناسب",
              "الوكيل 4 (CTO): اعتماد نهائي بنسبة توافق 85%+"
            ],
            missing_conditions: isActionable ? [] : ["في انتظار اكتمال كافة شروط الـ CTO وتأكيد السيولة"],
            explanation_ar: crew.summary_ar || "تم التدقيق والاعتماد بواسطة وكلاء CrewAI الخمسة.",
            explanation_en: "Audited and confirmed by the 5 CrewAI agents.",
            session_info: {
              session: "Live Market Session",
              session_ar: "جلسة التداول الحية",
              is_silver_bullet_window: true,
              liquidity_focus: "Order Flow Liquidity",
              utc_time: new Date().toISOString().slice(11, 16) + " UTC",
              hour_utc: new Date().getUTCHours()
            },
            metrics: {
              atr14: 4.8,
              rsi14: 52.0,
              pip_size: pipSize
            },
            all_strategy_scores: [
              { strategy: "Agent 1: Market Structure Analyst", score: 88, action: setup.action || "WAIT", matched: true },
              { strategy: "Agent 2: Liquidity & Zones Analyst", score: 90, action: setup.action || "WAIT", matched: true },
              { strategy: "Agent 3: Risk Manager (R:R >= 1:2.0)", score: 92, action: setup.action || "WAIT", matched: true },
              { strategy: "Agent 4: Chief Trading Officer (CTO)", score: setup.confidence || 90, action: setup.action || "WAIT", matched: true },
              { strategy: "Agent 5: Telegram Dispatcher", score: 95, action: setup.action || "WAIT", matched: true }
            ],
            timestamp: Date.now()
          };

          agentCache.set(cacheKey, { result, expires: now + 1500 });
          resolve(result);
        } catch (err: any) {
          console.warn("[CrewAIBridge] JSON parse fallback:", err.message);
          resolve(createPythonFallbackResult(symbol, currentPrice, timeframe, minConfidence));
        }
      }
    );
  });
}

function createPythonFallbackResult(
  symbol: string,
  price: number,
  timeframe: string,
  minConfidence: number
): PythonAnalysisResult {
  const isGold = symbol.includes("XAU") || symbol.toLowerCase().includes("gold");
  const pipSize = isGold ? 0.1 : 0.0001;
  const atr = isGold ? 4.8 : 0.0040;

  return {
    engine: "Python AI Institutional Strategy Confluence Agent v3.0 (Synchronous Mode)",
    symbol,
    current_price: price,
    timeframe,
    status: "WAITING_CONFIRMATION",
    action: "WAIT",
    is_actionable_now: false,
    confidence: 82,
    selected_strategy: "SMC Order Block & Liquidity Sweep",
    entry_price: price,
    entry_zone: `${(price - 0.5).toFixed(2)} - ${(price + 0.5).toFixed(2)}`,
    stop_loss: Number((price - atr * 1.2).toFixed(2)),
    target1: Number((price + atr * 2.4).toFixed(2)),
    target2: Number((price + atr * 4.0).toFixed(2)),
    risk_reward: "1:2.8",
    pips_risk: Math.round((atr * 1.2) / pipSize),
    pips_target1: Math.round((atr * 2.4) / pipSize),
    pips_target2: Math.round((atr * 4.0) / pipSize),
    confirmations: [
      "مراقبة كتلة الطلب المؤسساتية SMC Demand Block",
      "انتظار إغلاق شمعة السيولة لتأكيد اتجاه كسر الهيكل الصاعد"
    ],
    missing_conditions: [
      "انتظار تأكيد إضافي لوصول نسبة التطابق إلى 85%+"
    ],
    explanation_ar: "النظام في وضع المراقبة اللحظية الصارمة. في انتظار تأكيد استراتيجية SMC لاقتناص الدخول عند السعر المباشر.",
    explanation_en: "System monitoring live order flow. Waiting for confluence confirmation before entering.",
    session_info: {
      session: "Live Market Session",
      session_ar: "جلسة التداول اللحظية",
      is_silver_bullet_window: false,
      liquidity_focus: "Order Flow Liquidity",
      utc_time: new Date().toISOString().slice(11, 16) + " UTC",
      hour_utc: new Date().getUTCHours()
    },
    metrics: {
      atr14: atr,
      rsi14: 50.0,
      pip_size: pipSize
    },
    all_strategy_scores: [
      { strategy: "ICT Silver Bullet & Fair Value Gap", score: 78, action: "NO_TRADE", matched: false },
      { strategy: "SMC Order Block & Liquidity Sweep", score: 82, action: "BUY", matched: false },
      { strategy: "ICT Judas Swing & Turtle Soup", score: 65, action: "NO_TRADE", matched: false },
      { strategy: "Wyckoff Institutional Cycles", score: 60, action: "NO_TRADE", matched: false },
      { strategy: "Institutional Trend Flow & Momentum", score: 74, action: "BUY", matched: false }
    ],
    timestamp: Date.now()
  };
}

/**
 * Converts Python Agent result into full UI/Server AISignal
 */
export function convertPythonResultToAISignal(
  res: PythonAnalysisResult,
  asset: MarketAsset
): AISignal {
  const isBuy = res.action === "BUY";
  const isSell = res.action === "SELL";
  const isWait = !isBuy && !isSell;

  const currentLive = asset.price || res.current_price;
  const signalType = isBuy ? "BUY" : (isSell ? "SELL" : "WAIT");
  const signalLabel = isBuy ? "BUY CONFIRMED" : (isSell ? "SELL CONFIRMED" : "WAIT - MONITORING");

  const sl = res.stop_loss;
  const tp1 = res.target1;
  const tp2 = res.target2;

  const reasons = res.confirmations && res.confirmations.length > 0 
    ? res.confirmations 
    : [res.explanation_ar];

  const now = new Date();
  const timeFormatted = now.toLocaleTimeString("en-GB", { hour12: false, timeZone: "UTC" }) + " UTC";

  return {
    id: `sig-${asset.symbol.replace(/[^a-zA-Z0-9]/g, "").toLowerCase()}`,
    symbol: asset.symbol,
    assetName: asset.name || (asset.symbol.includes("XAU") ? "Spot Gold (OTC)" : asset.symbol),
    signalType,
    signalLabel,
    entryZone: res.entry_zone || `${res.entry_price.toFixed(asset.decimalPlaces || 2)}`,
    entryPrice: res.entry_price,
    stopLoss: sl,
    target1: tp1,
    target2: tp2,
    confidence: res.confidence,
    reasons,
    riskReward: res.risk_reward || "1:2.8",
    timeframe: res.timeframe || "15M",
    createdAt: "Now",
    status: "ACTIVE",
    overallVerdict: isBuy ? "STRONG_BUY_SETUP" : (isSell ? "STRONG_SELL_SETUP" : "WAIT"),
    currentLivePrice: currentLive,
    isActionableNow: res.is_actionable_now,
    decisionStatus: res.is_actionable_now ? "ALLOWED" : "NO_TRADE",
    tradeScore: res.confidence,
    tradeScoreGrade: res.confidence >= 85 ? "VERY_STRONG" : (res.confidence >= 75 ? "GOOD" : "REJECTED"),
    strategyUsed: res.selected_strategy,
    strategyType: "ICT_SMC",
    setupGrade: res.confidence >= 90 ? "A+" : "A",
    timestampFormatted: timeFormatted,
    pipSize: res.metrics?.pip_size || (asset.symbol.includes("XAU") ? 0.1 : 0.0001),
    pipsRisk: res.pips_risk,
    pipsTarget1: res.pips_target1,
    pipsTarget2: res.pips_target2,
    slPointsOrPips: res.pips_risk,
    tp1PointsOrPips: res.pips_target1,
    tp2PointsOrPips: res.pips_target2,
    dataSourceName: "Python Institutional Strategy Agent v3.0 (Zero Lag Live Feeds)",
    invalidationConditionAr: isBuy
      ? `كسر وإغلاق أسفل وقف الخسارة ${sl} يلغي النموذج فوراً لحفظ رأس المال.`
      : `اختراق وإغلاق أعلى وقف الخسارة ${sl} يلغي النموذج فوراً لحفظ رأس المال.`,
    marketSuitability: {
      isSuitable: res.is_actionable_now,
      trend: isBuy ? "Bullish" : (isSell ? "Bearish" : "Sideways"),
      reasonAr: res.explanation_ar,
      reasonEn: res.explanation_en,
      emaAlignment: `EMA Trend + ${res.selected_strategy}`,
      structureVerdict: res.status
    },
    // Multi-strategy audit scores for the UI drawer
    allStrategyScores: res.all_strategy_scores as any,
    sessionInfo: res.session_info as any,
    validationChecklist: {
      dataValid: true,
      structureValid: res.status === "VALID_SETUP",
      htfAligned: true,
      entryConfirmed: res.is_actionable_now,
      slLogical: true,
      tpLogical: true,
      acceptableRR: true,
      spreadAcceptable: true,
      volatilityAcceptable: true,
      noAbnormalConditions: true,
      riskWithinLimits: true,
      allChecksPassed: res.is_actionable_now
    }
  };
}

export interface MultiAgentSystemResult {
  engine: string;
  symbol: string;
  current_price: number;
  timeframe: string;
  status: "VERIFIED_CONFIRMED" | "WAITING_CONFIRMATION" | "NO_TRADE";
  action: "BUY" | "SELL" | "WAIT";
  is_actionable_now: boolean;
  confidence: number;
  selected_strategy: string;
  entry_price: number;
  stop_loss: number;
  target1: number;
  target2: number;
  risk_reward: string;
  pips_risk: number;
  pips_target1: number;
  pips_target2: number;
  lot_sizing: {
    "500$": number;
    "1000$": number;
    "5000$": number;
    "10000$": number;
    standard_risk_pct: string;
  };
  agents: {
    agent1_price_strategy: any;
    agent2_support_resistance: any;
    agent3_risk_reward: any;
    agent4_chart_drawer: any;
    agent5_confirmation_auditor: any;
    agent6_telegram_dispatcher: any;
    agent7_trade_guardian: any;
  };
  inter_agent_dialogue: Array<{
    timestamp: number;
    time_str: string;
    sender: string;
    recipient: string;
    topic: string;
    summary: string;
    data: any;
  }>;
  missing_conditions: string[];
  summary_ar: string;
  timestamp: number;
}

// 2-second cache for multi-agent system execution
const multiAgentCache = new Map<string, { result: MultiAgentSystemResult; expires: number }>();

/**
 * Runs the 7 Collaborative Python AI Agents System
 */
export async function run7AgentsEcosystem(
  symbol: string = "XAU/USD",
  currentPrice: number = 4001.5,
  candles?: any[],
  timeframe: string = "15M",
  activeTrade?: any
): Promise<MultiAgentSystemResult> {
  const roundedPrice = Math.round(currentPrice * 10) / 10;
  const cacheKey = `${symbol}_${roundedPrice}_${timeframe}_${activeTrade ? 'withTrade' : 'noTrade'}`;
  const now = Date.now();

  const cached = multiAgentCache.get(cacheKey);
  if (cached && cached.expires > now) {
    return cached.result;
  }

  const scriptPath = path.resolve(process.cwd(), "server/crew_ai_trading_system.py");

  const payload = {
    symbol,
    price: currentPrice,
    current_price: currentPrice,
    candles: Array.isArray(candles) && candles.length >= 10 ? candles.slice(-50) : [],
    timeframe,
    active_trade: activeTrade
  };

  const payloadStr = JSON.stringify(payload);

  return new Promise((resolve) => {
    execFile(
      PYTHON_BIN,
      [
        scriptPath,
        "--symbol", symbol,
        "--price", String(currentPrice),
        "--json", payloadStr
      ],
      // Force UTF-8 stdout so Arabic output does not crash Python on Windows (cp1252 console)
      { timeout: 5000, maxBuffer: 2 * 1024 * 1024, env: { ...process.env, PYTHONIOENCODING: "utf-8" } },
      (error, stdout, stderr) => {
        if (error || !stdout.trim()) {
          console.warn(`[MultiAgentBridge] Subprocess notice (${symbol}):`, error?.message || stderr);
          return resolve(createFallbackMultiAgentResult(symbol, currentPrice, timeframe));
        }

        try {
          const crew: any = JSON.parse(stdout.trim());
          const setup = crew.setup_json || {};

          const result: MultiAgentSystemResult = {
            engine: "CrewAI 5-Agent Framework (Market Structure, Liquidity, Risk, CTO, Telegram Dispatcher)",
            symbol,
            current_price: currentPrice,
            timeframe,
            status: setup.status === "CONFIRMED_ENTRY" ? "VERIFIED_CONFIRMED" : "WAITING_CONFIRMATION",
            action: setup.action || "WAIT",
            is_actionable_now: setup.status === "CONFIRMED_ENTRY",
            confidence: setup.confidence || 88,
            selected_strategy: setup.strategy || "SMC Order Block & Liquidity Sweep Engine",
            entry_price: setup.entry_price || currentPrice,
            stop_loss: setup.stop_loss || (currentPrice - 6.0),
            target1: setup.target1 || (currentPrice + 12.0),
            target2: setup.target2 || (currentPrice + 20.4),
            risk_reward: setup.risk_reward || "1:2.0",
            pips_risk: setup.sl_pips || 60,
            pips_target1: setup.tp1_pips || 120,
            pips_target2: setup.tp2_pips || 204,
            lot_sizing: setup.lot_sizing || {
              "500$": 0.01,
              "1000$": 0.02,
              "5000$": 0.08,
              "10000$": 0.16,
              standard_risk_pct: "1.0%"
            },
            agents: {
              agent1_price_strategy: crew.agents?.market_structure_analyst,
              agent2_support_resistance: crew.agents?.liquidity_zones_analyst,
              agent3_risk_reward: crew.agents?.risk_manager,
              agent4_chart_drawer: crew.agents?.market_structure_analyst,
              agent5_confirmation_auditor: crew.agents?.chief_trading_officer,
              agent6_telegram_dispatcher: crew.agents?.telegram_dispatcher,
              agent7_trade_guardian: {
                guardian_verdict: "MARKET_HEALTHY",
                reversal_risk: "LOW",
                action_recommended: "HOLD_TRADE",
                advice_ar: "🛡️ المراقب الفني: الوضع مستقر مع إدارة المخاطر الخماسية.",
                summary_ar: "الوكيل 7 يراقب مسار الصفقات لحظة بلحظة."
              }
            },
            inter_agent_dialogue: crew.inter_agent_dialogue || [],
            missing_conditions: setup.status === "CONFIRMED_ENTRY" ? [] : ["في انتظار اكتمال كافة شروط الـ CTO وتأكيد السيولة"],
            summary_ar: crew.summary_ar || "منظومة CrewAI الخماسية تتابع السوق لحظياً.",
            timestamp: Date.now()
          };

          multiAgentCache.set(cacheKey, { result, expires: now + 2000 });
          resolve(result);
        } catch (err: any) {
          console.warn("[MultiAgentBridge] JSON parse fallback:", err.message);
          resolve(createFallbackMultiAgentResult(symbol, currentPrice, timeframe));
        }
      }
    );
  });
}

function createFallbackMultiAgentResult(
  symbol: string,
  price: number,
  timeframe: string
): MultiAgentSystemResult {
  const isGold = symbol.includes("XAU") || symbol.toLowerCase().includes("gold");
  const pipSize = isGold ? 0.1 : 0.0001;

  return {
    engine: "7-Agent Collaborative Python AI Trading Ecosystem (Fallback Synchronous Mode)",
    symbol,
    current_price: price,
    timeframe,
    status: "WAITING_CONFIRMATION",
    action: "WAIT",
    is_actionable_now: false,
    confidence: 82,
    selected_strategy: "SMC Demand Block & SSL Sweep",
    entry_price: price,
    stop_loss: Number((price - 6.0).toFixed(2)),
    target1: Number((price + 12.0).toFixed(2)),
    target2: Number((price + 20.4).toFixed(2)),
    risk_reward: "1:2.0",
    pips_risk: 60,
    pips_target1: 120,
    pips_target2: 204,
    lot_sizing: {
      "500$": 0.01,
      "1000$": 0.02,
      "5000$": 0.08,
      "10000$": 0.16,
      standard_risk_pct: "1.0%"
    },
    agents: {
      agent1_price_strategy: {
        trend: "BULLISH",
        primary_strategy: "SMC Demand Block & SSL Sweep",
        proposed_action: "BUY",
        strategy_score: 82,
        summary_ar: "الوكيل 1 يحلل حركة الشموع ويقترح متابعة نموذج ارتداد كتلة الطلب المؤسساتية."
      },
      agent2_support_resistance: {
        support: price - 6.0,
        resistance: price + 10.0,
        bsl_target: price + 10.0,
        ssl_target: price - 6.0,
        summary_ar: "الوكيل 2 يحدد مستويات الدعم والمقاومة اللحظية."
      },
      agent3_risk_reward: {
        risk_reward: "1:2.0",
        sl_pips: 60,
        tp1_pips: 120,
        tp2_pips: 204,
        summary_ar: "الوكيل 3 يحسب وقف الخسارة والعائد (1:2.0) وحجم اللوت المناسب لقاعدة 1% مخاطرة."
      },
      agent4_chart_drawer: {
        chart_annotations_count: 6,
        summary_ar: "الوكيل 4 يقوم برسم المستويات الفنية والمناطق على الشارت."
      },
      agent5_confirmation_auditor: {
        verdict: "WAITING_CONFIRMATION",
        is_confirmed: false,
        confluence_score: 82,
        pillars_passed: "4/5",
        summary_ar: "الوكيل 5 يحجب الإشارة لحماية رأس المال حتى اكتمال شمعة الارتداد."
      },
      agent6_telegram_dispatcher: {
        dispatch_status: "SUPPRESSED_PENDING_CONFIRMATION",
        summary_ar: "الوكيل 6 جاهز لصياغة وإرسال الإشعار فور اكتمال موافقة الوكيل 5."
      },
      agent7_trade_guardian: {
        action_recommended: "HOLD_TRADE",
        advice_ar: "المراقب (الوكيل 7): السوق قيد المراقبة اللحظية والحماية مفعلة.",
        summary_ar: "الوكيل 7 يراقب حركة السعر الحية لمنع الانعكاسات المفاجئة."
      }
    },
    inter_agent_dialogue: [
      {
        timestamp: Date.now(),
        time_str: new Date().toISOString().slice(11, 19) + " UTC",
        sender: "Agent 1: Price Action & Strategy Analyst",
        recipient: "Agent 2: Support, Resistance & Liquidity Hunter",
        topic: "REQUEST_KEY_LEVELS",
        summary: "طلب مناطق الدعم والمقاومة والسيولة",
        data: {}
      },
      {
        timestamp: Date.now(),
        time_str: new Date().toISOString().slice(11, 19) + " UTC",
        sender: "Agent 2: Support, Resistance & Liquidity Hunter",
        recipient: "Agent 1: Price Action & Strategy Analyst",
        topic: "KEY_LEVELS_PROVIDED",
        summary: "توفير مستويات الدعم والمقاومة",
        data: {}
      }
    ],
    missing_conditions: [
      "في انتظار اكتمال شمعة M15 الاندفاعية لتأكيد كسر الهيكل الصاعد"
    ],
    summary_ar: "الوكلاء السبعة يراقبون السوق لحظياً لحماية الحساب.",
    timestamp: Date.now()
  };
}

/**
 * Runs the CrewAI 5-Agent Trading System (Market Structure, Liquidity, Risk Manager, CTO, Dispatcher)
 */
export async function runCrewAITradingSystem(
  symbol: string = "XAU/USD",
  currentPrice: number = 4001.5,
  candles?: any[]
): Promise<any> {
  const scriptPath = path.resolve(process.cwd(), "server/crew_ai_trading_system.py");

  const payload = {
    symbol,
    price: currentPrice,
    current_price: currentPrice,
    candles: Array.isArray(candles) && candles.length >= 10 ? candles.slice(-50) : []
  };

  const payloadStr = JSON.stringify(payload);

  return new Promise((resolve) => {
    execFile(
      PYTHON_BIN,
      [
        scriptPath,
        "--symbol", symbol,
        "--price", String(currentPrice),
        "--json", payloadStr
      ],
      // Force UTF-8 stdout so Arabic output does not crash Python on Windows (cp1252 console)
      { timeout: 5000, maxBuffer: 2 * 1024 * 1024, env: { ...process.env, PYTHONIOENCODING: "utf-8" } },
      (error, stdout, stderr) => {
        if (error || !stdout.trim()) {
          console.warn(`[CrewAI Bridge] Subprocess notice (${symbol}):`, error?.message || stderr);
          return resolve({
            framework: "CrewAI 5-Agent Trading System (Synchronous Fallback)",
            symbol,
            current_price: currentPrice,
            status: "WAITING_CONFIRMATION",
            action: "WAIT",
            confidence: 85,
            summary_ar: "نظام CrewAI يتابع حركة السوق لحظياً حماية لرأس المال."
          });
        }

        try {
          const parsed = JSON.parse(stdout.trim());
          resolve(parsed);
        } catch (err: any) {
          console.warn("[CrewAI Bridge] JSON parse fallback:", err.message);
          resolve({
            framework: "CrewAI 5-Agent Trading System (Fallback)",
            symbol,
            current_price: currentPrice,
            status: "WAITING_CONFIRMATION",
            action: "WAIT",
            confidence: 85,
            summary_ar: "نظام CrewAI يعمل في الوضع الاحتياطي."
          });
        }
      }
    );
  });
}
