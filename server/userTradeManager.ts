/**
 * Personalized User Active Trade Management Engine ("kola user o dyalo")
 * 
 * 1. When a trade signal is dispatched, users can react to the Telegram message
 *    (emoji reaction like 👍, 🎯, 🔥, 🚀 or clicking the inline button "🎯 دخلت الصفقة").
 * 2. The bot automatically binds that specific trade to that user's chat_id.
 * 3. The bot continuously monitors the price of that trade and sends direct,
 *    personalized updates & actionable instructions exclusively to that user:
 *    - Alert at 50% towards TP1
 *    - TP1 hit instruction: Book 50% profits + Move SL to Breakeven
 *    - Breakeven confirmation alert
 *    - Advance to TP2 progress update
 *    - TP2 final profit booking celebration
 *    - Risk caution if price tests invalidation boundary
 * 4. User can check /mytrades or interact via Telegram buttons anytime.
 */

import { MarketAsset, AISignal } from "../src/types";
import { getLocalDatabase, saveLocalDatabase } from "./localDb";
import { sendTelegramMessage, getTelegramConfig } from "./telegram";
import { getUserSubscriberProfile } from "./activation";

export interface UserTrackedTrade {
  id: string;
  chatId: string;
  userName: string;
  signalId: string;
  symbol: string;
  signalType: "BUY" | "SELL";
  entryPrice: number;
  currentPrice: number;
  joinedAtPrice: number;
  ticksRecorded: number;
  stopLoss: number;
  originalStopLoss: number;
  target1: number;
  target2: number;
  riskReward: string;
  timeframe: string;
  confidence: number;
  pipsSize: number;
  decimals: number;
  joinedAt: number;
  status: "ACTIVE" | "BE_SECURED" | "TP1_HIT" | "TP2_HIT" | "SL_HIT" | "MANUALLY_CLOSED";
  isBreakeven: boolean;
  partialProfitTaken: boolean;
  unrealizedPips: number;
  lastNotifiedStage: "ENTRY" | "HALFWAY_TP1" | "TP1" | "BE_REMINDER" | "HALFWAY_TP2" | "TP2" | "SL_WARNING" | "SL";
  lastActionRecommendedAr: string;
  lastUpdated: number;
  consecutiveTp1Ticks?: number;
  consecutiveTp2Ticks?: number;
  consecutiveSlTicks?: number;
}

export interface UserPerformanceStatsSummary {
  chatId: string;
  userName: string;
  capital: number;
  riskPercent: number;
  totalJoinedTrades: number;
  activeTradesCount: number;
  closedTradesCount: number;
  
  day: {
    total: number;
    completed: number;
    won: number;
    lost: number;
    breakeven: number;
    winRate: number;
    pips: number;
    gainUsd: number;
  };
  week: {
    total: number;
    completed: number;
    won: number;
    lost: number;
    breakeven: number;
    winRate: number;
    pips: number;
    gainUsd: number;
  };
  total: {
    total: number;
    completed: number;
    won: number;
    lost: number;
    breakeven: number;
    winRate: number;
    pips: number;
    gainUsd: number;
  };
  trades: UserTrackedTrade[];
}

// In-memory registry of actively tracked user trades
// Key: `${chatId}_${signalId}`
const userTradesMap = new Map<string, UserTrackedTrade>();

// Restore user trades from local database on initialization
function initUserTradesFromDb() {
  try {
    const db = getLocalDatabase();
    if (db.userTrades && typeof db.userTrades === "object") {
      for (const [k, v] of Object.entries(db.userTrades)) {
        if (v && (v as any).chatId && (v as any).signalId) {
          const trade = v as UserTrackedTrade;
          if (!trade.symbol || (!trade.symbol.includes("XAU") && trade.symbol !== "GOLD")) {
            continue; // Skip non-gold trades
          }
          userTradesMap.set(`${trade.chatId}_${trade.signalId}`, trade);
        }
      }
    }
  } catch (err) {
    console.error("[UserTradeManager] Error restoring trades from localDb:", err);
  }
}
initUserTradesFromDb();

function persistUserTrade(trade: UserTrackedTrade) {
  try {
    saveLocalDatabase((db) => {
      if (!db.userTrades) db.userTrades = {};
      db.userTrades[trade.id] = trade;
    });
  } catch (err) {
    console.error("[UserTradeManager] Error saving trade to localDb:", err);
  }
}

// Mapping of Telegram messageId to signalId to track emoji reactions
// Key: `${chatId}_${messageId}` -> signalId
const chatMessageToSignalMap = new Map<string, string>();
const globalMessageToSignalMap = new Map<number, string>();

/**
 * Associates a Telegram dispatched message ID with a signal ID
 */
export function registerSignalMessageId(chatId: string, messageId: number, signalId: string) {
  chatMessageToSignalMap.set(`${chatId}_${messageId}`, signalId);
  globalMessageToSignalMap.set(messageId, signalId);
}

/**
 * Gets the signal ID associated with a message
 */
export function getSignalIdByMessage(chatId: string, messageId: number): string | undefined {
  return chatMessageToSignalMap.get(`${chatId}_${messageId}`) || globalMessageToSignalMap.get(messageId);
}

/**
 * Calculates accurate statistics exclusively for trades a user has actually joined
 */
export function getUserPersonalStats(chatId: string): UserPerformanceStatsSummary {
  const profile = getUserSubscriberProfile(chatId);
  const allTrades = Array.from(userTradesMap.values()).filter(t => t.chatId === chatId);

  const now = new Date();
  const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayOfWeek = now.getDay();
  const distanceToMonday = (dayOfWeek + 6) % 7;
  const startOfWeek = new Date(now.getFullYear(), now.getMonth(), now.getDate() - distanceToMonday).getTime();

  function calculateWindowStats(windowTrades: UserTrackedTrade[]) {
    let won = 0;
    let lost = 0;
    let breakeven = 0;
    let pips = 0;
    let gainUsd = 0;

    for (const t of windowTrades) {
      const riskUsd = (profile.capital * profile.riskPercent) / 100;
      const slDist = Math.abs(t.entryPrice - t.originalStopLoss);

      if (t.status === "TP1_HIT" || t.status === "TP2_HIT") {
        won++;
        const target = t.status === "TP2_HIT" ? t.target2 : t.target1;
        const p = Math.round(Math.abs(target - t.entryPrice) / t.pipsSize);
        pips += p;
        const gainRatio = slDist > 0 ? Math.abs(target - t.entryPrice) / slDist : 2.0;
        gainUsd += riskUsd * gainRatio;
      } else if (t.status === "SL_HIT" || t.status === "BE_SECURED") {
        if (t.isBreakeven || t.status === "BE_SECURED") {
          breakeven++;
        } else {
          lost++;
          const p = Math.round(Math.abs(t.entryPrice - t.originalStopLoss) / t.pipsSize);
          pips -= p;
          gainUsd -= riskUsd;
        }
      } else if (t.status === "MANUALLY_CLOSED") {
        if (t.unrealizedPips > 0) {
          won++;
          pips += t.unrealizedPips;
          gainUsd += riskUsd * 0.8;
        } else if (t.unrealizedPips === 0) {
          breakeven++;
        } else {
          lost++;
          pips += t.unrealizedPips;
          gainUsd -= riskUsd * 0.8;
        }
      }
    }

    const completed = won + lost + breakeven;
    const decisive = won + lost;
    const winRate = decisive > 0 ? Math.round((won / decisive) * 100) : (won > 0 ? 100 : 0);

    return {
      total: windowTrades.length,
      completed,
      won,
      lost,
      breakeven,
      winRate,
      pips,
      gainUsd: Number(gainUsd.toFixed(2))
    };
  }

  const dayTrades = allTrades.filter(t => t.joinedAt >= startOfDay);
  const weekTrades = allTrades.filter(t => t.joinedAt >= startOfWeek);

  const day = calculateWindowStats(dayTrades);
  const week = calculateWindowStats(weekTrades);
  const total = calculateWindowStats(allTrades);

  const activeTradesCount = allTrades.filter(t => t.status === "ACTIVE" || t.status === "BE_SECURED").length;

  return {
    chatId,
    userName: profile.firstName || profile.username || "المتداول",
    capital: profile.capital,
    riskPercent: profile.riskPercent,
    totalJoinedTrades: allTrades.length,
    activeTradesCount,
    closedTradesCount: total.completed,
    day,
    week,
    total,
    trades: allTrades.sort((a, b) => b.joinedAt - a.joinedAt),
  };
}

/**
 * Returns performance stats for all subscribers who interacted with signals
 */
export function getAllUsersStats(): UserPerformanceStatsSummary[] {
  const db = getLocalDatabase();
  const chatIds = new Set<string>();

  if (db.chatSubscribers) {
    for (const id of Object.keys(db.chatSubscribers)) {
      chatIds.add(id);
    }
  }
  for (const t of userTradesMap.values()) {
    chatIds.add(t.chatId);
  }

  const result: UserPerformanceStatsSummary[] = [];
  for (const chatId of chatIds) {
    result.push(getUserPersonalStats(chatId));
  }

  return result.sort((a, b) => b.totalJoinedTrades - a.totalJoinedTrades || b.total.pips - a.total.pips);
}

/**
 * Formats a clean personal performance report for a user on Telegram (/stats)
 */
export function formatUserPersonalStatsMessage(chatId: string, userName: string): { text: string; replyMarkup: any } {
  const stats = getUserPersonalStats(chatId);

  if (stats.totalJoinedTrades === 0) {
    const emptyText = `📊 <b>إحصائياتك الشخصية (${stats.userName}):</b>
━━━━━━━━━━━━━━━━━━
❌ <b>لم تسجل دخولك في أي صفقة بعد (0 صفقات).</b>

💡 <i>يتم احتساب الإحصائيات فقط للصفقات التي قمت بالدخول إليها بالضغط على زر [ 🎯 دخلت الصفقة ] المرفق مع كل إشارة مؤكدة!</i>

💰 رأس مالك المسجل: <code>${stats.capital.toLocaleString()}$</code> (مخاطرة: <code>${stats.riskPercent}%</code>)`;

    const replyMarkup = {
      inline_keyboard: [
        [
          { text: "🧮 لوت محفظتي", callback_data: "calc_latest_lot" },
          { text: "⚙️ ضبط رأس المال والمخاطرة", callback_data: "my_profile" }
        ]
      ]
    };
    return { text: emptyText, replyMarkup };
  }

  const daySign = stats.day.pips >= 0 ? "+" : "";
  const weekSign = stats.week.pips >= 0 ? "+" : "";
  const totalSign = stats.total.pips >= 0 ? "+" : "";

  const text = `📊 <b>إحصائيات تداولك الشخصية (${stats.userName}):</b>
━━━━━━━━━━━━━━━━━━
🎯 <i>خاصة بالصفقات التي دخلت إليها فقط (${stats.totalJoinedTrades} صفقة):</i>

📅 <b>اليوم (Today):</b>
• الصفقات: <code>${stats.day.total}</code> (✅ ${stats.day.won} | 🛑 ${stats.day.lost} | 🛡️ ${stats.day.breakeven})
• نسبة النجاح (Win Rate): <b>${stats.day.winRate}%</b>
• أرباح النقاط: <b>${daySign}${stats.day.pips} Pips</b>

📆 <b>هذا الأسبوع (This Week):</b>
• الصفقات: <code>${stats.week.total}</code> (✅ ${stats.week.won} | 🛑 ${stats.week.lost})
• نسبة النجاح (Win Rate): <b>${stats.week.winRate}%</b>
• أرباح النقاط: <b>${weekSign}${stats.week.pips} Pips</b>

🏆 <b>الإجمالي الكلي (All-Time):</b>
• الصفقات المنفذة: <code>${stats.total.total}</code>
• الرابحة: <b>${stats.total.won} ✅</b> | الخاسرة: <b>${stats.total.lost} 🛑</b> | التعادل: <b>${stats.total.breakeven} 🛡️</b>
• نسبة النجاح الإجمالية: <b>${stats.total.winRate}%</b>
• صافي النقاط: <b>${totalSign}${stats.total.pips} Pips 📈</b>
• الصفقات النشطة حالياً: <code>${stats.activeTradesCount}</code>

💰 <b>رأس المال:</b> <code>${stats.capital.toLocaleString()}$</code> (المخاطرة: <code>${stats.riskPercent}%</code>)`;

  const replyMarkup = {
    inline_keyboard: [
      [
        { text: "📋 صفقاتي النشطة", callback_data: "my_trades" },
        { text: "🧮 لوت محفظتي", callback_data: "calc_latest_lot" }
      ],
      [
        { text: "⚙️ ضبط رأس المال والمخاطرة", callback_data: "my_profile" }
      ]
    ]
  };

  return { text, replyMarkup };
}

/**
 * Registers a user joining / entering a specific trade setup
 */
export async function trackUserTrade(
  chatId: string,
  userName: string,
  signal: {
    id: string;
    symbol: string;
    signalType: "BUY" | "SELL";
    entryPrice: number;
    stopLoss: number;
    target1: number;
    target2: number;
    riskReward?: string;
    timeframe?: string;
    confidence?: number;
  },
  customEntryPrice?: number,
  currentLivePrice?: number
): Promise<{ success: boolean; trade: UserTrackedTrade; isNew: boolean }> {
  const key = `${chatId}_${signal.id}`;
  const isGold = signal.symbol.includes("XAU") || signal.symbol.includes("Gold");
  const isCrypto = signal.symbol.includes("BTC") || signal.symbol.includes("ETH");
  const isForex = signal.symbol.includes("EUR") || signal.symbol.includes("GBP");
  
  const decimals = isForex ? 4 : isGold ? 2 : isCrypto ? 0 : 2;
  const pipsSize = isForex ? 0.0001 : isGold ? 0.1 : isCrypto ? 1.0 : 0.01;
  const entry = customEntryPrice && customEntryPrice > 0 ? customEntryPrice : signal.entryPrice;
  const livePrice = currentLivePrice && currentLivePrice > 0 ? currentLivePrice : entry;

  const isExisting = userTradesMap.has(key);
  const now = Date.now();

  const isBuy = signal.signalType === "BUY";
  const isAlreadyPastTp1 = isBuy ? livePrice >= signal.target1 : livePrice <= signal.target1;

  const trade: UserTrackedTrade = isExisting
    ? userTradesMap.get(key)!
    : {
        id: `tr-${chatId}-${signal.id}`,
        chatId,
        userName: userName || "المتداول",
        signalId: signal.id,
        symbol: signal.symbol,
        signalType: signal.signalType,
        entryPrice: Number(entry.toFixed(decimals)),
        currentPrice: Number(livePrice.toFixed(decimals)),
        joinedAtPrice: Number(livePrice.toFixed(decimals)),
        ticksRecorded: 0,
        stopLoss: signal.stopLoss,
        originalStopLoss: signal.stopLoss,
        target1: signal.target1,
        target2: signal.target2,
        riskReward: signal.riskReward || "1:3.2",
        timeframe: signal.timeframe || "15M",
        confidence: signal.confidence || 90,
        pipsSize,
        decimals,
        joinedAt: now,
        status: "ACTIVE",
        isBreakeven: false,
        partialProfitTaken: false,
        unrealizedPips: 0,
        lastNotifiedStage: isAlreadyPastTp1 ? "TP1" : "ENTRY",
        lastActionRecommendedAr: "مراقبة مسار الصفقة والالتزام الصارم بـ 1% مخاطرة",
        lastUpdated: now
      };

  userTradesMap.set(key, trade);
  persistUserTrade(trade);

  const directionText = signal.signalType === "BUY" ? "BUY 🟢" : "SELL 🔴";

  const welcomeMsg = `🎯 <b>متابعة — ${trade.symbol} (${directionText})</b>

📍 <b>Entry:</b> <code>${trade.entryPrice}</code>
🛑 <b>SL:</b> <code>${trade.stopLoss}</code>
🎯 <b>TP1:</b> <code>${trade.target1}</code>
🎯 <b>TP2:</b> <code>${trade.target2}</code>`;

  const inlineKeyboard = {
    inline_keyboard: [
      [
        { text: "🛡️ تأمين إلى الدخول (BE)", callback_data: `be_${trade.id}` },
        { text: "🛑 إغلاق يدوي للصفقة", callback_data: `close_${trade.id}` }
      ],
      [
        { text: "📊 إحصائياتي الشخصية", callback_data: "my_stats" },
        { text: "📋 صفقاتي النشطة", callback_data: "my_trades" }
      ]
    ]
  };

  await sendTelegramMessage(welcomeMsg, { chatId, replyMarkup: inlineKeyboard });

  return { success: true, trade, isNew: !isExisting };
}

/**
 * Secures a user's trade to Breakeven (Stop Loss moved to Entry Price)
 */
export async function secureUserTradeBreakeven(chatId: string, tradeId: string): Promise<{ success: boolean; message: string }> {
  let targetTrade: UserTrackedTrade | undefined;
  for (const t of userTradesMap.values()) {
    if (t.id === tradeId || (t.chatId === chatId && t.id.includes(tradeId))) {
      targetTrade = t;
      break;
    }
  }

  if (!targetTrade) {
    return { success: false, message: "لم يتم العثور على الصفقة المطلوبة." };
  }

  targetTrade.isBreakeven = true;
  targetTrade.stopLoss = targetTrade.entryPrice;
  targetTrade.status = "BE_SECURED";
  targetTrade.lastActionRecommendedAr = "الصفقة مؤمنة تماماً عند نقطة الدخول (Risk-Free)";
  targetTrade.lastUpdated = Date.now();
  persistUserTrade(targetTrade);

  const beMsg = `🛡️ <b>تم تأمين صفقتك بنجاح يا ${targetTrade.userName}!</b>

📊 <b>الرمز:</b> <b>${targetTrade.symbol}</b>
🔒 <b>وقف الخسارة الجديد:</b> <code>${targetTrade.entryPrice}</code> (سعر الدخول)
🎉 <b>أنت الآن في صفقة خالية تماماً من أي مخاطرة (Risk-Free Trade)!</b>

دع الأرباح تمتد نحو الهدف الثاني 🎯 <code>${targetTrade.target2}</code> بأمان واطمئنان.`;

  await sendTelegramMessage(beMsg, { chatId });
  return { success: true, message: `تم تأمين صفقة ${targetTrade.symbol} عند نقطة الدخول بنجاح.` };
}

/**
 * Closes a user's trade manually
 */
export async function closeUserTradeManually(chatId: string, tradeId: string): Promise<{ success: boolean; message: string }> {
  let targetTrade: UserTrackedTrade | undefined;
  for (const t of userTradesMap.values()) {
    if (t.id === tradeId || (t.chatId === chatId && t.id.includes(tradeId))) {
      targetTrade = t;
      break;
    }
  }

  if (!targetTrade) {
    return { success: false, message: "لم يتم العثور على الصفقة." };
  }

  targetTrade.status = "MANUALLY_CLOSED";
  targetTrade.lastUpdated = Date.now();
  persistUserTrade(targetTrade);

  const pips = targetTrade.unrealizedPips;
  const pipsSign = pips >= 0 ? `+${pips} Pips 🟢` : `${pips} Pips 🔴`;

  const closeMsg = `🛑 <b>تم إغلاق الصفقة يدوياً</b>

📊 <b>الرمز:</b> ${targetTrade.symbol}
💰 <b>النتيجة النهائية:</b> <b>${pipsSign}</b>
سعر الإغلاق: <code>${targetTrade.currentPrice}</code>

<i>تم تسجيل النتيجة بنجاح واحتسابها في إحصائياتك الشخصية.</i>`;

  await sendTelegramMessage(closeMsg, { chatId });
  return { success: true, message: `تم إغلاق صفقة ${targetTrade.symbol} بنتيجة ${pipsSign}` };
}

/**
 * Returns formatted text overview of all active trades for a given user
 */
export function formatUserActiveTradesTelegram(chatId: string): { text: string; replyMarkup: any } {
  const userTrades = Array.from(userTradesMap.values()).filter(
    t => t.chatId === chatId && (t.status === "ACTIVE" || t.status === "BE_SECURED" || t.status === "TP1_HIT")
  );

  if (userTrades.length === 0) {
    return {
      text: `📋 <b>صفقاتك النشطة:</b>\n\nلا توجد صفقات مفتوحة قيد المتابعة حالياً.\n\n💡 <i>عندما تصلك أي صفقة جديدة في البوت، اضغط على زر [ 🎯 دخلت الصفقة ] أو تفاعل معها، وسيبدأ البوت بمتابعتها معك خطوة بخطوة!</i>`,
      replyMarkup: undefined
    };
  }

  let text = `📋 <b>صفقاتك النشطة المتابعة شخصياً (${userTrades.length}):</b>\n\n`;
  const keyboardButtons: any[] = [];

  for (const t of userTrades) {
    const isBuy = t.signalType === "BUY";
    const dir = isBuy ? "BUY 🟢" : "SELL 🔴";
    const pipsText = t.unrealizedPips >= 0 ? `+${t.unrealizedPips} Pips 📈` : `${t.unrealizedPips} Pips 📉`;
    const beStatus = t.isBreakeven ? "🛡️ مؤمنة (BE)" : "⏳ قيد المراقبة";

    text += `🔸 <b>${t.symbol} — ${dir}</b>
• الدخول: <code>${t.entryPrice}</code> | الحالي: <code>${t.currentPrice}</code>
• النتيجة: <b>${pipsText}</b> | الحالة: <b>${beStatus}</b>
• الأهداف: TP1 <code>${t.target1}</code> | TP2 <code>${t.target2}</code>
• التوجيه: <i>${t.lastActionRecommendedAr}</i>\n\n`;

    if (!t.isBreakeven) {
      keyboardButtons.push([
        { text: `🛡️ تأمين ${t.symbol} إلى الدخول`, callback_data: `be_${t.id}` },
        { text: `🛑 إغلاق ${t.symbol}`, callback_data: `close_${t.id}` }
      ]);
    } else {
      keyboardButtons.push([
        { text: `🛑 إغلاق ${t.symbol}`, callback_data: `close_${t.id}` }
      ]);
    }
  }

  return {
    text,
    replyMarkup: { inline_keyboard: keyboardButtons }
  };
}

/**
 * Checks all active user trades against live market prices and sends individual milestones & instructions
 * Triggered every second in sync with price updates
 */
export async function checkUserTrackedTradesAgainstLivePrices(assetsList: MarketAsset[]) {
  if (userTradesMap.size === 0) return;

  const assetMap = new Map<string, number>();
  for (const a of assetsList) {
    if (a.price && a.price > 0) {
      assetMap.set(a.symbol, a.price);
    }
  }

  for (const trade of userTradesMap.values()) {
    if (trade.status === "TP2_HIT" || trade.status === "SL_HIT" || trade.status === "MANUALLY_CLOSED") {
      continue;
    }

    // Auto-expire trades older than 12 hours
    if (Date.now() - trade.joinedAt > 12 * 3600 * 1000) {
      trade.status = "MANUALLY_CLOSED";
      persistUserTrade(trade);
      continue;
    }

    const currentPrice = assetMap.get(trade.symbol);
    if (!currentPrice || currentPrice <= 0) continue;

    trade.currentPrice = currentPrice;
    trade.lastUpdated = Date.now();

    trade.ticksRecorded = (trade.ticksRecorded || 0) + 1;

    const isBuy = trade.signalType === "BUY";
    const rawDiff = isBuy ? currentPrice - trade.entryPrice : trade.entryPrice - currentPrice;
    trade.unrealizedPips = Math.round(rawDiff / trade.pipsSize);

    const totalTp1Diff = Math.abs(trade.target1 - trade.entryPrice);
    const totalSlDiff = Math.abs(trade.entryPrice - trade.originalStopLoss);

    // ----------------------------------------------------
    // MILESTONE 1: Halfway to TP1 (~50% of distance with solid profit)
    // ----------------------------------------------------
    if (trade.lastNotifiedStage === "ENTRY" && totalTp1Diff > 0) {
      const reachedRatio = rawDiff / totalTp1Diff;
      if (reachedRatio >= 0.50 && trade.unrealizedPips >= 12 && trade.ticksRecorded >= 2) {
        trade.lastNotifiedStage = "HALFWAY_TP1";
        trade.lastActionRecommendedAr = "السعر في منتصف المسار نحو الهدف الأول. الأرباح مؤمنة بحساب 1%.";
        persistUserTrade(trade);
      }
    }

    // ----------------------------------------------------
    // MILESTONE 2: TP1 Reached (Hit Target 1)
    // ----------------------------------------------------
    const validTp1Start = isBuy 
      ? trade.joinedAtPrice < trade.target1 
      : trade.joinedAtPrice > trade.target1;
    const isTp1Hit = isBuy ? currentPrice >= trade.target1 : currentPrice <= trade.target1;

    if (isTp1Hit) {
      trade.consecutiveTp1Ticks = (trade.consecutiveTp1Ticks || 0) + 1;
    } else {
      trade.consecutiveTp1Ticks = 0;
    }

    const timeSinceJoinSec = (Date.now() - trade.joinedAt) / 1000;

    if (validTp1Start && isTp1Hit && (trade.lastNotifiedStage === "ENTRY" || trade.lastNotifiedStage === "HALFWAY_TP1") && (trade.consecutiveTp1Ticks || 0) >= 3 && timeSinceJoinSec >= 15) {
      trade.lastNotifiedStage = "TP1";
      trade.status = "TP1_HIT";
      trade.partialProfitTaken = true;
      trade.isBreakeven = true;
      trade.stopLoss = trade.entryPrice;
      trade.lastActionRecommendedAr = "تم تحقيق TP1 بنجاح! حجز 50% أرباح وتأمين الوقف على الدخول (BE).";
      persistUserTrade(trade);
    }

    // ----------------------------------------------------
    // MILESTONE 3: Halfway between TP1 and TP2 (~75% overall)
    // ----------------------------------------------------
    const totalTp2Diff = Math.abs(trade.target2 - trade.entryPrice);
    if ((trade.lastNotifiedStage === "TP1" || trade.lastNotifiedStage === "BE_REMINDER") && totalTp2Diff > 0) {
      const overallRatio = rawDiff / totalTp2Diff;
      if (overallRatio >= 0.75) {
        trade.lastNotifiedStage = "HALFWAY_TP2";
        trade.lastActionRecommendedAr = "السعر يقترب من الهدف الثاني TP2.";
        persistUserTrade(trade);
      }
    }

    // ----------------------------------------------------
    // MILESTONE 4: TP2 Hit (Target 2 Fully Smashed)
    // ----------------------------------------------------
    const isTp2Hit = isBuy ? currentPrice >= trade.target2 : currentPrice <= trade.target2;
    if (isTp2Hit) {
      trade.consecutiveTp2Ticks = (trade.consecutiveTp2Ticks || 0) + 1;
    } else {
      trade.consecutiveTp2Ticks = 0;
    }

    if (isTp2Hit && (trade.status === "TP1_HIT" || trade.isBreakeven) && trade.lastNotifiedStage !== "TP2" && (trade.consecutiveTp2Ticks || 0) >= 3) {
      trade.lastNotifiedStage = "TP2";
      trade.status = "TP2_HIT";
      trade.lastActionRecommendedAr = "تم تحقيق كامل الأهداف TP2 بنجاح تام وفق الخطة!";
      persistUserTrade(trade);
    }

    // ----------------------------------------------------
    // MILESTONE 5: SL Warning (Internal monitoring without spamming)
    // ----------------------------------------------------
    if (!trade.isBreakeven && trade.lastNotifiedStage === "ENTRY" && totalSlDiff > 0) {
      const drawdownDistance = isBuy ? trade.entryPrice - currentPrice : currentPrice - trade.entryPrice;
      if (drawdownDistance > 0 && drawdownDistance / totalSlDiff >= 0.75) {
        trade.lastNotifiedStage = "SL_WARNING";
        trade.lastActionRecommendedAr = "السعر يختبر منطقة الوقف مع حماية صارمة لرأس المال.";
      }
    }

    // ----------------------------------------------------
    // MILESTONE 6: Stop Loss Hit or Breakeven Exit
    // ----------------------------------------------------
    const isSlHit = isBuy ? currentPrice <= trade.stopLoss : currentPrice >= trade.stopLoss;
    if (isSlHit) {
      trade.consecutiveSlTicks = (trade.consecutiveSlTicks || 0) + 1;
    } else {
      trade.consecutiveSlTicks = 0;
    }

    if (isSlHit && trade.lastNotifiedStage !== "SL" && (trade.consecutiveSlTicks || 0) >= 3 && timeSinceJoinSec >= 15) {
      trade.lastNotifiedStage = "SL";
      trade.status = trade.isBreakeven ? "BE_SECURED" : "SL_HIT";
      if (trade.isBreakeven) {
        trade.unrealizedPips = 0;
        trade.lastActionRecommendedAr = "خروج بدون أي خسارة (Breakeven 0$) بعد حجز أرباح TP1.";
      } else {
        trade.lastActionRecommendedAr = "تم الخروج عند الوقف بحماية 99% من رأس المال وفق قاعدة 1% مخاطرة.";
      }
      persistUserTrade(trade);
    }
  }
}

/**
 * Returns all active user tracked trades (for Web API)
 */
export function getAllUserTrackedTrades(): UserTrackedTrade[] {
  return Array.from(userTradesMap.values());
}

/**
 * Finds recent dispatched signal or active signal by id or latest
 */
export function findSignalById(signalId: string, pool: AISignal[]): AISignal | undefined {
  return pool.find(s => s.id === signalId);
}

/**
 * Resets all user trades completely
 */
export function resetAllUserTrades() {
  userTradesMap.clear();
  saveLocalDatabase((d) => {
    d.userTrades = {};
  });
  console.log("[UserTradeManager] All user trades have been purged.");
}
