import { MarketAsset, AISignal, NewsItem } from '../types';

export const INITIAL_ASSETS: MarketAsset[] = [
  {
    id: 'gold',
    symbol: 'XAU/USD',
    name: 'Gold / US Dollar (Spot Institutional)',
    arabicName: 'الذهب الفوري / الدولار الأمريكي',
    frenchName: 'Or au Comptant / Dollar US',
    category: 'metals',
    price: 2685.50,
    change24h: 0.28,
    change24hAmount: 7.50,
    high24h: 2700.00,
    low24h: 2675.00,
    volume24h: '$58.2B',
    trend: 'Bullish',
    trendStrength: 94,
    decimalPlaces: 2,
    pipSize: 0.1,
  },
  {
    id: 'eurusd',
    symbol: 'EUR/USD',
    name: 'Euro / US Dollar (Spot Institutional)',
    arabicName: 'اليورو / الدولار الأمريكي',
    frenchName: 'Euro au Comptant / Dollar US',
    category: 'forex',
    price: 1.0845,
    change24h: 0.15,
    change24hAmount: 0.0016,
    high24h: 1.0880,
    low24h: 1.0810,
    volume24h: '$125.0B',
    trend: 'Bullish',
    trendStrength: 90,
    decimalPlaces: 4,
    pipSize: 0.0001,
  }
];

export const INITIAL_SIGNALS: AISignal[] = [
  {
    id: 'sig-gold',
    symbol: 'XAU/USD',
    assetName: 'Spot Gold / الذهب الفوري المؤسساتي',
    signalType: 'BUY',
    signalLabel: 'CONFIRMED BUY (SMC LIQUIDITY SWEEP & FVG RETEST)',
    entryZone: '4125.50 - 4126.80',
    entryPrice: 4126.10,
    stopLoss: 4118.00,
    target1: 4142.30,
    target2: 4153.60,
    confidence: 88,
    setupGrade: 'A+',
    confluenceScore: 88,
    isHighConfirmation: true,
    isActionableNow: true,
    reasons: [
      'سحب سيولة قاع جلسة آسيا ولندن (M15 SSL Sweep) واختراق القاع ثم الإغلاق الصريح داخل النطاق',
      'اندفاع سعري قوي M5 Displacement بإغلاق شمعة زخم جسمها > 65% وتجاوزت 1.3x ATR(14)',
      'تكوين فجوة قيمة عادلة نقية 3-Candle Bullish FVG غير ملموسة مع وضع أمر معلق عند 50% CE',
      'تطابق نافذة نيويورك الزمنية (14:00 - 15:00 GMT / 10:00 - 11:00 EST) بدون أي ذبذبة أخبار عنيفة'
    ],
    confluenceChecklist: [
      { id: 'c1', label: 'Pre-14:00 GMT M15 Prep', labelAr: 'تحضير سيولة M15: رسم قمم وقيعان آسيا ولندن', passed: true, detail: 'قمم وقيعان جلسة آسيا (00-08h) ولندن (08-14h) مرسومة آلياً' },
      { id: 'c2', label: 'M5 Liquidity Sweep (14-15h GMT)', labelAr: 'سحب سيولة M5 داخل نافذة نيويورك', passed: true, detail: 'كسر قاع SSL وإغلاق فوري داخل النطاق خلال نافذة الـ 60 دقيقة' },
      { id: 'c3', label: 'M5 Displacement & MSS', labelAr: 'كسر هيكل صاعد بزخم قوي (Body > 65%)', passed: true, detail: 'شمعة اختراق قوية بجسم 72% ومدى 1.6x من الـ ATR(14)' },
      { id: 'c4', label: 'Unmitigated FVG & 50% CE', labelAr: 'فجوة FVG غير ملموسة مع أمر معلق 50% CE', passed: true, detail: 'تحديد دقيق لفجوة 3 شموع والدخول عند منتصف Consequent Encroachment' },
      { id: 'c5', label: 'Strict Risk:Reward >= 1:2', labelAr: 'وقف هيكلي + بافر 0.5 ATR وعائد يفوق 1:2', passed: true, detail: 'وقف أسفل قاع السحب مع نسبة عائد صافية تفوق 1:2.8' }
    ],
    smcDetails: {
      orderBlockZone: '4175.50 - 4178.00 (M5 FVG 50% CE Zone)',
      liquiditySwept: 'سحب سيولة قاع آسيا ولندن @ 4164.20 (SSL Swept)',
      fvgMitigation: 'فجوة سعرية نقية غير ملموسة تنتظر ملامسة 50% CE',
      marketStructureShift: 'Bullish MSS مؤكد باختراق شمعة الاندفاع لقمة 4172.50',
      invalidationReason: 'كسر قاع السحب 4163.00 يلغي النموذج تماماً'
    },
    managementPlan: {
      tp1Action: 'حجز 50% من أرباح العقد عند 4198.00 ونقل الستوب فوراً لسعر الدخول (Breakeven 0$ Risk)',
      tp2Action: 'ترك الـ 50% الباقية لتصل لهدف سيولة القمم الخارجية عند 4220.00 بأمان كامل',
      stopLossLogic: 'وقف الخسارة محكم خلف ذيل شمعة السحب + 0.5x ATR(14) لمنع ضرب الستوب العشوائي',
      maxRiskAdvice: 'المخاطرة الصارمة: 1% فقط من رصيد الحساب (0.01 لوت لكل 1000$)'
    },
    riskReward: '1:2.9',
    timeframe: 'M15 Prep / M5 Execution',
    createdAt: 'NY Silver Bullet (14:00 - 15:00 GMT)',
    status: 'ACTIVE'
  }
];

export const INITIAL_NEWS: NewsItem[] = [
  {
    id: 'n-1',
    title: 'Fed signals potential rate cuts as inflation softens; Gold surges on institutional safe-haven flows',
    titleAr: 'الفيدرالي الأمريكي يلمح لخفض الفائدة مع تباطؤ التضخم، والذهب يقفز بتدفقات مؤسساتية كبرى',
    timeAgo: 'منذ 12 دقيقة',
    source: 'Bloomberg Terminal',
    category: 'fed',
    importance: 'HIGH',
    impactAsset: 'XAU/USD (Gold)',
    impactVerdict: 'positive',
    impactHeadlineAr: 'إيجابي جداً للذهب (Strong Bullish Gold Catalyst)',
    reasonAr: 'انخفاض عوائد سندات الخزانة الأمريكية وتراجع مؤشر الدولار DXY يدفع السيولة العالمية نحو الذهب كملاذ آمن وأصل سيادي أول.',
    reasonEn: 'Falling US Treasury yields and Dollar Index weakness directly compress opportunity cost, triggering multi-billion institutional inflows into Gold.',
  },
  {
    id: 'n-2',
    title: 'Global Central Banks accelerate physical gold reserves accumulation at record pace',
    titleAr: 'البنوك المركزية العالمية تسرع وتيرة شراء احتياطيات سبائك الذهب بوتيرة قياسية',
    timeAgo: 'منذ 28 دقيقة',
    source: 'World Gold Council',
    category: 'commodities',
    importance: 'HIGH',
    impactAsset: 'XAU/USD',
    impactVerdict: 'positive',
    impactHeadlineAr: 'دعم هيكلي طويل الأمد للذهب (Institutional Physical Demand)',
    reasonAr: 'مشتريات البنوك المركزية توفر قاعاً صلباً ودعماً مستمراً لأسعار الذهب فوق مستويات 4100$.',
    reasonEn: 'Continuous physical bullion purchases by global central banks provide an unyielding structural floor under gold prices.',
  }
];
