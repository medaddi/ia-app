export type Language = 'fr' | 'ar' | 'en';

export type AssetCategory = 'metals' | 'crypto' | 'forex' | 'stocks' | 'commodities' | 'equities';

export interface MarketAsset {
  id: string;
  symbol: string;
  name: string;
  arabicName: string;
  frenchName?: string;
  category: AssetCategory;
  price: number;
  change24h: number;
  change24hAmount: number;
  high24h: number;
  low24h: number;
  volume24h: string;
  trend: 'Bullish' | 'Bearish' | 'Sideways';
  trendStrength: number; // 0 - 100%
  pipSize: number;
  decimalPlaces: number;
  isMarketOpen?: boolean;
  marketStatusLabel?: string;
  marketSource?: string;
  nextOpen?: string;
}

export interface Candle {
  time: number; // unix timestamp in seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SMCIndicators {
  orderBlock: {
    low: number;
    high: number;
    type: 'Bullish Demand OB' | 'Bearish Supply OB';
    timeframe: string;
  };
  fairValueGap: {
    low: number;
    high: number;
    status: 'Open Imbalance' | 'Mitigated' | 'Partial Fill';
  };
  liquiditySweep: {
    level: number;
    session: string;
    type: 'BSL Swept (Buy-Side)' | 'SSL Swept (Sell-Side)' | 'Testing Liquidity';
    timeAgo: string;
  };
  marketStructureShift: 'Bullish MSS Confirmed' | 'Bearish MSS Confirmed' | 'Range Consolidation';
  premiumDiscount: 'Discount Zone (Optimal Long)' | 'Premium Zone (Optimal Short)' | 'Equilibrium 50%';
  confluenceScore: number; // 0 - 100%
  institutionalBias: string;
}

export interface TechnicalIndicators {
  ema20: number;
  ema50: number;
  ema200: number;
  rsi: number;
  macd: {
    line: number;
    signal: number;
    hist: number;
  };
  bollingerBands: {
    upper: number;
    middle: number;
    lower: number;
  };
  fibonacci: {
    level0: number;
    level236: number;
    level382: number;
    level500: number;
    level618: number;
    level100: number;
  };
  support: number;
  resistance: number;
  marketStructure: string;
  structureNote: string;
  candlestickPattern: string;
  setupProbability: number;
  smc?: SMCIndicators;
}

export interface ConfluenceCheckItem {
  id: string;
  label: string;
  labelAr: string;
  passed: boolean;
  detail: string;
}

export interface MastersBookRule {
  bookTitle: string;
  author: string;
  principle: string;
  principleAr: string;
  appliedRule: string;
  appliedRuleAr: string;
  verified: boolean;
  notes: string;
}

export interface MastersTradingVerification {
  markDouglasDiscipline: MastersBookRule;       // Trading in the Zone
  jesseLivermorePivotalPoint: MastersBookRule;  // Reminiscences of a Stock Operator
  paulTudorJonesRiskAsymmetry: MastersBookRule; // Market Wizards
  mikeBellafioreOneGoodTrade: MastersBookRule;  // One Good Trade
  richardWyckoffSmartMoney: MastersBookRule;    // The Wyckoff Method
  overallMastersScore: number;                  // 100% when all verified
  allConditionsPassed: boolean;
}

export interface AISignal {
  id: string;
  symbol: string;
  assetName: string;
  signalType: 'BUY' | 'SELL' | 'WAIT';
  signalLabel: string; // e.g. "BUY POSSIBLE"
  entryZone: string;   // e.g. "4288.50 - 4292.00"
  entryPrice?: number; // mid/numeric entry price for drawing on chart
  stopLoss: number;    // e.g. 4274.00
  target1: number;     // e.g. 4322.00 (Realistic TP1 - 1:1.85 R:R)
  target2: number;     // e.g. 4342.00 (Realistic TP2 - 1:3.00 R:R)
  target3?: number;    // e.g. 4365.00 (Extended TP3 - 1:4.50 R:R)
  confidence: number;  // e.g. 91%
  reasons: string[];
  riskReward: string;  // e.g. "1:3.2"
  timeframe: string;   // e.g. "15M / 4H"
  createdAt: string;
  status: 'ACTIVE' | 'TARGET_HIT' | 'EXPIRED' | 'MARKET_CLOSED';
  overallVerdict?: 'STRONG_BUY_SETUP' | 'STRONG_SELL_SETUP' | 'WAIT' | 'NO_TRADE';
  invalidationCondition?: string;
  invalidationConditionAr?: string;
  dataSourceName?: string;
  timestampFormatted?: string;
  positionSizeLots?: number;
  positionSizeUnits?: number;
  maxRiskAmountDollars?: number;
  scoreBreakdown?: {
    htfTrend: number;          // max 20
    marketStructure: number;   // max 15
    liquidityConfirmation: number; // max 15
    supplyDemand: number;      // max 10
    entryConfirmation: number; // max 15
    volume: number;            // max 10
    momentum: number;          // max 5
    riskReward: number;        // max 10
    totalScore: number;        // 0 - 100
  };
  validationChecklist?: {
    dataValid: boolean;
    structureValid: boolean;
    htfAligned: boolean;
    entryConfirmed: boolean;
    slLogical: boolean;
    tpLogical: boolean;
    acceptableRR: boolean;
    spreadAcceptable: boolean;
    volatilityAcceptable: boolean;
    noAbnormalConditions: boolean;
    riskWithinLimits: boolean;
    allChecksPassed: boolean;
    failureReasons?: string[];
  };
  isMarketOpen?: boolean;
  marketStatusLabel?: string;
  // Immediate Actionability & Execution Timing
  currentLivePrice?: number; // Real-time market tick price
  isActionableNow?: boolean; // Price is strictly in optimal entry zone RIGHT NOW
  distanceToEntryPips?: number;
  distanceToEntryText?: string;
  actionableWindow?: string;
  entryTimingQuality?: 'OPTIMAL_CONFIRMED' | 'WAITING_PULLBACK' | 'MONITORING';
  entryTimingNoteAr?: string;
  entryTimingNoteFr?: string;
  tightRiskAdvantageAr?: string;
  confirmationCheckPassed?: boolean;
  confirmationCandle15M?: {
    confirmed: boolean;
    candleType: string;
    timeframe: string;
    rejectionWickDetail: string;
    bodyDisplacementPct?: number;
    statusAr: string;
    statusEn: string;
    candleCloseTimerMinutes?: number;
  };
  confirmationCandle5M?: {
    confirmed: boolean;
    candleType: string;
    rejectionWickDetail: string;
    statusAr: string;
    statusEn: string;
  };
  // Elite World-Class Trading Strategies
  strategyUsed?: string; // e.g. "ICT Judas Swing + FVG", "Wyckoff Phase C Spring", "Order Flow Delta"
  strategyType?: 'ICT_SMC' | 'WYCKOFF' | 'ORDER_FLOW' | 'PROP_FIRM_MASTER' | 'MACRO_CONFLUENCE';
  winRateHistorical?: number; // e.g. 89.2%
  slPointsOrPips?: number;
  tp1PointsOrPips?: number;
  tp2PointsOrPips?: number;
  // Institutional / Smart Money Concepts enhancement
  setupGrade?: 'A+' | 'A' | 'B+';
  validatedByAgentId?: string;
  validatedByAgentNameAr?: string;
  agentSpecialtyBadge?: string;
  confluenceScore?: number; // e.g. 91
  isHighConfirmation?: boolean; // Only top tier trades (4+ out of 5 confirmations)
  confluenceChecklist?: ConfluenceCheckItem[];
  mastersVerification?: MastersTradingVerification;
  // ============================================================
  // PAIR-SPECIFIC ANALYSIS & DYNAMIC SL/TP ENGINE (PROMPT REQ #5)
  // ============================================================
  pairProfile?: PairProfile;
  dynamicSLTP?: DynamicSLTPAnalysis;
  analyticalPlan?: any;
  lifecycleState?: SetupLifecycleState;
  marketRegime?: MarketRegimeType;
  // ============================================================
  // ADVANCED TRADING DECISION ENGINE (10 PILLARS)
  // ============================================================
  decisionStatus?: 'ALLOWED' | 'NO_TRADE';
  tradeScore?: number; // 0 - 100%
  tradeScoreGrade?: 'VERY_STRONG' | 'GOOD' | 'REJECTED';
  marketSuitability?: {
    isSuitable: boolean;
    trend: 'Bullish' | 'Bearish' | 'Sideways';
    reasonAr: string;
    reasonEn: string;
    emaAlignment: string;
    structureVerdict: string;
  };
  multiTimeframeAlignment?: {
    htfAligned: boolean; // 4H / 1D
    mtfAligned: boolean; // 1H / 15M
    ltfAligned: boolean; // 5M / 15M
    allAligned: boolean;
    summaryAr: string;
    summaryEn: string;
  };
  smartEntryChecklist?: {
    items: { key: string; label: string; labelAr: string; passed: boolean; note: string }[];
    allPassed: boolean;
  };
  smcEngine?: {
    bosConfirmed: boolean;
    chochConfirmed: boolean;
    liquiditySweepConfirmed: boolean;
    fvgDetected: boolean;
    avoidHugeCandlePassed: boolean;
    avoidMiddleOfRangePassed: boolean;
    avoidLiquidityTrapPassed: boolean;
    institutionalZone: string;
  };
  lossPrevention?: {
    volatilitySafe: boolean;
    spreadSafe: boolean;
    newsSafe: boolean;
    manipulationSafe: boolean;
    timingSafe: boolean;
    safeToTrade: boolean;
    riskLevel: 'LOW' | 'MEDIUM' | 'HIGH';
    rejectionReasons: string[];
    rejectionReasonsAr: string[];
  };
  newsCatalyst?: {
    isHighImpactLockout?: boolean;
    isUncertaintyActive?: boolean;
    sentimentScore?: number;
    headlineAr?: string;
    headlineEn?: string;
    lockoutReasonAr?: string;
    lockoutReasonEn?: string;
    source?: string;
  };
  tradeExplanation?: {
    direction: 'BUY' | 'SELL' | 'NO TRADE';
    entry: string;
    stopLoss: string;
    takeProfit: string;
    confidence: number;
    tradeScore: number;
    reasons: string[];
    reasonsAr: string[];
    marketCondition: string;
    riskLevel: 'LOW' | 'MEDIUM' | 'HIGH';
  };
  smcDetails?: {
    orderBlockZone: string;
    liquiditySwept: string;
    fvgMitigation: string;
    marketStructureShift: string;
    invalidationReason: string;
    confirmationCandle15M?: {
      confirmed: boolean;
      candleType: 'M15_DISPLACEMENT_BODY_CLOSE' | 'M15_REJECTION_PINBAR_SWEEP' | 'M15_CHOCH_MSS_CONFIRMED';
      timeframe: '15M';
      rejectionWickDetail: string;
      bodyDisplacementPct: number;
      statusAr: string;
      statusEn: string;
      candleCloseTimerMinutes?: number;
    };
    confirmationCandle5M?: {
      confirmed: boolean;
      candleType: 'ENGULFING_DISPLACEMENT' | 'REJECTION_PINBAR' | 'CHOCH_BODY_CLOSE';
      rejectionWickDetail: string;
      statusAr: string;
      statusEn: string;
    };
  };
  managementPlan?: {
    tp1Action: string; // e.g. "حجز 60% أرباح + نقل وقف الخسارة إلى نقطة الدخول (Breakeven)"
    tp2Action: string; // e.g. "إغلاق باقي العقد (40%) عند هدف السيولة الكبرى"
    stopLossLogic: string; // e.g. "موضوع أسفل قاع سحب السيولة بـ 2 pips لحماية رأس المال"
    maxRiskAdvice: string; // e.g. "1% كحد أقصى لحجم الحساب"
  };
  // Real-Time Macro News & Economic Confluence
  newsConfluence?: {
    headline: string;
    headlineAr: string;
    source: string;
    impactVerdict: 'positive' | 'negative' | 'neutral';
    importance: 'HIGH' | 'MEDIUM' | 'LOW';
    alignedWithSignal: boolean;
    confluenceNoteAr: string;
  };
  // 100% High-Precision Institutional Mathematical Metrics
  precisionMetrics?: {
    fibOteRange: string;
    fibOteGoldenPrice: number;
    fib618Price: number;
    fib786Price: number;
    fvgUpperPrice: number;
    fvgLowerPrice: number;
    fvgConsequentEncroachment: number;
    liquiditySweepPrice: number;
    liquidityType: 'SSL_SWEEP' | 'BSL_SWEEP';
    sessionKillzone: string;
    sessionTimingValid: boolean;
    multiTimeframeMatrix: {
      tf4h: { bias: 'BULLISH' | 'BEARISH'; struct: string };
      tf1h: { bias: 'BULLISH' | 'BEARISH'; struct: string };
      tf15m: { bias: 'BULLISH' | 'BEARISH'; struct: string };
      tf5m: { bias: 'BULLISH' | 'BEARISH'; struct: string };
      confluencePercent: number;
    };
    volumeDeltaStats: {
      buyVolumePct: number;
      sellVolumePct: number;
      deltaInterpretation: string;
      cvdDivergence: boolean;
    };
    atr14: number;
    lotSizeCalculations: {
      account500: { lot: string; riskUsd: string; gainTp1: string; gainTp2: string };
      account1000: { lot: string; riskUsd: string; gainTp1: string; gainTp2: string };
      account5000: { lot: string; riskUsd: string; gainTp1: string; gainTp2: string };
      account10000: { lot: string; riskUsd: string; gainTp1: string; gainTp2: string };
    };
    exactPipsRisk: number;
    exactPipsGainTp1: number;
    exactPipsGainTp2: number;
    invalidationPipLevel: number;
  };
  technicalIndicators?: any;
  reasoning?: string;
  arabicReasoning?: string;
  frenchReasoning?: string;
  decisionAudit?: any;
  action?: string;
  allStrategyScores?: Array<{
    strategy: string;
    score: number;
    action: 'BUY' | 'SELL' | 'NO_TRADE';
    matched: boolean;
    reason?: string;
  }>;
  sessionInfo?: any;
  pipsRisk?: number;
  pipsTarget1?: number;
  pipsTarget2?: number;
  pipSize?: number;
}

export interface NewsItem {
  id: string;
  title: string;
  titleAr: string;
  source: string;
  timeAgo: string;
  category: 'fed' | 'cpi' | 'nfp' | 'geopolitical' | 'corporate' | 'commodities' | 'forex';
  impactAsset: string;
  impactVerdict: 'positive' | 'negative' | 'neutral';
  impactHeadlineAr: string; // e.g. "إيجابي للذهب" / "سلبي للدولار"
  reasonAr: string;
  reasonEn: string;
  importance: 'HIGH' | 'MEDIUM' | 'LOW';
  url?: string;
  isLive?: boolean;
  publishedAt?: string;
  isLockoutEvent?: boolean;
  isUncertainty?: boolean;
  lockoutReasonAr?: string;
  lockoutReasonEn?: string;
}

export interface SentimentData {
  assetSymbol: string;
  positive: number; // e.g. 68
  negative: number; // e.g. 22
  neutral: number;  // e.g. 10
  sentimentSummaryAr: string;
  sources: {
    twitter: { positive: number; negative: number; neutral: number };
    reddit: { positive: number; negative: number; neutral: number };
    news: { positive: number; negative: number; neutral: number };
  };
  fearAndGreedIndex: number; // 0 - 100
  fearAndGreedLabel: string; // "Extreme Greed", "Greed", "Neutral", "Fear"
}

export interface RiskCalculationResult {
  accountBalance: number;
  riskPercent: number;
  maxLossDollars: number;
  entryPrice: number;
  stopLossPrice: number;
  pipsRisked: number;
  recommendedLotSize: number;
  riskRewardRatio: number;
  potentialProfitT1: number;
  potentialProfitT2: number;
  riskEvaluationAr: string;
  status: 'SAFE' | 'MODERATE' | 'HIGH_RISK';
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  signalContext?: AISignal;
}

export interface TelegramConfig {
  botToken: string;
  chatId: string;
  enabled: boolean;
  minConfidence: number; // e.g. 75%
  assets: string[]; // e.g. ['XAU/USD', 'BTC/USDT', 'EUR/USD']
  notifyOnNews: boolean;
  activationCode?: string;
  codeExpiresAt?: number;
  isCodeValid?: boolean;
}

export interface ActivationKey {
  code: string;
  createdAt: number;
  expiresAt: number;
  durationHours: number;
  durationLabel: string;
  note?: string;
  isActive: boolean;
}

export interface TelegramNotificationHistory {
  id: string;
  type: 'SIGNAL' | 'TEST' | 'NEWS';
  title: string;
  details: string;
  sentAt: string;
  status: 'SUCCESS' | 'FAILED';
  error?: string;
}

export type SignalOutcome = 'TP2_HIT' | 'TP1_HIT' | 'SL_HIT' | 'BE_CLOSED' | 'ACTIVE';

export interface SignalAuditRecord {
  id: string;
  symbol: string;
  assetName: string;
  signalType: 'BUY' | 'SELL';
  entryPrice: number;
  stopLoss: number;
  target1: number;
  target2: number;
  riskReward: string;
  setupGrade: 'A+' | 'A' | 'B+';
  timeframe: string;
  date: string;
  closedAt?: string;
  outcome: SignalOutcome;
  pipsGained: number; // e.g. +140 or -30
  realizedRR: number; // e.g. +3.25 or -1.0
  notesAr: string;
}

export interface AssetPerformanceStat {
  symbol: string;
  name: string;
  totalSignals: number;
  wins: number;
  slHits: number;
  winRate: number;
  pipsGained: number;
}

export interface LiveActiveTradeItem {
  id: string;
  symbol: string;
  assetName: string;
  signalType: 'BUY' | 'SELL';
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
  status: 'ACTIVE' | 'TP1_HIT' | 'TP2_HIT' | 'SL_HIT';
  timeAgo: string;
}

export interface SignalsPerformanceStats {
  totalSignals: number;
  closedSignals: number;
  activeSignals: number;
  tp1Hits: number;
  tp2Hits: number;
  slHits: number; // شحال من SL ضرب
  beHits: number;
  winRate: number; // نسبة النجاح الإجمالية %
  profitFactor: number;
  totalPipsGained: number;
  averageRiskReward: string;
  consecutiveWins: number;
  maxDrawdownPercent: number;
  recentAuditHistory: SignalAuditRecord[];
  assetBreakdown: AssetPerformanceStat[];
  lastUpdated: string;
}

export interface AIMacroLearningState {
  learningIteration: number;
  lastUpdated: string;
  adaptiveDrift: number;
  neuralWeights: {
    asianSweepWeight: number;
    orderBlockWeight: number;
    macroNewsWeight: number;
    chochWeight: number;
  };
  topMacroAnalysis: {
    symbol: string;
    assetName: string;
    macroSynthesisAr: string;
    macroSynthesisEn: string;
    htfTrend4H: string;
    ltfTrigger15M: string;
    newsCorrelationVerdict: 'BULLISH_CATALYST' | 'BEARISH_CATALYST' | 'NEUTRAL_ABSORPTION';
    newsCorrelationSummaryAr: string;
    activeCatalysts: {
      headline: string;
      source: string;
      impact: 'HIGH' | 'MEDIUM';
      alignment: 'ALIGNED' | 'CONFLICTING';
      effectAr: string;
    }[];
    institutionalScore: number;
    recommendedActionAr: string;
    timingConfidence: number;
  };
}

export interface OmniRadarAssetStatus {
  symbol: string;
  name: string;
  arabicName: string;
  category: AssetCategory;
  price: number;
  change24h: number;
  isMarketOpen: boolean;
  isKillzoneActive: boolean;
  killzoneNameAr: string;
  radarStatus: 'A_PLUS_OPPORTUNITY' | 'IN_ENTRY_ZONE' | 'SCANNING_LIQUIDITY' | 'WAITING_STRUCTURE' | 'MARKET_CLOSED';
  statusLabelAr: string;
  statusLabelFr: string;
  statusLabelEn: string;
  confluenceScore: number;
  estimatedWinRate: string;
  currentPhaseAr: string;
  currentPhaseFr: string;
  suggestedAction: 'BUY' | 'SELL' | 'WAIT';
  entryZone?: string;
  stopLoss?: number;
  target1?: number;
  target2?: number;
  riskReward?: string;
  strategyName?: string;
  distanceToEntryPips?: number;
}

export interface OmniRadarState {
  omniRadarEnabled: boolean;
  activeMarketsCount: number;
  totalMarketsMonitored: number;
  opportunitiesFound: number;
  lastScanTimestamp: number;
  scanIntervalSeconds: number;
  assets: OmniRadarAssetStatus[];
}

export type AgentSpecialistId = 
  | 'agent_gold' 
  | 'agent_gold_ict'
  | 'agent_gold_macro'
  | 'agent_eurusd' 
  | 'agent_gbpusd' 
  | 'agent_usdjpy' 
  | 'agent_audusd' 
  | 'agent_usdcad' 
  | 'agent_btc' 
  | 'agent_eth' 
  | 'agent_oil' 
  | 'agent_nvda' 
  | 'agent_aapl'
  | 'agent_crypto' 
  | 'agent_forex' 
  | 'agent_equities';

export interface MarketSpecialistAgent {
  id: AgentSpecialistId;
  name: string;
  arabicName: string;
  arabicRole: string;
  avatarEmoji: string;
  accentColor: string;
  assignedSymbols: string[];
  category: AssetCategory;
  status: 'ACTIVE_HUNTING' | 'ANALYZING_SETUP' | 'SIGNAL_CONFIRMED' | 'STANDBY_SESSION';
  statusLabelAr: string;
  statusLabelFr: string;
  currentBias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  specialtyMethodAr: string;
  primaryKillzonesAr: string;
  liveMarketThesisAr: string;
  liveMarketThesisFr: string;
  activeOpportunitiesCount: number;
  confluenceScore: number;
  verifiedWinRate: number;
  totalSetupsCaptured: number;
  lastAnalysisTimestamp: number;
  topCandidateSymbol: string;
  activeSignal?: AISignal | null;
  patienceLevelAr?: string;
  confirmationRuleAr?: string;
  riskModelAr?: string;
  experienceYears?: string;
}

export interface AgentChatMessage {
  id: string;
  agentId: AgentSpecialistId;
  sender: 'user' | 'agent';
  text: string;
  timestamp: number;
  assetSymbol?: string;
}

// ============================================================
// HISTORICAL BACKTESTING ENGINE INTERFACES (REQ #21)
// ============================================================
export interface BacktestConfig {
  symbol: string;
  strategyId: string;
  timeframe: string;
  dateRange: '30D' | '90D' | '180D' | '1Y';
  initialCapital: number;
  riskPerTradePct: number;
}

export interface BacktestTrade {
  id: string;
  timestamp: number;
  dateStr: string;
  symbol: string;
  type: 'BUY' | 'SELL';
  entryPrice: number;
  exitPrice: number;
  stopLoss: number;
  takeProfit: number;
  result: 'WIN' | 'LOSS';
  pnlDollars: number;
  pnlPct: number;
  riskRewardAchieved: number;
  exitReason: 'TP1' | 'TP2' | 'TP3' | 'SL' | 'BREAKEVEN';
}

export interface BacktestResult {
  config: BacktestConfig;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number; // e.g. 74.2%
  profitFactor: number; // e.g. 2.65
  netProfitDollars: number;
  netProfitPct: number;
  maxDrawdownDollars: number;
  maxDrawdownPct: number;
  averageRiskReward: number;
  averageWinDollars: number;
  averageLossDollars: number;
  sharpeRatio: number;
  consecutiveWins: number;
  consecutiveLosses: number;
  equityCurve: { time: number; dateStr: string; balance: number }[];
  trades: BacktestTrade[];
}

// ============================================================
// ALERTS SYSTEM INTERFACES (REQ #20)
// ============================================================
export interface TradingAlert {
  id: string;
  timestamp: number;
  symbol: string;
  type: 'ZONE_REACHED' | 'LIQUIDITY_SWEPT' | 'BOS_CHOCH' | 'ENTRY_CONFIRMED' | 'HIGH_SCORE_SETUP' | 'TP_HIT' | 'SL_HIT';
  title: string;
  titleAr: string;
  message: string;
  messageAr: string;
  score?: number;
  price?: number;
  read: boolean;
}

// ============================================================
// PAIR-SPECIFIC ANALYSIS & DYNAMIC SL/TP ENGINE (PROMPT REQ #5)
// ============================================================

export type MarketRegimeType =
  | 'TRENDING_UP'
  | 'TRENDING_DOWN'
  | 'RANGING'
  | 'HIGH_VOLATILITY'
  | 'LOW_VOLATILITY'
  | 'UNCLEAR_CHOP';

export type VolatilityRegime =
  | 'LOW_COMPRESSION'
  | 'NORMAL_LIQUID'
  | 'HIGH_EXPANSION'
  | 'ERRATIC_SPIKE';

export type SetupLifecycleState =
  | 'DETECTED'
  | 'WAITING_FOR_CONFIRMATION'
  | 'CONFIRMED'
  | 'INVALIDATED'
  | 'EXPIRED'
  | 'WAIT';

export interface PairHistoricalStrategyPerformance {
  strategyName: string;
  winRate: number;
  avgRR: string;
  totalTrades: number;
}

export interface PairProfile {
  symbol: string;
  assetType: 'forex_major' | 'forex_cross' | 'gold' | 'crypto' | 'equity_index' | 'commodity';
  averageAtr: number;
  atrByTimeframe: {
    m15: number;
    h1: number;
    h4: number;
    d1: number;
  };
  averageSpreadPips: number;
  currentSpreadPips: number;
  averageDailyRangePips: number;
  volatilityRegime: VolatilityRegime;
  typicalSessionBehavior: {
    preferredSessions: string[];
    activeSessionNow: string;
    asianSessionCharacter: string;
    londonSessionCharacter: string;
    newYorkSessionCharacter: string;
  };
  trendBehavior: 'Clean trending' | 'Range bound' | 'Mean reverting' | 'Volatile breakouts';
  falseBreakoutFrequency: 'Low' | 'Medium' | 'High';
  liquidityBehavior: string;
  bestPerformingStrategies: string[];
  historicalStrategyPerformance: PairHistoricalStrategyPerformance[];
  newsSensitivity: 'Extreme' | 'High' | 'Moderate' | 'Low';
  lastUpdated: number;
}

export interface DynamicSLTPAnalysis {
  invalidationLevel: number;
  invalidationReason: string;
  invalidationReasonAr: string;
  volatilityBuffer: number;
  bufferReason: string;
  stopLossPrice: number;
  slDistancePoints: number;
  slDistancePips: number;
  takeProfit1Price: number;
  takeProfit1Reason: string;
  takeProfit1RR: number;
  takeProfit2Price: number;
  takeProfit2Reason: string;
  takeProfit2RR: number;
  takeProfit3Price?: number;
  takeProfit3Reason?: string;
  takeProfit3RR?: number;
  overallRR: string;
  lifecycleState: SetupLifecycleState;
  marketRegime: MarketRegimeType;
  regimeReason: string;
  isTradeApproved: boolean;
  rejectionOrWaitReason?: string;
  rejectionOrWaitReasonAr?: string;
}
