/**
 * Real-Time Institutional Trade Performance & Audit Engine:
 * - Tracks Win-Rate % across all dispatched signals
 * - Tracks exact count of Stop Losses Hit (شحال من SL ضرب) vs Targets (TP1 & TP2) Hit
 * - Tracks Net Pips / Profit & Asset breakdown
 * - Provides verified stats for the web application & Telegram Bot (/stats, /performance, /winrate)
 */

import { getLocalDatabase, saveLocalDatabase } from "./localDb";

export interface AuditTrade {
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
  closedAt: string;
  outcome: 'TP2_HIT' | 'TP1_HIT' | 'SL_HIT' | 'BE_CLOSED' | 'ACTIVE';
  pipsGained: number;
  realizedRR: number;
  notesAr: string;
}

// Initial clean baseline ledger for fresh real-time tracking from now on (0 trades, 100% clean slate)
const INITIAL_BASELINE_LEDGER: AuditTrade[] = [];

// In-memory ledger initialized from persistent DB
let AUDIT_LEDGER: AuditTrade[] = [];
const CURRENT_LEDGER_VERSION = 3; // Reset to 0: Fresh Real-Time Audit Tracker from scratch

// Initialize ledger from localDb
export function initLedgerFromDb(forceReset: boolean = false) {
  try {
    const db = getLocalDatabase();
    if (!forceReset && db.tradeAuditLogsVersion === CURRENT_LEDGER_VERSION && db.tradeAuditLogs && Array.isArray(db.tradeAuditLogs)) {
      AUDIT_LEDGER = [...db.tradeAuditLogs];
    } else {
      AUDIT_LEDGER = [];
      saveLocalDatabase((d) => {
        d.tradeAuditLogs = [];
        d.tradeAuditLogsVersion = CURRENT_LEDGER_VERSION;
      });
    }
  } catch (err) {
    AUDIT_LEDGER = [];
  }
}

export function resetLedgerToZero() {
  AUDIT_LEDGER = [];
  try {
    saveLocalDatabase((d) => {
      d.tradeAuditLogs = [];
      d.tradeAuditLogsVersion = CURRENT_LEDGER_VERSION;
    });
  } catch (err) {
    console.error("[SignalPerformance] Failed to save zeroed ledger:", err);
  }
}

export function resetLedgerToBaseline() {
  resetLedgerToZero();
}

// Run initial load
initLedgerFromDb();

/**
 * Appends a real-time audited trade result (TP1, TP2, or SL hit) to the ledger
 * and permanently saves it to disk.
 */
export function recordAuditTradeResult(trade: Omit<AuditTrade, "id" | "date" | "closedAt"> & { id?: string; date?: string; closedAt?: string }) {
  if (AUDIT_LEDGER.length === 0) {
    initLedgerFromDb();
  }

  const newTrade: AuditTrade = {
    id: trade.id || `aud-${Date.now()}`,
    symbol: trade.symbol,
    assetName: trade.assetName,
    signalType: trade.signalType,
    entryPrice: trade.entryPrice,
    stopLoss: trade.stopLoss,
    target1: trade.target1,
    target2: trade.target2,
    riskReward: trade.riskReward || "1:3.5",
    setupGrade: trade.setupGrade || "A+",
    timeframe: trade.timeframe || "15M",
    date: trade.date || new Date().toLocaleDateString("fr-FR"),
    closedAt: trade.closedAt || `اليوم ${new Date().toLocaleTimeString("ar-MA", { hour: "2-digit", minute: "2-digit" })}`,
    outcome: trade.outcome,
    pipsGained: trade.pipsGained,
    realizedRR: trade.realizedRR,
    notesAr: trade.notesAr
  };

  // If already exists in ledger, update it, else unshift
  const existingIdx = AUDIT_LEDGER.findIndex(t => t.id === newTrade.id);
  if (existingIdx >= 0) {
    AUDIT_LEDGER[existingIdx] = newTrade;
  } else {
    AUDIT_LEDGER.unshift(newTrade);
    if (AUDIT_LEDGER.length > 100) AUDIT_LEDGER.pop();
  }

  // Persist atomically to disk
  try {
    saveLocalDatabase((d) => {
      d.tradeAuditLogs = AUDIT_LEDGER;
    });
  } catch (err) {
    console.error('[SignalPerformance] Failed to persist trade audit to localDb:', err);
  }
}

/**
 * Calculates live audited statistics based on the trade ledger
 */
export function getSignalsPerformanceStats() {
  if (AUDIT_LEDGER.length === 0) {
    initLedgerFromDb();
  }

  const closedTrades = AUDIT_LEDGER.filter(t => t.outcome !== 'ACTIVE');
  const tp2Hits = closedTrades.filter(t => t.outcome === 'TP2_HIT').length;
  const tp1Hits = closedTrades.filter(t => t.outcome === 'TP1_HIT').length;
  const slHits = closedTrades.filter(t => t.outcome === 'SL_HIT').length;
  const beHits = closedTrades.filter(t => t.outcome === 'BE_CLOSED').length;
  const activeCount = AUDIT_LEDGER.filter(t => t.outcome === 'ACTIVE').length;

  const totalWins = tp2Hits + tp1Hits;
  const totalDecided = totalWins + slHits;
  const winRate = totalDecided > 0 ? Number(((totalWins / totalDecided) * 100).toFixed(1)) : 0;

  const totalPipsGained = closedTrades.reduce((acc, t) => acc + (t.pipsGained || 0), 0);
  
  // Calculate Profit Factor strictly from actual ledger: (Gross Win Pips / Gross Loss Pips)
  const grossWinPips = closedTrades.filter(t => (t.pipsGained || 0) > 0).reduce((a, b) => a + b.pipsGained, 0);
  const grossLossPips = Math.abs(closedTrades.filter(t => (t.pipsGained || 0) < 0).reduce((a, b) => a + b.pipsGained, 0)) || 0;
  const profitFactor = grossLossPips > 0 ? Number((grossWinPips / grossLossPips).toFixed(2)) : (grossWinPips > 0 ? Number((grossWinPips / 10).toFixed(2)) : 0);

  // Asset breakdowns
  const assetMap = new Map<string, { symbol: string; name: string; total: number; wins: number; sl: number; pips: number }>();
  for (const t of closedTrades) {
    if (!assetMap.has(t.symbol)) {
      assetMap.set(t.symbol, { symbol: t.symbol, name: t.assetName, total: 0, wins: 0, sl: 0, pips: 0 });
    }
    const stat = assetMap.get(t.symbol)!;
    stat.total += 1;
    if (t.outcome === 'TP1_HIT' || t.outcome === 'TP2_HIT') stat.wins += 1;
    if (t.outcome === 'SL_HIT') stat.sl += 1;
    stat.pips += t.pipsGained || 0;
  }

  const assetBreakdown = Array.from(assetMap.values()).map(a => ({
    symbol: a.symbol,
    name: a.name,
    totalSignals: a.total,
    wins: a.wins,
    slHits: a.sl,
    winRate: a.total > 0 ? Number(((a.wins / a.total) * 100).toFixed(1)) : 0,
    pipsGained: a.pips
  }));

  // Dynamically calculate average R:R from actual realized trades
  const rrTrades = closedTrades.filter(t => (t.realizedRR || 0) > 0);
  const avgRRValue = rrTrades.length > 0 
    ? (rrTrades.reduce((acc, t) => acc + t.realizedRR, 0) / rrTrades.length).toFixed(1)
    : '0.0';
  const averageRiskReward = rrTrades.length > 0 ? `1:${avgRRValue}` : 'N/A';

  // Calculate actual current consecutive wins from closed trades
  let currentConsecWins = 0;
  for (const trade of closedTrades) {
    if (trade.outcome === 'TP1_HIT' || trade.outcome === 'TP2_HIT') {
      currentConsecWins++;
    } else {
      break;
    }
  }

  // Calculate actual max drawdown from closed trades
  let peakPips = 0;
  let runningPips = 0;
  let maxDrawdownPips = 0;
  for (const trade of [...closedTrades].reverse()) {
    runningPips += trade.pipsGained || 0;
    if (runningPips > peakPips) peakPips = runningPips;
    const dd = peakPips - runningPips;
    if (dd > maxDrawdownPips) maxDrawdownPips = dd;
  }
  const maxDrawdownPercent = peakPips > 0 ? Number(((maxDrawdownPips / peakPips) * 100).toFixed(1)) : 0;

  return {
    totalSignals: AUDIT_LEDGER.length,
    closedSignals: closedTrades.length,
    activeSignals: activeCount,
    tp1Hits,
    tp2Hits,
    slHits, // شحال من SL ضرب بالتدقيق
    beHits,
    winRate, // نسبة النجاح الإجمالية الحقيقية من السجل
    profitFactor,
    totalPipsGained, // مجموع النقاط الصافية المحققة فعلياً
    averageRiskReward,
    consecutiveWins: currentConsecWins,
    maxDrawdownPercent,
    recentAuditHistory: AUDIT_LEDGER,
    assetBreakdown,
    circuitBreaker: getConsecutiveLossState(),
    lastUpdated: new Date().toLocaleTimeString('ar-MA', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  };
}

/**
 * Checks consecutive stop loss outcomes in the ledger to enforce real-world prop firm circuit breaker.
 * If 2 or more recent closed trades hit SL consecutively, it halts automatic execution to prevent drawdown.
 */
let manualCircuitBreakerResetTimestamp = 0;
let circuitBreakerActivatedAt = 0;

export function getConsecutiveLossState(): {
  isTriggered: boolean;
  consecutiveLossCount: number;
  reasonAr: string;
  cooldownRemainingMinutes: number;
} {
  const closed = AUDIT_LEDGER.filter(t => t.outcome !== 'ACTIVE');
  if (closed.length === 0) {
    return { isTriggered: false, consecutiveLossCount: 0, reasonAr: "", cooldownRemainingMinutes: 0 };
  }

  // Count consecutive SLs from the most recent closed trades
  let count = 0;
  for (const trade of closed) {
    if (trade.outcome === 'SL_HIT') {
      count++;
    } else {
      break; // broken by a TP or BE
    }
  }

  // If 2 or more consecutive SLs occurred
  if (count >= 2) {
    if (!circuitBreakerActivatedAt) {
      circuitBreakerActivatedAt = Date.now();
    }
    const cooldownDuration = count >= 3 ? (2 * 60 * 60 * 1000) : (60 * 60 * 1000); // 2 hours if 3 SLs, 1 hour if 2 SLs
    
    // Check manual override
    if (manualCircuitBreakerResetTimestamp > circuitBreakerActivatedAt) {
      return { isTriggered: false, consecutiveLossCount: count, reasonAr: "", cooldownRemainingMinutes: 0 };
    }

    const elapsed = Date.now() - circuitBreakerActivatedAt;
    if (elapsed > cooldownDuration) {
      return { isTriggered: false, consecutiveLossCount: count, reasonAr: "", cooldownRemainingMinutes: 0 };
    }

    const remainingMin = Math.max(1, Math.round((cooldownDuration - elapsed) / 60000));
    return {
      isTriggered: true,
      consecutiveLossCount: count,
      reasonAr: `🛡️ تفعيل نظام حماية رأس المال التلقائي (Loss Circuit Breaker): تم رصد ${count} صفقات متتالية ضربت الوقف. تم تعليق الإشارات مؤقتاً لحماية الحساب من تذبذب السوق.`,
      cooldownRemainingMinutes: remainingMin
    };
  } else {
    // Reset activation when not >= 2
    circuitBreakerActivatedAt = 0;
  }

  return { isTriggered: false, consecutiveLossCount: count, reasonAr: "", cooldownRemainingMinutes: 0 };
}

export function resetCircuitBreakerManually() {
  manualCircuitBreakerResetTimestamp = Date.now();
}

/**
 * Formats a clean, ultra-precise human pro trader performance report for Telegram
 */
export function formatTelegramPerformanceReport(): string {
  const stats = getSignalsPerformanceStats();

  if (stats.closedSignals === 0) {
    return `📊 <b>سجل الشفافية والأداء المباشر (Audit Stats 100% Real)</b>

🔄 <b>تمت تصفية العداد لبدء الحساب من الصفر (Fresh Start):</b>
🎯 <b>نسبة النجاح (Win Rate):</b> <b>0% (في انتظار حسم أول صفقة مؤكدة)</b>
🏆 <b>الأهداف المحققة (TP1 & TP2):</b> <b>0</b>
🛑 <b>الستوب لوس (SL Hits):</b> <b>0</b>
💰 <b>صافي النقاط (Net Pips):</b> <b>0 Pips</b>

🛡️ <b>منهجية أنجح متداول (Human Pro Discipline):</b>
• الحساب كيبدا من 0 مع الصفقات الحية الجديدة اللي غاتخرج من دابا لفوق.
• كل صفقة A+ كتسجل لحظياً: كيتحدد دخولها، هدفها الأول (TP1)، هدفها الثاني (TP2)، وستوب لوس دقيق.
• بمجرد ما تضرب الهدف أو الستوب، نسبة الـ Win Rate وعدد الـ SL غيتحسبو قدامك بدقة 100%.
🕒 <i>آخر تدقيق لحظي: ${stats.lastUpdated}</i>`;
  }

  const pipsPrefix = stats.totalPipsGained > 0 ? "+" : "";
  return `📊 <b>سجل الشفافية والأداء المباشر (Audit Stats 100% Real)</b>

🎯 <b>نسبة النجاح (Win Rate):</b> <b>${stats.winRate}%</b>
🏆 <b>الأهداف المحققة (TP1 & TP2):</b> <b>${stats.tp1Hits + stats.tp2Hits} صفقة رابحة</b>
🛑 <b>الستوب لوس (SL Hits):</b> <b>${stats.slHits} صفقات فقط</b>
💰 <b>صافي النقاط (Net Pips):</b> <b>${pipsPrefix}${stats.totalPipsGained.toLocaleString()} Pips</b>
⚖️ <b>معامل الربحية (Profit Factor):</b> <b>${stats.profitFactor}x</b>
📐 <b>متوسط العائد للمخاطرة (R:R):</b> <b>${stats.averageRiskReward}</b>

🛡️ <b>منهجية أنجح متداول (Human Pro Discipline):</b>
• جودة الصفقات قبل العدد (صفقة A+ واحدة مؤكدة تغني عن 10 صفقات عشوائية).
• احترام 1% كحد أقصى للمخاطرة لكل صفقة.
• تأمين فوري ونقل الستوب للدخول (Breakeven) عند تحقيق TP1.
🕒 <i>آخر تدقيق لحظي: ${stats.lastUpdated}</i>`;
}

