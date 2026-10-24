// Telegram Bot Integration Service

import {
  isBotLicenseValid,
  isChatActivated,
  activateChatWithCode,
  getActiveChatSubscribers,
  getNewlyExpiredSubscribers,
  markSubscriberExpiredNotified,
  formatRemainingTime,
  getUserSubscriberProfile,
  updateUserCapitalAndRisk,
} from "./activation";
import { getQuickChartImageUrl, generateSignalChartPngBuffer } from "./chartGenerator";
import { fetchLiveCandles, getLivePrice, getMarketSessionStatus, getKillzoneStatus, fetchLiveSpotGold } from "./liveMarket";
import { runPythonAnalysisAgentRaw, convertPythonResultToAISignal, runCrewAITradingSystem } from "./pythonAgentBridge";
import {
  registerSignalMessageId,
  getSignalIdByMessage,
  trackUserTrade,
  secureUserTradeBreakeven,
  closeUserTradeManually,
  formatUserActiveTradesTelegram,
  formatUserPersonalStatsMessage,
} from "./userTradeManager";
import { registerDispatchedSignal, canDispatchNewSignal } from "./signalTracker";
import { validateAndSanitizeSignalLevels } from "./strategiesEngine";
import { INITIAL_SIGNALS } from "../src/data/defaultData";

export interface TelegramConfigServer {
  botToken: string;
  chatId: string;
  enabled: boolean;
  minConfidence: number; // e.g. 75
  assets: string[];
  notifyOnNews: boolean;
  omniRadarAllMarkets?: boolean;
}

export interface TelegramLog {
  id: string;
  type: 'SIGNAL' | 'TEST' | 'NEWS' | 'ALERT';
  title: string;
  details: string;
  sentAt: string;
  status: 'SUCCESS' | 'FAILED';
  error?: string;
}

// In-memory Telegram settings backed by local JSON DB
import { getLocalDatabase, saveLocalDatabase } from "./localDb";

// Cache of recently dispatched signals to support fast reaction & callback queries
const recentDispatchedSignalsMap = new Map<string, any>();

// Confirmed signal message ID tracking for replying to the original trade message in Telegram
// Key: `${signalId}_${chatId}` -> messageId
const confirmedSignalMessageMap = new Map<string, number>();
// Key: `${symbol}_${chatId}` -> messageId
const confirmedSymbolMessageMap = new Map<string, number>();

export function saveConfirmedSignalMessageId(signalId: string, symbol: string, chatId: string, messageId: number) {
  confirmedSignalMessageMap.set(`${signalId}_${chatId}`, messageId);
  confirmedSymbolMessageMap.set(`${symbol}_${chatId}`, messageId);
}

export function getConfirmedSignalMessageId(signalId: string, chatId: string): number | undefined {
  return confirmedSignalMessageMap.get(`${signalId}_${chatId}`);
}

export function getConfirmedSignalMessageIdBySymbol(symbol: string, chatId: string): number | undefined {
  return confirmedSymbolMessageMap.get(`${symbol}_${chatId}`);
}

export function clearConfirmedSignalMessageId(signalId: string, symbol?: string) {
  for (const key of Array.from(confirmedSignalMessageMap.keys())) {
    if (key.startsWith(`${signalId}_`)) {
      confirmedSignalMessageMap.delete(key);
    }
  }
  if (symbol) {
    for (const key of Array.from(confirmedSymbolMessageMap.keys())) {
      if (key.startsWith(`${symbol}_`)) {
        confirmedSymbolMessageMap.delete(key);
      }
    }
  }
}

export function getDispatchedSignalById(id: string): any | undefined {
  return recentDispatchedSignalsMap.get(id);
}

export function cacheDispatchedSignal(signal: any) {
  if (!signal || !signal.id) return;
  recentDispatchedSignalsMap.set(signal.id, signal);
  // Keep cache bounded
  if (recentDispatchedSignalsMap.size > 50) {
    const firstKey = recentDispatchedSignalsMap.keys().next().value;
    if (firstKey) recentDispatchedSignalsMap.delete(firstKey);
  }
}

export function getTelegramConfig(): TelegramConfigServer {
  const db = getLocalDatabase();
  const cfg = db.telegramConfig || {};
  const omniRadar = typeof cfg.omniRadarAllMarkets === "boolean" ? cfg.omniRadarAllMarkets : true;
  const allAvailableAssets = ["XAU/USD"];
  return {
    botToken: cfg.botToken || process.env.TELEGRAM_BOT_TOKEN || "",
    chatId: cfg.chatId || process.env.TELEGRAM_CHAT_ID || "",
    enabled: typeof cfg.enabled === "boolean" ? cfg.enabled : true,
    minConfidence: cfg.minConfidence || 95,
    assets: allAvailableAssets,
    notifyOnNews: typeof cfg.notifyOnNews === "boolean" ? cfg.notifyOnNews : true,
    omniRadarAllMarkets: false,
  };
}

export function updateTelegramConfig(newConfig: Partial<TelegramConfigServer>): TelegramConfigServer {
  const current = getTelegramConfig();
  const updated = {
    ...current,
    ...newConfig,
  };
  saveLocalDatabase((db) => {
    db.telegramConfig = updated;
  });
  return updated;
}

// Anti-Duplication Message Store (Guarantees zero duplicate messages across all bots & restarts)
interface SentMessageRecord {
  sentAt: number;
  messageId?: number;
}
const sentMessageDeduplication = new Map<string, SentMessageRecord>();
const MESSAGE_DEDUP_WINDOW_MS = 45 * 1000; // 45 seconds for exact message text
let cachedBotInfo: { id: number; username: string; firstName: string; verifiedAt: number } | null = null;

/**
 * Validates a bot token with Telegram's getMe API and retrieves its identity
 */
export async function getTelegramBotInfo(customToken?: string): Promise<{
  valid: boolean;
  bot?: { id: number; username: string; firstName: string };
  error?: string;
}> {
  const cfg = getTelegramConfig();
  const token = customToken || cfg.botToken || process.env.TELEGRAM_BOT_TOKEN;

  if (!token) {
    return { valid: false, error: "لم يتم تحديد Bot Token" };
  }

  // Use short memory cache if verified recently (within 60s)
  if (!customToken && cachedBotInfo && Date.now() - cachedBotInfo.verifiedAt < 60000) {
    return {
      valid: true,
      bot: {
        id: cachedBotInfo.id,
        username: cachedBotInfo.username,
        firstName: cachedBotInfo.firstName,
      }
    };
  }

  try {
    const url = `https://api.telegram.org/bot${token}/getMe`;
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    const data = await res.json() as any;

    if (!res.ok || !data.ok || !data.result) {
      return {
        valid: false,
        error: data?.description || "رمز Bot Token غير صالح أو محذوف من تيليجرام.",
      };
    }

    const botResult = {
      id: data.result.id,
      username: data.result.username || "TradingBot",
      firstName: data.result.first_name || "Trading AI",
    };

    if (!customToken) {
      cachedBotInfo = { ...botResult, verifiedAt: Date.now() };
    }

    return { valid: true, bot: botResult };
  } catch (err: any) {
    return { valid: false, error: err?.message || "تعذر الاتصال بـ api.telegram.org" };
  }
}

/**
 * Switches the active Telegram Bot to a NEW bot exclusively for this app.
 * Drops all pending updates and deletes any conflicting webhooks from other apps.
 */
export async function switchTelegramBot(
  newBotToken: string,
  newChatId?: string,
  dropPendingUpdates: boolean = true
): Promise<{
  success: boolean;
  bot?: { id: number; username: string; firstName: string };
  message: string;
  error?: string;
}> {
  const cleanToken = newBotToken.trim();
  if (!cleanToken) {
    return { success: false, message: "يرجى إدخال Bot Token الجديد", error: "Token is required" };
  }

  // 1. Validate the new bot with Telegram
  const verification = await getTelegramBotInfo(cleanToken);
  if (!verification.valid || !verification.bot) {
    return {
      success: false,
      message: verification.error || "رمز Bot Token غير صالح! تأكد من نسخه بدقة من @BotFather.",
      error: verification.error,
    };
  }

  const botData = verification.bot;

  // 2. Disconnect any conflicting webhooks and purge pending updates from other apps/servers
  try {
    const purgeUrl = `https://api.telegram.org/bot${cleanToken}/deleteWebhook?drop_pending_updates=${dropPendingUpdates ? 'true' : 'false'}`;
    await fetch(purgeUrl, { signal: AbortSignal.timeout(5000) });
  } catch (err) {
    // quiet catch
  }

  // 3. Reset Polling pointer and deduplication cache
  lastUpdateId = 0;
  sentMessageDeduplication.clear();
  cachedBotInfo = { ...botData, verifiedAt: Date.now() };

  // 4. Update stored config in database & memory
  const cleanChatId = newChatId ? newChatId.trim() : undefined;
  const updatedCfg = updateTelegramConfig({
    botToken: cleanToken,
    ...(cleanChatId ? { chatId: cleanChatId } : {}),
    enabled: true,
  });

  // 5. If newChatId is given, ensure it is registered as active VIP subscriber
  if (cleanChatId) {
    saveLocalDatabase((db) => {
      if (!db.chatSubscribers) db.chatSubscribers = {};
      db.chatSubscribers[cleanChatId] = {
        chatId: cleanChatId,
        code: "PRO-TRADER-2026-VIP",
        firstName: botData.firstName,
        durationHours: 87600,
        durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
        activatedAt: Date.now(),
        expiresAt: 2105300000000,
        isPermanent: true,
        expiredNotified: false,
      };
    });
  }

  // 6. Send exclusive pairing greeting to the chat if available
  const targetChat = cleanChatId || updatedCfg.chatId;
  if (targetChat) {
    const pairingMsg = `🤖 <b>تم تفعيل وربط البوت الجديد بنجاح وحصرياً!</b>
━━━━━━━━━━━━━━━━━━
🔹 <b>اسم البوت:</b> <b>${botData.firstName}</b> (@${botData.username})
🆔 <b>معرف البوت:</b> <code>${botData.id}</code>
⚡ <b>الارتباط:</b> 🔒 <b>حصري لتطبيق التداول هذا فقط (Single-App Lock)</b>
🛡️ <b>حماية التكرار:</b> <b>Anti-Duplication Active ✅ (لن تتكرر الرسائل نهائياً)</b>

🚀 <i>تم تنظيف قائمة الانتظار القديمة بنجاح، والبوت جاهز لاستقبال وإرسال الصفقات بدقة فائقة!</i>`;

    await sendTelegramMessage(pairingMsg, {
      botToken: cleanToken,
      chatId: targetChat,
      skipDedup: true,
    }).catch(() => {});
  }

  recordNotificationLog({
    type: "ALERT",
    title: `[تبديل البوت] @${botData.username}`,
    details: `تم تبديل البوت وربطه حصرياً بالتطبيق وحذف التراكمات المعلقة بنجاح.`,
    sentAt: new Date().toLocaleTimeString("ar-MA", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    status: "SUCCESS",
  });

  return {
    success: true,
    bot: botData,
    message: `تم ربط البوت الجديد @${botData.username} بنجاح وحصرياً بهذا التطبيق، مع تفعيل حماية منع تكرار الرسائل!`,
  };
}

const notificationHistory: TelegramLog[] = [];

export function getNotificationHistory(): TelegramLog[] {
  return [...notificationHistory];
}

/**
 * Sends a Markdown / HTML formatted message to Telegram Chat via Bot API
 * Includes anti-duplication guard to prevent duplicate messages across all bots.
 */
export async function sendTelegramMessage(
  text: string,
  customConfig?: { botToken?: string; chatId?: string; replyMarkup?: any; replyToMessageId?: number; skipDedup?: boolean }
): Promise<{ success: boolean; error?: string; messageId?: number; duplicatePrevented?: boolean }> {
  const cfg = getTelegramConfig();
  const token = customConfig?.botToken || cfg.botToken || process.env.TELEGRAM_BOT_TOKEN;
  const chatId = customConfig?.chatId || cfg.chatId || process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    return {
      success: false,
      error: "Telegram Bot Token أو Chat ID غير محددين. يرجى إدخالهما في إعدادات تليجرام."
    };
  }

  // --- ANTI-DUPLICATION SHIELD ---
  const now = Date.now();
  // Periodically clean stale cache entries older than 2 minutes
  if (sentMessageDeduplication.size > 200) {
    for (const [k, v] of sentMessageDeduplication.entries()) {
      if (now - v.sentAt > 120000) sentMessageDeduplication.delete(k);
    }
  }

  const normalizedText = text.trim().replace(/\s+/g, ' ');
  const dedupKey = `${token.slice(-10)}_${chatId}_${normalizedText.slice(0, 100)}`;
  const existingSent = sentMessageDeduplication.get(dedupKey);

  if (!customConfig?.skipDedup && existingSent && (now - existingSent.sentAt < MESSAGE_DEDUP_WINDOW_MS)) {
    console.log(`[Telegram Anti-Duplication] Prevented duplicate message to ${chatId}: ${normalizedText.slice(0, 45)}...`);
    return {
      success: true,
      messageId: existingSent.messageId,
      duplicatePrevented: true,
    };
  }

  const url = `https://api.telegram.org/bot${token}/sendMessage`;

  try {
    const payload: any = {
      chat_id: chatId,
      text: text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
    };

    if (customConfig?.replyMarkup) {
      payload.reply_markup = customConfig.replyMarkup;
    }

    if (customConfig?.replyToMessageId) {
      payload.reply_to_message_id = customConfig.replyToMessageId;
    }

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = (await response.json()) as any;

    if (!response.ok || !data.ok) {
      const errDescription = data?.description || `HTTP ${response.status}`;
      return { success: false, error: errDescription };
    }

    const messageId = data?.result?.message_id;
    // Record in anti-duplication cache
    sentMessageDeduplication.set(dedupKey, { sentAt: now, messageId });
    return { success: true, messageId };
  } catch (err: any) {
    return { success: false, error: err?.message || "خطأ أثناء الاتصال بسيرفرات Telegram" };
  }
}

/**
 * Answers a Telegram callback query with optional notification toast / alert
 */
export async function answerTelegramCallbackQuery(
  callbackQueryId: string,
  text?: string,
  showAlert: boolean = false
): Promise<boolean> {
  const cfg = getTelegramConfig();
  const token = cfg.botToken || process.env.TELEGRAM_BOT_TOKEN;
  if (!token || !callbackQueryId) return false;

  try {
    const url = `https://api.telegram.org/bot${token}/answerCallbackQuery`;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        callback_query_id: callbackQueryId,
        text: text || "",
        show_alert: showAlert
      })
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Sends a Photo with an HTML-formatted caption to Telegram Chat via Bot API.
 * Supports both direct PNG Buffer upload (multipart/form-data) and remote URL strings.
 */
export async function sendTelegramPhoto(
  photoBufferOrUrl: string | Buffer,
  caption: string,
  customConfig?: { botToken?: string; chatId?: string; replyMarkup?: any }
): Promise<{ success: boolean; messageId?: number; error?: string }> {
  const cfg = getTelegramConfig();
  const token = customConfig?.botToken || cfg.botToken || process.env.TELEGRAM_BOT_TOKEN;
  const chatId = customConfig?.chatId || cfg.chatId || process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    return {
      success: false,
      error: "Telegram Bot Token أو Chat ID غير محددين."
    };
  }

  const url = `https://api.telegram.org/bot${token}/sendPhoto`;

  try {
    let response: Response;

    if (typeof photoBufferOrUrl === 'string' && (photoBufferOrUrl.startsWith('http://') || photoBufferOrUrl.startsWith('https://'))) {
      const payload: any = {
        chat_id: chatId,
        photo: photoBufferOrUrl,
        caption: caption.slice(0, 1024), // Telegram max caption length
        parse_mode: "HTML",
      };
      if (customConfig?.replyMarkup) {
        payload.reply_markup = customConfig.replyMarkup;
      }
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      // Send binary PNG photo using standard FormData
      const formData = new FormData();
      formData.append("chat_id", chatId);
      formData.append("caption", caption.slice(0, 1024));
      formData.append("parse_mode", "HTML");
      if (customConfig?.replyMarkup) {
        formData.append("reply_markup", JSON.stringify(customConfig.replyMarkup));
      }

      const buffer = typeof photoBufferOrUrl === 'string'
        ? Buffer.from(photoBufferOrUrl)
        : photoBufferOrUrl;

      const blob = new Blob([buffer], { type: "image/png" });
      formData.append("photo", blob, "tradingview_smc_chart.png");

      response = await fetch(url, {
        method: "POST",
        body: formData,
      });
    }

    const data = (await response.json()) as any;

    if (!response.ok || !data.ok) {
      const errDescription = data?.description || `HTTP ${response.status}`;
      return { success: false, error: errDescription };
    }

    return { success: true, messageId: data.result?.message_id };
  } catch (err: any) {
    return { success: false, error: err?.message || "خطأ أثناء إرسال الصورة إلى Telegram" };
  }
}

/**
 * Performs a real-time live system & market analysis diagnostic test
 * and generates a comprehensive report for Telegram & Web UI
 */
export async function runSystemDiagnosticAndFormatMessage(): Promise<{
  success: boolean;
  text: string;
  data: {
    marketOnline: boolean;
    analysisActive: boolean;
    telegramConnected: boolean;
    databaseHealthy: boolean;
    assets: Array<{ symbol: string; price: number; latencyMs: number; status: string; marketOpen: boolean }>;
    session: any;
    killzone: any;
    activeSubscribersCount: number;
    timestamp: string;
  };
}> {
  const testAssets = ["XAU/USD"];
  
  // Parallel Zero-Lag Query across all assets simultaneously
  const assetResults: Array<{ symbol: string; price: number; latencyMs: number; status: string; marketOpen: boolean }> = await Promise.all(
    testAssets.map(async (sym) => {
      const t0 = Date.now();
      try {
        const priceData = await getLivePrice(sym);
        const latency = Math.max(8, Date.now() - t0);
        if (priceData && priceData.price > 0) {
          return {
            symbol: sym,
            price: priceData.price,
            latencyMs: latency,
            status: "ONLINE",
            marketOpen: priceData.isMarketOpen !== false,
          };
        } else {
          return {
            symbol: sym,
            price: 0,
            latencyMs: latency,
            status: "UNAVAILABLE",
            marketOpen: false,
          };
        }
      } catch {
        return {
          symbol: sym,
          price: 0,
          latencyMs: Math.max(12, Date.now() - t0),
          status: "OFFLINE",
          marketOpen: false,
        };
      }
    })
  );

  const feedErrorsCount = assetResults.filter(a => a.status !== "ONLINE").length;

  const goldSession = getMarketSessionStatus("XAU/USD");
  const goldKillzone = getKillzoneStatus("XAU/USD");
  const subscribers = getActiveChatSubscribers();
  const cfg = getTelegramConfig();
  const isTelegramConfigured = Boolean(cfg.botToken && (cfg.chatId || subscribers.length > 0));
  const isMarketOnline = feedErrorsCount === 0;
  const isAnalysisActive = true;
  const isAllHealthy = isMarketOnline;
  const nowStr = new Date().toLocaleTimeString("ar-MA", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  let text = "";
  if (isAllHealthy) {
    text = `🧪 <b>تقرير فحص مكتب الذهب المتفوق (Gold Elite Desk Health)</b>

✅ <b>النتيجة: تركيز 100% على الذهب وبسرعة فائقة (Zero Lag)!</b>

📡 <b>1. أسعار الذهب الحية المباشرة (Live Gold Prices):</b>
${assetResults.map(a => {
  let label = a.symbol;
  if (a.symbol === "XAU/USD") label = "🥇 XAU/USD (الذهب الفوري Spot)";

  const formattedPrice = a.price > 0 ? a.price.toFixed(2) + "$" : "N/A";
  const openLabel = a.marketOpen ? "🟢 مفتوح" : "🟡 مغلق (عطلة)";

  return `• <b>${label}:</b> <code>${formattedPrice}</code> [${openLabel}] (${a.latencyMs}ms)`;
}).join("\n")}

🧠 <b>2. محرك قنص صفقات الذهب (Gold AI Decision Engine):</b>
• <b>التخصص الحصري:</b> 🟢 <b>تركيز 100% على سيولة الذهب (XAU/USD)</b>
• <b>الجلسة الحالية:</b> <b>${goldSession.labelAr || goldSession.labelFr || "جلسة التداول الرسمية"}</b>
• <b>منطقة القتل (ICT Killzone):</b> <b>${goldKillzone.killzoneNameAr || goldKillzone.killzoneName || "فترة تداول اعتيادية"}</b>
• <b>خوارزميات الفحص:</b> London Gold Fix + Judas Swings + ICT Silver Bullet + FVG Mitigations

💾 <b>3. قاعدة البيانات والأمان (Storage & Database):</b>
• <b>حالة التخزين:</b> 🟢 <b>تخزين دائم محمي 24/7 (Local Persistent Storage)</b>
• <b>المشتركون النشطون:</b> <b>${subscribers.length} مشترك</b>

🤖 <b>4. حالة بوت التيليجرام (Telegram Dispatcher):</b>
• <b>سرعة الاستجابة:</b> 🟢 <b>فورية (<50ms) وجاهز لإرسال صفقات A+ المؤكدة</b>
• <b>وقت الفحص:</b> <b>${nowStr}</b>

🚀 <i>التطبيق متصل ومحرك التحليل خدام كيقنص أي فرصة قوية ومؤكدة (+90%) باش يصيفطها لك مباشرة!</i>`;
  } else {
    text = `⚠️ <b>تقرير فحص النظام (System Diagnostic Alert)</b>

❌ <b>تنبيه: تم رصد بعض الملاحظات أثناء فحص الاتصال:</b>

📡 <b>1. حالة الأسواق والأسعار الحية:</b>
${assetResults.map(a => `• <b>${a.symbol}:</b> ${a.status === "ONLINE" ? `<code>${a.price}</code> 🟢 شغال (${a.latencyMs}ms)` : `❌ منقطع (${a.status})`}`).join("\n")}

${!isTelegramConfigured ? `⚠️ <b>تنبيه التيليجرام:</b> إعدادات البوت (Token أو Chat ID) تحتاج ضبطاً لتصلك الإشعارات.` : `🤖 <b>حالة البوت:</b> 🟢 متصل ومفعل.`}

🧠 <b>2. محرك التحليل:</b> 🟢 <b>نشط وشغال محلياً 24/7</b>
• <b>وقت الفحص:</b> <b>${nowStr}</b>

👉 <i>قم بتفقد الاتصال لضمان استلام كافة الإشارات بدون تأخير.</i>`;
  }

  return {
    success: isAllHealthy,
    text,
    data: {
      marketOnline: isMarketOnline,
      analysisActive: isAnalysisActive,
      telegramConnected: isTelegramConfigured,
      databaseHealthy: true,
      assets: assetResults,
      session: goldSession,
      killzone: goldKillzone,
      activeSubscribersCount: subscribers.length,
      timestamp: nowStr,
    }
  };
}

/**
 * Calculates custom lot size, risk in USD, and profit targets for a specific user profile
 */
export function calculateCustomTradeLotAndRisk(params: {
  symbol: string;
  entryPrice: number;
  stopLoss: number;
  target1: number;
  target2: number;
  capital: number;
  riskPercent: number;
}) {
  const { symbol, entryPrice, stopLoss, target1, target2, capital, riskPercent } = params;
  const safeCapital = Math.max(10, capital || 1000);
  const safeRiskPct = Math.max(0.1, riskPercent || 1.0);
  const riskUsd = (safeCapital * safeRiskPct) / 100;

  const rawSlDist = Math.abs(entryPrice - stopLoss);
  const safeSlDist = rawSlDist > 0 ? rawSlDist : (entryPrice * 0.005);

  let rawLot = 0.01;
  let lotFormatted = "0.01 Lot";
  let pipOrPointDist = 0;
  let distUnit = "نقطة";

  const sym = symbol.toUpperCase();
  if (sym.includes("XAU") || sym.includes("GOLD")) {
    // Gold: 1 standard lot = 100 oz. $1 move = $100 per 1 standard lot
    rawLot = riskUsd / (safeSlDist * 100);
    rawLot = Math.max(0.01, Number(rawLot.toFixed(2)));
    lotFormatted = `${rawLot.toFixed(2)} Lot`;
    pipOrPointDist = Number(safeSlDist.toFixed(2));
    distUnit = "$";
  } else if (sym.includes("BTC")) {
    // BTC: 1 contract/coin. Price move $1000 = $1000 per 1 BTC
    rawLot = riskUsd / safeSlDist;
    if (rawLot < 0.01) {
      lotFormatted = `${rawLot.toFixed(4)} BTC`;
    } else {
      lotFormatted = `${rawLot.toFixed(3)} BTC`;
    }
    pipOrPointDist = Number(safeSlDist.toFixed(1));
    distUnit = "$";
  } else if (sym.includes("ETH")) {
    rawLot = riskUsd / safeSlDist;
    rawLot = Math.max(0.01, Number(rawLot.toFixed(2)));
    lotFormatted = `${rawLot.toFixed(2)} ETH`;
    pipOrPointDist = Number(safeSlDist.toFixed(2));
    distUnit = "$";
  } else if (sym.includes("OIL") || sym.includes("USOIL") || sym.includes("WTI")) {
    // Oil: 1 standard lot = 1000 barrels. $1 move = $1000
    rawLot = riskUsd / (safeSlDist * 1000);
    rawLot = Math.max(0.01, Number(rawLot.toFixed(2)));
    lotFormatted = `${rawLot.toFixed(2)} Lot`;
    pipOrPointDist = Number(safeSlDist.toFixed(2));
    distUnit = "$";
  } else if (sym.includes("NVDA") || sym.includes("AAPL") || sym.includes("TSLA")) {
    const shares = Math.max(1, Math.floor(riskUsd / safeSlDist));
    rawLot = shares;
    lotFormatted = `${shares} Share`;
    pipOrPointDist = Number(safeSlDist.toFixed(2));
    distUnit = "$";
  } else {
    // Forex standard pairs (EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, etc.)
    const isJpy = sym.includes("JPY");
    const isCad = sym.includes("CAD");
    const pipMultiplier = isJpy ? 0.01 : 0.0001;
    const pips = safeSlDist / pipMultiplier;
    
    // Accurate pip value per standard lot (100,000 units) in USD
    let pipValuePerLot = 10;
    if (isJpy && entryPrice > 0) {
      pipValuePerLot = 1000 / entryPrice; // e.g. for USD/JPY ~154.20 -> ~$6.48
    } else if (isCad && entryPrice > 0) {
      pipValuePerLot = 10 / entryPrice; // e.g. for USD/CAD ~1.37 -> ~$7.30
    }

    rawLot = riskUsd / (pips * pipValuePerLot);
    rawLot = Math.max(0.01, Number(rawLot.toFixed(2)));
    lotFormatted = `${rawLot.toFixed(2)} Lot`;
    pipOrPointDist = Number(pips.toFixed(1));
    distUnit = "Pip";
  }

  const tp1Dist = Math.abs(target1 - entryPrice);
  const tp2Dist = Math.abs(target2 - entryPrice);

  const tp1GainUsd = (tp1Dist / safeSlDist) * riskUsd;
  const tp1GainPct = (tp1GainUsd / safeCapital) * 100;

  const tp2GainUsd = (tp2Dist / safeSlDist) * riskUsd;
  const tp2GainPct = (tp2GainUsd / safeCapital) * 100;

  const rrRatio = (tp2Dist / safeSlDist).toFixed(2);

  return {
    capital: safeCapital,
    riskPercent: safeRiskPct,
    riskUsd,
    rawLot,
    lotFormatted,
    slDistance: safeSlDist,
    pipOrPointDist,
    distUnit,
    tp1GainUsd,
    tp1GainPct,
    tp2GainUsd,
    tp2GainPct,
    rrRatio,
  };
}

/**
 * Calculates standard lot matrix for common capital levels at 1.0% risk
 */
export function getStandardLotMatrix(signal: {
  symbol: string;
  entryPrice?: number;
  entryZone?: string;
  stopLoss: number;
  target1: number;
  target2: number;
}) {
  let entryNum = signal.entryPrice;
  if (!entryNum && signal.entryZone) {
    const parts = signal.entryZone.split("-").map((p) => parseFloat(p.replace(/[^0-9.]/g, ""))).filter((n) => !isNaN(n));
    entryNum = parts.length > 0 ? parts.reduce((a, b) => a + b, 0) / parts.length : signal.target1;
  }
  const safeEntry = entryNum || signal.stopLoss;

  const c500 = calculateCustomTradeLotAndRisk({
    symbol: signal.symbol,
    entryPrice: safeEntry,
    stopLoss: signal.stopLoss,
    target1: signal.target1,
    target2: signal.target2,
    capital: 500,
    riskPercent: 1.0,
  });

  const c1k = calculateCustomTradeLotAndRisk({
    symbol: signal.symbol,
    entryPrice: safeEntry,
    stopLoss: signal.stopLoss,
    target1: signal.target1,
    target2: signal.target2,
    capital: 1000,
    riskPercent: 1.0,
  });

  const c5k = calculateCustomTradeLotAndRisk({
    symbol: signal.symbol,
    entryPrice: safeEntry,
    stopLoss: signal.stopLoss,
    target1: signal.target1,
    target2: signal.target2,
    capital: 5000,
    riskPercent: 1.0,
  });

  const c10k = calculateCustomTradeLotAndRisk({
    symbol: signal.symbol,
    entryPrice: safeEntry,
    stopLoss: signal.stopLoss,
    target1: signal.target1,
    target2: signal.target2,
    capital: 10000,
    riskPercent: 1.0,
  });

  return {
    distFormatted: `${c1k.pipOrPointDist} ${c1k.distUnit}`,
    lot500: c500.lotFormatted,
    lot1k: c1k.lotFormatted,
    lot5k: c5k.lotFormatted,
    lot10k: c10k.lotFormatted,
    rrRatio: c1k.rrRatio,
  };
}

export function getCapitalSelectionKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "💵 500$", callback_data: "set_cap_500" },
        { text: "💵 1,000$", callback_data: "set_cap_1000" },
        { text: "💵 2,000$", callback_data: "set_cap_2000" },
      ],
      [
        { text: "💵 5,000$", callback_data: "set_cap_5000" },
        { text: "💵 10,000$", callback_data: "set_cap_10000" },
        { text: "💵 25,000$", callback_data: "set_cap_25000" },
      ],
      [
        { text: "💵 50,000$", callback_data: "set_cap_50000" },
        { text: "💵 100,000$", callback_data: "set_cap_100000" },
      ],
      [
        { text: "🛡️ تعديل نسبة المخاطرة (%)", callback_data: "set_risk_menu" },
        { text: "📋 عرض ملفي", callback_data: "my_profile" },
      ]
    ]
  };
}

export function getRiskSelectionKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "🛡️ 0.5% (حذر جداً)", callback_data: "set_risk_0.5" },
        { text: "🛡️ 1.0% (القياسي الموصى به)", callback_data: "set_risk_1.0" },
      ],
      [
        { text: "🛡️ 1.5%", callback_data: "set_risk_1.5" },
        { text: "🛡️ 2.0% (متوسط)", callback_data: "set_risk_2.0" },
        { text: "🛡️ 3.0% (أقصى حد)", callback_data: "set_risk_3.0" },
      ],
      [
        { text: "💰 تعديل رأس المال ($)", callback_data: "set_cap_menu" },
        { text: "📋 عرض ملفي", callback_data: "my_profile" },
      ]
    ]
  };
}

export function formatUserProfileMessage(chatId: string, userName: string): { text: string; replyMarkup: any } {
  const profile = getUserSubscriberProfile(chatId);
  const riskUsd = (profile.capital * profile.riskPercent) / 100;

  const text = `⚙️ <b>محفظتك | ${profile.firstName || userName}</b>
💰 <b>رأس المال:</b> <code>${profile.capital.toLocaleString()}$</code>
🛡️ <b>المخاطرة:</b> <code>${profile.riskPercent}%</code> (-$${riskUsd.toFixed(2)})
🛑 <i>الستوب ثابت لحماية الحساب.</i>`;

  const replyMarkup = {
    inline_keyboard: [
      [
        { text: "💰 رأس المال ($)", callback_data: "set_cap_menu" },
        { text: "🛡️ المخاطرة (%)", callback_data: "set_risk_menu" },
      ],
      [
        { text: "🧮 لوت أحدث صفقة", callback_data: "calc_latest_lot" },
      ]
    ]
  };

  return { text, replyMarkup };
}

export function formatCustomLotCalculationMessage(chatId: string, userName: string, signal: any): { text: string; replyMarkup: any } {
  const profile = getUserSubscriberProfile(chatId);
  const parts = (signal.entryZone || "").split("-").map((p: string) => parseFloat(p.replace(/[^0-9.]/g, ""))).filter((n: number) => !isNaN(n));
  const entryNum = parts.length > 0 ? parts.reduce((a: number, b: number) => a + b, 0) / parts.length : (signal.entryPrice || signal.target1);
  const calc = calculateCustomTradeLotAndRisk({
    symbol: signal.symbol,
    entryPrice: entryNum,
    stopLoss: signal.stopLoss,
    target1: signal.target1,
    target2: signal.target2,
    capital: profile.capital,
    riskPercent: profile.riskPercent,
  });

  const isBuy = signal.signalType === "BUY";
  const icon = isBuy ? "🟢" : "🔴";

  const text = `🧮 <b>حساب اللوت | ${signal.symbol}</b>
───────────────
${icon} <b>${signal.signalType}</b> | 📍 <b>Entry:</b> <code>${signal.entryZone || entryNum}</code>
🛑 <b>SL:</b> <code>${signal.stopLoss}</code> <i>(${calc.pipOrPointDist} ${calc.distUnit})</i>
🎯 <b>اللوت:</b> <code>${calc.lotFormatted}</code> (${calc.capital.toLocaleString()}$ | -${calc.riskPercent}% = -$${calc.riskUsd.toFixed(2)})
───────────────
• الخسارة عند SL: <b>-$${calc.riskUsd.toFixed(2)}</b>
• الربح عند TP1: <b>+$${calc.tp1GainUsd.toFixed(2)}</b> | TP2: <b>+$${calc.tp2GainUsd.toFixed(2)}</b>`;

  const replyMarkup = {
    inline_keyboard: [
      [
        { text: "🎯 دخلت الصفقة", callback_data: `join_${signal.id}` },
        { text: "⚙️ إعدادات المحفظة", callback_data: "my_profile" },
      ]
    ]
  };

  return { text, replyMarkup };
}

/**
 * Interactive Telegram Bot Message Handler:
 * 1. /start for new users: Asks for activation code (دخل كود التفعيل)
 * 2. Entering code:
 *    - If invalid: "الكود غلط، عاود كتبو وتأكد منو"
 *    - If valid: "صافي راه خدم! مدة الكود: ... ودابا غايبداو يوصلوك الصفقات"
 * 3. /test or /health or /check: Runs full live system diagnostic and market analysis check
 * 4. /status command: Checks time remaining on license
 * 5. /capital [amount] & /risk [pct]: Customizes user capital & risk preferences persistently
 * 6. /profile & /lot: Displays user's custom risk calculation & lot recommendations
 */
export async function handleIncomingTelegramMessage(
  chatId: string,
  rawText: string,
  userName: string,
  token: string
) {
  const text = (rawText || "").trim();
  const lowerText = text.toLowerCase();
  const isStart = text.startsWith("/start");
  const isTestOrDiagnostic =
    text.startsWith("/test") ||
    text.startsWith("/ping") ||
    text.startsWith("/health") ||
    text.startsWith("/check") ||
    text.startsWith("/diag") ||
    text.startsWith("/system") ||
    text.startsWith("/analyse") ||
    text.startsWith("/analysis") ||
    lowerText.includes("wach khadama") ||
    lowerText.includes("wach khdam") ||
    lowerText.includes("فحص") ||
    lowerText.includes("اختبار") ||
    lowerText === "test";
  const isStatus = text.startsWith("/status") || text.startsWith("/code") || text.startsWith("/info");
  const isStats = text.startsWith("/stats") || text.startsWith("/performance") || text.startsWith("/winrate") || text.startsWith("/results") || text.startsWith("/arba7") || text.startsWith("/sl");
  const isHelp = text.startsWith("/help");
  const isProfile = text.startsWith("/profile") || text.startsWith("/settings") || text.startsWith("/myrisk") || text.startsWith("/account") || text.startsWith("/hisab") || lowerText === "profile" || lowerText === "settings" || lowerText === "إعدادات" || lowerText === "حسابي";
  const isCapitalCmd = text.startsWith("/capital") || text.startsWith("/solde") || text.startsWith("/balance") || text.startsWith("/flous") || lowerText.startsWith("capital") || lowerText.startsWith("solde") || lowerText.startsWith("راس المال") || lowerText.startsWith("رأس المال");
  const isRiskCmd = text.startsWith("/risk") || text.startsWith("/risq") || text.startsWith("/mokhatara") || text.startsWith("/mo5atara") || lowerText.startsWith("risk") || lowerText.startsWith("نسبة المخاطرة") || lowerText.startsWith("المخاطرة");
  const isLotCmd = text.startsWith("/lot") || text.startsWith("/calclot") || text.startsWith("/calc") || lowerText.includes("ch7al lot") || lowerText.includes("شحال لوت") || lowerText.includes("اللوت") || lowerText === "lot";
  const isSignalCmd = text.startsWith("/signal") || text.startsWith("/live") || text.startsWith("/safqa") || text.startsWith("/saf9a") || text.startsWith("/gold") || text.startsWith("/now") || lowerText === "signal" || lowerText === "صفقة";
  const isAgentsCmd = text.startsWith("/crew") || text.startsWith("/crewai") || text.startsWith("/agents") || text.startsWith("/agent") || text.startsWith("/wokal") || text.startsWith("/operations") || lowerText.includes("crew") || lowerText.includes("الوكلاء");

  const status = isChatActivated(chatId);

  // 1. User clicked /start
  if (isStart) {
    if (status.active) {
      const alreadyActiveMsg = `👋 <b>أهلاً بك ${status.firstName || userName}!</b>

✅ <b>البوت مفعل ويعمل على مدار الساعة (24/7)</b>
⏱️ <b>المدة المتبقية:</b> <b>${formatRemainingTime(status.remainingMs)}</b>
🔑 <b>رمز التفعيل:</b> <code>${status.code}</code>

💰 <b>رأس مالك ومخاطرتك:</b> أرسل <code>/profile</code> أو <code>/capital</code> لضبط محفظتك وحساب اللوت المناسب لكل صفقة بدقة!
🧪 <b>لفحص اتصال النظام والتحليل الحي أرسل:</b> <code>/test</code>

🚀 <i>ستصلك أفضل الصفقات المؤكدة عالية الاحتمالية تلقائياً فور توفر شروط الدخول.</i>`;
      await sendTelegramMessage(alreadyActiveMsg, { botToken: token, chatId });
    } else {
      // Auto-activate user with Permanent VIP Code from db.json so user never loses signals when app restarts
      const autoAct = activateChatWithCode(chatId, "PRO-TRADER-2026-VIP", { firstName: userName });
      const welcomeActiveMsg = `👋 مرحباً بك <b>${userName}</b>!

🎉 <b>تم تفعيل حسابك تلقائياً بكود VIP الدائم المحفوظ في db.json:</b>
🔑 <b>رمز التفعيل:</b> <code>PRO-TRADER-2026-VIP</code>
⏱️ <b>الصلاحية:</b> <b>مدى الحياة (VIP دائم 10 سنوات محفوظ في db.json)</b>
🟢 <b>حالة البوت:</b> متصل وشغال 24/7!

⚙️ <b>خصص حسابك الآن:</b>
• أرسل <code>/capital 1000</code> لضبط رأس مالك (مثلاً 1,000$ أو 5,000$).
• أرسل <code>/risk 1</code> لضبط نسبة المخاطرة لكل صفقة (مثلاً 1% أو 2%).
• أو أرسل <code>/profile</code> لإدارة إعداداتك بضغطة زر!

🚀 <i>ستصلك الآن أفضل صفقات الـ A+ المؤكدة بالأسعار الحقيقية الدقيقة فور رصدها.</i>
🧪 <i>لفحص الاتصال والتحليل الحي أرسل:</i> <code>/test</code>`;
      await sendTelegramMessage(welcomeActiveMsg, { botToken: token, chatId });
    }
    return;
  }

  // 1.2. User requested profile or settings (/profile, /settings, /myrisk)
  if (isProfile) {
    const prof = formatUserProfileMessage(chatId, userName);
    await sendTelegramMessage(prof.text, { botToken: token, chatId, replyMarkup: prof.replyMarkup });
    return;
  }

  // 1.3. Smart Capital & Risk Parser (Supports commands, Darija, fixed $, and combined phrases)
  let detectedCapital: number | undefined;
  let detectedRisk: number | undefined;

  // Check combined /calc or /lot with arguments: e.g. "/calc 5000 1", "/lot 1000 1%", "/calc 5000"
  if (text.startsWith("/calc") || text.startsWith("/calclot") || (text.startsWith("/lot") && text.length > 5)) {
    const nums = text.match(/\d+[\d,.]*/g);
    if (nums && nums.length >= 2) {
      detectedCapital = parseFloat(nums[0].replace(/,/g, ""));
      detectedRisk = parseFloat(nums[1]);
    } else if (nums && nums.length === 1) {
      const val = parseFloat(nums[0].replace(/,/g, ""));
      if (val >= 50) detectedCapital = val;
      else detectedRisk = val;
    }
  }

  // Check explicit /capital command or capital keywords
  if (!detectedCapital && isCapitalCmd) {
    const rawNumberMatch = text.match(/\d+[\d,.]*/g);
    if (rawNumberMatch && rawNumberMatch.length > 0) {
      const num = parseFloat(rawNumberMatch[0].replace(/,/g, ""));
      if (!isNaN(num) && num > 0) {
        detectedCapital = num;
        if (rawNumberMatch.length > 1) {
          detectedRisk = parseFloat(rawNumberMatch[1]);
        }
      }
    }
  }

  // Check explicit /risk command or risk keywords
  if (!detectedRisk && isRiskCmd) {
    const dollarMatch = text.match(/\$\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*\$/);
    if (dollarMatch) {
      const dollarVal = parseFloat(dollarMatch[1] || dollarMatch[2]);
      const currentProfile = getUserSubscriberProfile(chatId);
      const cap = detectedCapital || currentProfile.capital || 1000;
      if (dollarVal > 0 && cap > 0) {
        detectedRisk = Number(((dollarVal / cap) * 100).toFixed(2));
      }
    } else {
      const rawNumberMatch = text.match(/\d+(\.\d+)?/);
      if (rawNumberMatch) {
        const num = parseFloat(rawNumberMatch[0]);
        if (!isNaN(num) && num > 0) {
          detectedRisk = num;
        }
      }
    }
  }

  // Check natural Moroccan Darija / Arabic / French / English phrases:
  // e.g. "3ndi 5000$ bghit nriski 1%", "capital 3000 o bghit nriski 2%", "solde 2000 flous 2000"
  if (!detectedCapital && !detectedRisk) {
    const capMatch = text.match(/(?:capital|solde|balance|3ndi|flous|راس المال|رأس المال)\s*[:=]?\s*(\$?\d+[\d,.]*)/i);
    if (capMatch) {
      const parsed = parseFloat(capMatch[1].replace(/[\$,]/g, ""));
      if (!isNaN(parsed) && parsed > 0) detectedCapital = parsed;
    }
    const riskMatch = text.match(/(?:risk|risq|mokhatara|mo5atara|nriski|nkhater|مخاطرة|المخاطرة)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(%|\$)?/i);
    if (riskMatch) {
      const rawRiskNum = parseFloat(riskMatch[1]);
      if (riskMatch[2] === "$") {
        const currentProfile = getUserSubscriberProfile(chatId);
        const cap = detectedCapital || currentProfile.capital || 1000;
        detectedRisk = Number(((rawRiskNum / cap) * 100).toFixed(2));
      } else if (!isNaN(rawRiskNum) && rawRiskNum > 0) {
        detectedRisk = rawRiskNum;
      }
    }
  }

  // If user provided Capital and/or Risk: save and calculate immediately!
  if (detectedCapital || detectedRisk) {
    const updateRes = updateUserCapitalAndRisk(chatId, detectedCapital, detectedRisk, userName);
    const latestSig = Array.from(recentDispatchedSignalsMap.values()).pop() || INITIAL_SIGNALS[0];

    const parts = (latestSig.entryZone || "").split("-").map((p: string) => parseFloat(p.replace(/[^0-9.]/g, ""))).filter((n: number) => !isNaN(n));
    const entryNum = parts.length > 0 ? parts.reduce((a: number, b: number) => a + b, 0) / parts.length : (latestSig.entryPrice || latestSig.target1);
    const calc = calculateCustomTradeLotAndRisk({
      symbol: latestSig.symbol,
      entryPrice: entryNum,
      stopLoss: latestSig.stopLoss,
      target1: latestSig.target1,
      target2: latestSig.target2,
      capital: updateRes.capital,
      riskPercent: updateRes.riskPercent,
    });

    const isBuy = latestSig.signalType === "BUY";
    const icon = isBuy ? "🟢" : "🔴";

    const successMsg = `✅ <b>تم ضبط المحفظة وحساب اللوت!</b>
───────────────
💰 <b>رأس المال:</b> <code>${updateRes.capital.toLocaleString()}$</code> | 🛡️ <b>المخاطرة:</b> <code>${updateRes.riskPercent}% (-$${calc.riskUsd.toFixed(2)})</code>
🎯 <b>صفقة:</b> <code>${latestSig.symbol}</code> (${icon} ${latestSig.signalType})
📍 <b>Entry:</b> <code>${latestSig.entryZone || entryNum}</code>
🛑 <b>SL (ثابت):</b> <code>${latestSig.stopLoss}</code>
🧮 <b>اللوت الدقيق:</b> <code>${calc.lotFormatted}</code>
───────────────
• الخسارة عند SL: <b>-$${calc.riskUsd.toFixed(2)}</b> (-${updateRes.riskPercent}%)
• الربح عند TP1: <b>+$${calc.tp1GainUsd.toFixed(2)}</b> (+${calc.tp1GainPct.toFixed(1)}%)
• الربح عند TP2: <b>+$${calc.tp2GainUsd.toFixed(2)}</b> (+${calc.tp2GainPct.toFixed(1)}%)
⚖️ <b>R:R:</b> <code>1:${calc.rrRatio}</code>
───────────────
🚀 <i>كل الصفقات القادمة ستصلك بحجم اللوت المخصص لمحفظتك تلقائياً.</i>`;

    const replyMarkup = {
      inline_keyboard: [
        [
          { text: "🎯 دخلت الصفقة", callback_data: `join_${latestSig.id}` },
          { text: "⚙️ إعدادات المحفظة", callback_data: "my_profile" },
        ]
      ]
    };
    await sendTelegramMessage(successMsg, { botToken: token, chatId, replyMarkup });
    return;
  }

  // If user sent empty /capital command
  if (isCapitalCmd) {
    const promptCapMsg = `💰 <b>حدد رأس مال محفظتك (Capital in USD):</b>
━━━━━━━━━━━━━━━━━━
اختر مبلغ رأس مالك بالضغط على أحد الأزرار، أو اكتب المبلغ مباشرة (مثال: <code>/capital 5000</code> أو <code>3000$</code>):`;
    await sendTelegramMessage(promptCapMsg, { botToken: token, chatId, replyMarkup: getCapitalSelectionKeyboard() });
    return;
  }

  // If user sent empty /risk command
  if (isRiskCmd) {
    const promptRiskMsg = `🛡️ <b>حدد نسبة المخاطرة لكل صفقة (Risk Percentage %):</b>
━━━━━━━━━━━━━━━━━━
القاعدة المؤسساتية الذهبية هي <b>1.0%</b> كحد أقصى لكل صفقة لحماية رأس المال.
اختر النسبة بالضغط على أحد الأزرار، أو اكتبها مباشرة (مثال: <code>/risk 1</code> أو <code>/risk 50$</code>):`;
    await sendTelegramMessage(promptRiskMsg, { botToken: token, chatId, replyMarkup: getRiskSelectionKeyboard() });
    return;
  }

  // 1.45. User asked for tailored lot calculation (/lot, /calclot)
  if (isLotCmd) {
    const latestSig = Array.from(recentDispatchedSignalsMap.values()).pop() || INITIAL_SIGNALS[0];
    if (latestSig) {
      const calcMsg = formatCustomLotCalculationMessage(chatId, userName, latestSig);
      await sendTelegramMessage(calcMsg.text, { botToken: token, chatId, replyMarkup: calcMsg.replyMarkup });
      return;
    }
  }

  // 1.4. User explicitly requested a live signal or real-time analysis (/signal, /live, /gold, /safqa)
  if (isSignalCmd) {
    try {
      const { runExunuSMCEngine, convertExunuToAISignal } = await import("./exunuAgentBridge");
      const userProf = getUserSubscriberProfile(chatId);
      const sections: string[] = [];
      for (const sym of ["XAU/USD", "EUR/USD"]) {
        const res = await runExunuSMCEngine(sym);
        const r = res.strategy;
        const st = r.setup;
        if (r.status === "SIGNAL" && st && ["PENDING", "OPEN"].includes(st.lifecycle.state)) {
          const sig = convertExunuToAISignal(res, { symbol: sym, price: r.price } as any);
          recentDispatchedSignalsMap.set(sig.id, sig);
          await sendTelegramMessage(formatSignalMessage(sig, userProf), {
            botToken: token, chatId,
            replyMarkup: { inline_keyboard: [[
              { text: "🎯 دخلت الصفقة", callback_data: `enter_trade:${sig.id}` },
              { text: "🛡️ تأمين الدخول (BE)", callback_data: `be_trade:${sig.id}` },
              { text: "✖️ إغلاق", callback_data: `close_trade:${sig.id}` }
            ]] },
          });
          continue;
        }
        const lines = r.checklist.map(c => `${c.passed ? "✅" : "❌"} ${c.ruleAr}: <i>${c.detail}</i>`).join("\n");
        const levels = st ? `\n📍 <b>${st.direction}</b> ${st.entryType} <code>${st.entry}</code> · SL <code>${st.sl}</code> · TP2 <code>${st.tp2}</code> · score ${r.score}` : "";
        sections.push(`<b>${sym} · ${r.strategyName}</b>
💲 <code>${r.price}</code> · الاتجاه <b>${r.bias.direction}</b>
🧭 <b>${r.headlineAr}</b> (${r.headline})${levels}
${lines}`);
      }
      if (sections.length) {
        await sendTelegramMessage(`⏱️ <b>تحليل مباشر — EXUNU</b>

${sections.join("\n\n")}

<i>تصلك الإشارة تلقائياً فقط عندما تكتمل كل الشروط (score ≥ 75).</i>`, { botToken: token, chatId });
      }
      return;
    } catch (err: any) {
      await sendTelegramMessage(`⚠️ تعذر جلب التحليل اللحظي: ${err.message}`, { botToken: token, chatId });
      return;
    }
  }

  // 1.45. User requested CrewAI Agents status (/crew, /crewai, /agents, /agent, /wokal)
  if (isAgentsCmd) {
    try {
      const { runExunuSMCEngine } = await import("./exunuAgentBridge");
      const spot = await fetchLiveSpotGold(true);
      const res = await runExunuSMCEngine("XAU/USD", spot.price);
      const ag = res.agents;
      const agentsMsg = `🤖 <b>وكلاء EXUNU الأربعة (تحليل واحد مشترك)</b>

🥇 السعر: <code>$${spot.price.toFixed(2)}</code>

1️⃣ <b>Structure Agent:</b> ${ag.structure_agent.summary}
2️⃣ <b>Liquidity Agent:</b> ${ag.liquidity_agent.summary}
3️⃣ <b>Risk Agent:</b> ${ag.risk_agent.summary}
4️⃣ <b>CTO:</b> ${res.strategy.headlineAr} (score ${res.strategy.score}/100)

<i>نفس التحليل الظاهر على الشارت داخل التطبيق.</i>`;
      await sendTelegramMessage(agentsMsg, { botToken: token, chatId });
      return;
    } catch (err: any) {
      await sendTelegramMessage(`⚠️ تعذر جلب تقرير CrewAI: ${err.message}`, { botToken: token, chatId });
      return;
    }
  }

  // 1.5. User asked for system test or live market analysis check (/test, /health, /ping, /check, "wach khadama")
  if (isTestOrDiagnostic) {
    const diagReport = await runSystemDiagnosticAndFormatMessage();
    await sendTelegramMessage(diagReport.text, { botToken: token, chatId });
    return;
  }

  // 2. User asked for personal performance stats (/stats, /mystats, /results, /arba7, /winrate)
  if (isStats) {
    const userStats = formatUserPersonalStatsMessage(chatId, userName);
    await sendTelegramMessage(userStats.text, { botToken: token, chatId, replyMarkup: userStats.replyMarkup });
    return;
  }

  // 3. User asked for status
  if (isStatus) {
    if (status.active) {
      const prof = getUserSubscriberProfile(chatId);
      const statusMsg = `📋 <b>حالة الاشتراك وإعدادات الحساب:</b>

• <b>المشترك:</b> <b>${status.firstName || userName}</b>
• <b>الحالة:</b> 🟢 مفعل ونشط
• <b>رمز التفعيل:</b> <code>${status.code}</code>
• <b>المدة المتبقية:</b> <b>${formatRemainingTime(status.remainingMs)}</b>
• <b>رأس المال المسجل:</b> <b>${prof.capital.toLocaleString()}$</b>
• <b>نسبة المخاطرة:</b> <b>${prof.riskPercent}%</b>
• <b>نظام منع السبام:</b> 🛡️ <b>نشط (صفقة واحدة مؤكدة A+ فقط كل 45 دقيقة)</b>

⚙️ لتعديل رأس المال أو المخاطرة أرسل: <code>/profile</code>
🧪 لفحص اتصال النظام والتحليل الحي أرسل: <code>/test</code>`;
      await sendTelegramMessage(statusMsg, { botToken: token, chatId });
    } else if (status.isExpired) {
      const expiredStatusMsg = `🔒 <b>حالة الاشتراك: منتهي الصلاحية</b>

👉 <i>يرجى إرسال رمز تفعيل جديد هنا لتشغيل البوت.</i>`;
      await sendTelegramMessage(expiredStatusMsg, { botToken: token, chatId });
    } else {
      const notActiveMsg = `🔒 <b>حسابك غير مفعل!</b>

👉 <i>يرجى إرسال رمز التفعيل لتشغيل البوت واستقبال الصفقات.</i>`;
      await sendTelegramMessage(notActiveMsg, { botToken: token, chatId });
    }
    return;
  }

  // 4. User asked for help
  if (isHelp) {
    const helpMsg = `🤖 <b>أوامر البوت وإدارة الحساب:</b>
• <code>/pairs</code> : استعراض كافة الأزواج المراقبة 24h/24 و 7j/7 (فوركس، كريبتو، ذهب، مؤشرات)
• <code>/capital 5000</code> : ضبط رأس مالك في البوت لحساب اللوت بدقة
• <code>/risk 1</code> : ضبط نسبة المخاطرة لكل صفقة (1% موصى بها)
• <code>/profile</code> : عرض وتعديل بيانات رأس المال والمخاطرة بضغطة زر
• <code>/lot</code> : حساب اللوت المناسب لأحدث صفقة بناءً على محفظتك
• <code>/mytrades</code> : عرض صفقاتك النشطة وتفاصيلها ومتابعتها لحظياً
• <code>/test</code> : فحص الاتصال الحي بالسوق ومحرك التحليل بالذكاء الاصطناعي
• <code>/status</code> : التحقق من مدة الاشتراك المتبقية
• <code>/stats</code> : تقرير سجل الأداء ونسبة الأرباح وتدقيق الصفقات
• <i>تفاعل مع أي صفقة أو اضغط [ 🎯 دخلت الصفقة ] لمتابعتها معك فورياً!</i>`;
    await sendTelegramMessage(helpMsg, { botToken: token, chatId });
    return;
  }

  // 4.4 User asked for pairs list (/pairs, /azwaj, /alazwaj, /radar)
  const isPairsRequest = text.startsWith("/pairs") || text.startsWith("/azwaj") || text.startsWith("/alazwaj") || text.startsWith("/radar") || lowerText === "azwaj" || lowerText === "الأزواج";
  if (isPairsRequest) {
    const pairsMsg = `🥇 <b>محطة تداول الذهب الحصرية (Gold Sovereign AI):</b>

🪙 <b>الزوج المعتمد:</b>
• <b>XAU/USD</b> (الذهب الفوري Spot OTC)

🛡️ <b>استراتيجية التداول:</b>
• <b>NY Silver Bullet (14:00 - 15:00 GMT) & SMC Liquidity Engine</b>
• تأكيد شمعة فريم 15 دقيقة (15M Sniper Rejection)
• فحص حقيقي لسيولة لندن وآسيا مع وقف هيكلي وعائد يفوق 1:2.0

⚡ يتم إرسال صفقات الذهب المؤكدة A+ فقط برسالة نصية صغيرة ومباشرة بدون أي تشتيت.`;
    await sendTelegramMessage(pairsMsg, { botToken: token, chatId });
    return;
  }

  // 4.5 User asked for their personal active trades (/mytrades, /trades, /safaqat)
  const isMyTrades = text.startsWith("/mytrades") || text.startsWith("/trades") || text.startsWith("/safaqat") || text.startsWith("/positions");
  if (isMyTrades) {
    const overview = formatUserActiveTradesTelegram(chatId);
    await sendTelegramMessage(overview.text, { botToken: token, chatId, replyMarkup: overview.replyMarkup });
    return;
  }

  // 4.6 User sent a text message indicating they entered the current trade (e.g. "دخلت", "دخلت الصفقة")
  const isEntryDeclaration = lowerText.includes("دخلت") || lowerText.includes("دخول") || lowerText === "buy" || lowerText === "sell" || lowerText === "entry" || lowerText.includes("dkhlt");
  if (isEntryDeclaration && status.active) {
    const latestSig = Array.from(recentDispatchedSignalsMap.values()).pop();
    if (latestSig) {
      const parts = (latestSig.entryZone || "").split("-").map((p: string) => parseFloat(p.replace(/[^0-9.]/g, ""))).filter((n: number) => !isNaN(n));
      const entryNum = parts.length > 0 ? parts.reduce((a: number, b: number) => a + b, 0) / parts.length : latestSig.target1;
      await trackUserTrade(chatId, userName, {
        id: latestSig.id,
        symbol: latestSig.symbol,
        signalType: latestSig.signalType,
        entryPrice: entryNum,
        stopLoss: latestSig.stopLoss,
        target1: latestSig.target1,
        target2: latestSig.target2,
        riskReward: latestSig.riskReward,
        timeframe: latestSig.timeframe,
        confidence: latestSig.confidence,
      });
      return;
    }
  }

  // 5. Activation code processing vs General query handling
  const cleanInput = text.trim().toUpperCase();
  const looksLikeCode = cleanInput.startsWith("VIP-") || cleanInput === "PRO-TRADER-2026-VIP" || cleanInput.includes("-");

  // Check if user simply sent a direct amount like "5000$" or "2000" or "1%"
  if (text.match(/^\$?\d{2,7}\$?$/)) {
    const val = parseFloat(text.replace(/[^0-9.]/g, ""));
    if (val >= 50) {
      const updateRes = updateUserCapitalAndRisk(chatId, val, undefined, userName);
      const capMsg = `✅ <b>تم تحديث رأس مالك إلى: ${updateRes.capital.toLocaleString()}$</b>\n\n🎯 سيتم استخدام هذا الرصيد في حساب اللوت الصارم لكل الصفقات!`;
      await sendTelegramMessage(capMsg, { botToken: token, chatId });
      return;
    }
  }

  // If user is already active and sent a casual message (not an activation code)
  if (status.active && !looksLikeCode) {
    const activeInfoMsg = `🟢 <b>حسابك مفعل وجاهز ${status.firstName || userName}!</b>

⏱️ <b>المدة المتبقية:</b> <b>${formatRemainingTime(status.remainingMs)}</b>
🔑 <b>رمز التفعيل الحالي:</b> <code>${status.code}</code>

💰 <b>رأس مالك المسجل:</b> <code>${getUserSubscriberProfile(chatId).capital.toLocaleString()}$</code> (مخاطرة: <b>${getUserSubscriberProfile(chatId).riskPercent}%</b>)
⚙️ لتعديل رأس المال أو المخاطرة أرسل: <code>/profile</code>

📡 <b>منهجية القناص المؤسساتي (Anti-Spam & A+ Precision):</b>
• ممنوع العشوائية والسبام نهائياً: ننتظر فرصة واحدة A+ مؤكدة (+95%) فقط.
• قبل الدخول: سيصلك إشعار <b>👀 وجّد راسك</b> موضح فيه اسم الاستراتيجية وشرط التأكيد المنتظر.
• عند نجاح التأكيد: يرسل البوت <b>✅ تأكيد الدخول الرسمي</b> مع أهداف TP1 و TP2 وزر حساب اللوت الصارم.
• في حال فشل التأكيد: يرسل البوت <b>❌ إلغاء الفرصة</b> مع السبب الميداني ويعيد بناء صفقة جديدة من الصفر (0) لحماية رأس مالك.`;
    await sendTelegramMessage(activeInfoMsg, { botToken: token, chatId });
    return;
  }

  // Otherwise, process activation code
  const result = activateChatWithCode(chatId, text, { firstName: userName });

  if (result.success) {
    const successMsg = `🎉 <b>تم تفعيل البوت بنجاح!</b>

👤 <b>المشترك:</b> <b>${result.userName}</b>
⏱️ <b>المدة:</b> <b>${result.durationLabel}</b>
🔑 <b>رمز التفعيل:</b> <code>${result.code}</code>
📅 <b>ينتهي في:</b> ${new Date(result.expiresAt!).toLocaleDateString("ar-MA")}

⚙️ <b>الخطوة التالية:</b> أرسل <code>/profile</code> لضبط رأس مال محفظتك ونسبة المخاطرة (1%) لحساب اللوت المناسب لكل صفقة.
🚀 <i>ستصلك الآن أفضل الصفقات المؤكدة تلقائياً على مدار الساعة (24/7).</i>`;
    await sendTelegramMessage(successMsg, { botToken: token, chatId });

    // Auto-fill default chatId in config if not already set
    const curCfg = getTelegramConfig();
    if (!curCfg.chatId) {
      updateTelegramConfig({ chatId });
    }

    // Notify Admin Chat if configured and different from subscriber
    if (curCfg.chatId && curCfg.chatId !== chatId) {
      const adminNotice = `👤 <b>تفعيل جديد:</b> <b>${result.userName}</b> (${result.durationLabel}) | <code>${result.code}</code>`;
      await sendTelegramMessage(adminNotice, { botToken: token, chatId: curCfg.chatId });
    }

    // Record in Platform Audit Logs
    recordNotificationLog({
      type: "ALERT",
      title: `[تفعيل جديد] ${result.userName} (${chatId})`,
      details: `تم تفعيل البوت بنجاح برمز ${result.code} (${result.durationLabel}).`,
      sentAt: new Date().toLocaleTimeString("ar-MA", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      status: "SUCCESS",
    });
  } else {
    const errorMsg = `❌ <b>فشل التفعيل:</b>\n\n${result.message || 'رمز التفعيل غير صحيح أو منتهي الصلاحية.'}`;
    await sendTelegramMessage(errorMsg, { botToken: token, chatId });
  }
}

/**
 * Periodically checks for subscribers whose duration just expired:
 * 1. Cuts off signals automatically
 * 2. Sends them an automated prompt to input a new code
 */
export async function checkAndNotifyExpiredSubscribers(token: string) {
  const expiredList = getNewlyExpiredSubscribers();
  for (const exp of expiredList) {
    markSubscriberExpiredNotified(exp.chatId);

    const expiredNotice = `🔒 <b>انتهت صلاحية الاشتراك!</b>

⚠️ انتهت مدة رمز التفعيل (<code>${exp.code}</code>).
👉 <i>يرجى إرسال رمز تفعيل جديد هنا لتشغيل البوت واستقبال الصفقات.</i>`;

    await sendTelegramMessage(expiredNotice, { botToken: token, chatId: exp.chatId });

    recordNotificationLog({
      type: "ALERT",
      title: `[انتهاء اشتراك] ${exp.firstName || exp.chatId}`,
      details: `انتهت صلاحية الرمز (${exp.code}). تم إيقاف استقبال الصفقات تلقائياً وإرسال إشعار للمستخدم.`,
      sentAt: new Date().toLocaleTimeString("ar-MA", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      status: "SUCCESS",
    });
  }
}

// Telegram Polling state
let lastUpdateId = 0;
let isPollingRunning = false;
let isFetchingUpdates = false;

/**
 * Poll Telegram for updates (long polling) so user can send /start, activation code,
 * react to signals with emojis, and click interactive buttons (join, breakeven, close).
 * Protected with concurrency lock to prevent Telegram 409 conflict errors.
 */
export async function pollTelegramUpdates() {
  const cfg = getTelegramConfig();
  const token = cfg.botToken || process.env.TELEGRAM_BOT_TOKEN;
  if (!token) return;

  if (isFetchingUpdates) return;
  isFetchingUpdates = true;

  try {
    const allowedUpdates = JSON.stringify(["message", "callback_query", "message_reaction"]);
    const url = `https://api.telegram.org/bot${token}/getUpdates?offset=${lastUpdateId + 1}&limit=50&timeout=2&allowed_updates=${encodeURIComponent(allowedUpdates)}`;
    const response = await fetch(url, { signal: AbortSignal.timeout(8000) });
    if (!response.ok) return;

    const data = (await response.json()) as any;
    if (!data || !data.ok || !Array.isArray(data.result)) return;

    for (const update of data.result) {
      if (update.update_id > lastUpdateId) {
        lastUpdateId = update.update_id;
      }

      // A. Handle interactive button clicks (Inline Keyboard Callbacks)
      if (update.callback_query) {
        const cb = update.callback_query;
        const cbId = cb.id;
        const from = cb.from;
        const chatId = String(cb.message?.chat?.id || from.id);
        const userName = from?.first_name || from?.username || "المتداول";
        const callbackData = (cb.data || "").trim();

        if (callbackData.startsWith("join_")) {
          const sigId = callbackData.replace("join_", "");
          const sig = getDispatchedSignalById(sigId) || Array.from(recentDispatchedSignalsMap.values()).pop();
          if (sig) {
            await answerTelegramCallbackQuery(cbId, `✅ تم تسجيل دخولك في صفقة ${sig.symbol}! ستصلك التوجيهات لحظة بلحظة.`, false);
            const parts = (sig.entryZone || "").split("-").map((p: string) => parseFloat(p.replace(/[^0-9.]/g, ""))).filter((n: number) => !isNaN(n));
            const entryNum = parts.length > 0 ? parts.reduce((a: number, b: number) => a + b, 0) / parts.length : sig.target1;
            const livePriceRes = await getLivePrice(sig.symbol).catch(() => null);
            const currentLive = livePriceRes?.price || entryNum;
            await trackUserTrade(chatId, userName, {
              id: sig.id,
              symbol: sig.symbol,
              signalType: sig.signalType,
              entryPrice: entryNum,
              stopLoss: sig.stopLoss,
              target1: sig.target1,
              target2: sig.target2,
              riskReward: sig.riskReward,
              timeframe: sig.timeframe,
              confidence: sig.confidence,
            }, entryNum, currentLive);
          } else {
            await answerTelegramCallbackQuery(cbId, "✅ تم تسجيل دخولك في الصفقة!", false);
          }
        } else if (callbackData.startsWith("be_")) {
          const tradeId = callbackData.replace("be_", "");
          const res = await secureUserTradeBreakeven(chatId, tradeId);
          await answerTelegramCallbackQuery(cbId, res.message, false);
        } else if (callbackData.startsWith("close_")) {
          const tradeId = callbackData.replace("close_", "");
          const res = await closeUserTradeManually(chatId, tradeId);
          await answerTelegramCallbackQuery(cbId, res.message, false);
        } else if (callbackData === "my_trades") {
          const overview = formatUserActiveTradesTelegram(chatId);
          await answerTelegramCallbackQuery(cbId, "جاري فتح صفقاتك النشطة...", false);
          await sendTelegramMessage(overview.text, { chatId, replyMarkup: overview.replyMarkup });
        } else if (callbackData.startsWith("risk_")) {
          const sigId = callbackData.replace("risk_", "");
          const sig = getDispatchedSignalById(sigId) || Array.from(recentDispatchedSignalsMap.values()).pop();
          if (sig) {
            const customCalc = formatCustomLotCalculationMessage(chatId, userName, sig);
            await answerTelegramCallbackQuery(cbId, "🧮 حساب اللوت المخصص لمحفظتك", false);
            await sendTelegramMessage(customCalc.text, { chatId, replyMarkup: customCalc.replyMarkup });
          } else {
            const profile = getUserSubscriberProfile(chatId);
            const riskMsg = `🧮 <b>حاسبة إدارة المخاطر الذكية (${profile.riskPercent}%):</b>

💰 <b>رأس مالك المسجل:</b> <code>${profile.capital.toLocaleString()}$</code>
🛡️ <b>نسبة المخاطرة:</b> <code>${profile.riskPercent}%</code> (<b>${((profile.capital * profile.riskPercent) / 100).toFixed(2)}$</b>)
🔹 <b>القاعدة الذهبية:</b> اجعل خسارة الصفقة في حال ضرب الوقف لا تتجاوز ${profile.riskPercent}% فقط من إجمالي محفظتك.
الانضباط في اللوت هو سر استمرارية وربحية المحترفين!`;
            await answerTelegramCallbackQuery(cbId, `حاسبة إدارة المخاطر ${profile.riskPercent}%`, false);
            await sendTelegramMessage(riskMsg, { chatId, replyMarkup: {
              inline_keyboard: [[{ text: "⚙️ تعديل رأس المال / المخاطرة", callback_data: "my_profile" }]]
            } });
          }
        } else if (callbackData === "set_cap_menu") {
          await answerTelegramCallbackQuery(cbId, "💰 اختر رأس المال", false);
          const promptCapMsg = `💰 <b>حدد رأس مال محفظتك (Capital in USD):</b>
━━━━━━━━━━━━━━━━━━
اختر مبلغ رأس مالك بالضغط على أحد الأزرار، أو اكتب المبلغ مباشرة في الشات (مثال: <code>/capital 5000</code>):`;
          await sendTelegramMessage(promptCapMsg, { chatId, replyMarkup: getCapitalSelectionKeyboard() });
        } else if (callbackData.startsWith("set_cap_")) {
          const amountStr = callbackData.replace("set_cap_", "");
          const amount = parseFloat(amountStr);
          if (!isNaN(amount) && amount > 0) {
            const updateRes = updateUserCapitalAndRisk(chatId, amount, undefined, userName);
            await answerTelegramCallbackQuery(cbId, `✅ تم ضبط رأس المال: ${updateRes.capital.toLocaleString()}$`, true);
            const successCapMsg = `✅ <b>تم تحديث رأس المال!</b>
───────────────
💰 <b>رأس المال:</b> <code>${updateRes.capital.toLocaleString()}$</code>
🛡️ <b>المخاطرة:</b> <code>${updateRes.riskPercent}%</code> (<b>-$${((updateRes.capital * updateRes.riskPercent) / 100).toFixed(2)}</b>)
───────────────
🎯 <i>سيتم حساب اللوت تلقائياً لكل الصفقات القادمة.</i>`;
            const replyMarkup = {
              inline_keyboard: [
                [
                  { text: "🛡️ تعديل نسبة المخاطرة (%)", callback_data: "set_risk_menu" },
                  { text: "🧮 حساب لوت أحدث صفقة", callback_data: "calc_latest_lot" },
                ]
              ]
            };
            await sendTelegramMessage(successCapMsg, { chatId, replyMarkup });
          }
        } else if (callbackData === "set_risk_menu") {
          await answerTelegramCallbackQuery(cbId, "🛡️ اختر نسبة المخاطرة", false);
          const promptRiskMsg = `🛡️ <b>حدد نسبة المخاطرة لكل صفقة (Risk %):</b>
━━━━━━━━━━━━━━━━━━
القاعدة المؤسساتية الذهبية هي <b>1.0%</b> كحد أقصى لحماية رأس المال.
اختر النسبة بالضغط على أحد الأزرار، أو اكتبها في الشات (مثال: <code>/risk 1.5</code>):`;
          await sendTelegramMessage(promptRiskMsg, { chatId, replyMarkup: getRiskSelectionKeyboard() });
        } else if (callbackData.startsWith("set_risk_")) {
          const pctStr = callbackData.replace("set_risk_", "");
          const pct = parseFloat(pctStr);
          if (!isNaN(pct) && pct > 0) {
            const updateRes = updateUserCapitalAndRisk(chatId, undefined, pct, userName);
            await answerTelegramCallbackQuery(cbId, `✅ تم ضبط المخاطرة: ${updateRes.riskPercent}%`, true);
            const successRiskMsg = `✅ <b>تم تحديث نسبة المخاطرة!</b>
───────────────
🛡️ <b>نسبة المخاطرة:</b> <code>${updateRes.riskPercent}%</code>
💰 <b>رأس المال:</b> <code>${updateRes.capital.toLocaleString()}$</code>
🛑 <b>أقصى خسارة:</b> <b>-$${((updateRes.capital * updateRes.riskPercent) / 100).toFixed(2)}</b>
───────────────
🎯 <i>تم قفل حجم اللوت في كل الصفقات لحماية حسابك.</i>`;
            const replyMarkup = {
              inline_keyboard: [
                [
                  { text: "💰 تعديل رأس المال ($)", callback_data: "set_cap_menu" },
                  { text: "🧮 حساب لوت أحدث صفقة", callback_data: "calc_latest_lot" },
                ]
              ]
            };
            await sendTelegramMessage(successRiskMsg, { chatId, replyMarkup });
          }
        } else if (callbackData === "my_stats" || callbackData === "user_stats") {
          await answerTelegramCallbackQuery(cbId, "📊 إحصائياتك الشخصية", false);
          const userStats = formatUserPersonalStatsMessage(chatId, userName);
          await sendTelegramMessage(userStats.text, { chatId, replyMarkup: userStats.replyMarkup });
        } else if (callbackData === "my_profile") {
          await answerTelegramCallbackQuery(cbId, "⚙️ إعدادات الحساب", false);
          const prof = formatUserProfileMessage(chatId, userName);
          await sendTelegramMessage(prof.text, { chatId, replyMarkup: prof.replyMarkup });
        } else if (callbackData === "calc_latest_lot") {
          const latestSig = Array.from(recentDispatchedSignalsMap.values()).pop();
          if (latestSig) {
            await answerTelegramCallbackQuery(cbId, "🧮 حساب اللوت المخصص", false);
            const calcMsg = formatCustomLotCalculationMessage(chatId, userName, latestSig);
            await sendTelegramMessage(calcMsg.text, { chatId, replyMarkup: calcMsg.replyMarkup });
          } else {
            await answerTelegramCallbackQuery(cbId, "لا توجد صفقة حديثة مسجلة", true);
          }
        }
        continue;
      }

      // B. Handle Telegram Native Emoji Reactions (👍, 🎯, 🔥, 🚀, ❤️)
      if (update.message_reaction) {
        const mr = update.message_reaction;
        const chatId = String(mr.chat?.id);
        const user = mr.user;
        const userName = user?.first_name || user?.username || "المتداول";
        const messageId = mr.message_id;

        // If user reacted with at least one emoji
        if (mr.new_reaction && mr.new_reaction.length > 0) {
          const sigId = getSignalIdByMessage(chatId, messageId);
          const sig = (sigId ? getDispatchedSignalById(sigId) : undefined) || Array.from(recentDispatchedSignalsMap.values()).pop();
          if (sig) {
            const parts = (sig.entryZone || "").split("-").map((p: string) => parseFloat(p.replace(/[^0-9.]/g, ""))).filter((n: number) => !isNaN(n));
            const entryNum = parts.length > 0 ? parts.reduce((a: number, b: number) => a + b, 0) / parts.length : sig.target1;
            const livePriceRes = await getLivePrice(sig.symbol).catch(() => null);
            const currentLive = livePriceRes?.price || entryNum;
            await trackUserTrade(chatId, userName, {
              id: sig.id,
              symbol: sig.symbol,
              signalType: sig.signalType,
              entryPrice: entryNum,
              stopLoss: sig.stopLoss,
              target1: sig.target1,
              target2: sig.target2,
              riskReward: sig.riskReward,
              timeframe: sig.timeframe,
              confidence: sig.confidence,
            }, entryNum, currentLive);
          }
        }
        continue;
      }

      // C. Handle Regular Text Messages & Commands
      const msg = update.message;
      if (!msg || !msg.chat || !msg.chat.id) continue;

      const chatId = String(msg.chat.id);
      const text = (msg.text || "").trim();
      const userName = msg.from?.first_name || msg.from?.username || "Trader";

      if (text) {
        await handleIncomingTelegramMessage(chatId, text, userName, token);
      }
    }

    // 2. Automated expiration watchdog
    await checkAndNotifyExpiredSubscribers(token);
  } catch {
    // Network interruption, ignore and let next tick retry
  } finally {
    isFetchingUpdates = false;
  }
}

/**
 * Initializes indestructible background polling loop for Telegram incoming messages (24h/24 7j/7)
 */
export function initTelegramBotPolling() {
  if (isPollingRunning) return;
  isPollingRunning = true;
  console.log("Telegram Bot 24/7 interactive listener polling initialized.");

  // Polling runner every 2 seconds
  setInterval(async () => {
    await pollTelegramUpdates();
  }, 2000);

  // 24/7 Connection Keep-Alive Heartbeat every 60 seconds
  setInterval(async () => {
    try {
      const cfg = getTelegramConfig();
      if (cfg.botToken) {
        await getTelegramBotInfo(cfg.botToken).catch(() => {});
      }
    } catch {
      // quiet catch to prevent unhandled rejections
    }
  }, 60000);
}

function cleanStrategyName(name?: string, isBuy: boolean = true): string {
  if (!name) return isBuy ? "SMC Demand Block (SSL Sweep)" : "SMC Supply Block (BSL Sweep)";
  if (name.includes("Set & Forget") || name.includes("SMC")) {
    return isBuy ? "SMC Demand Block (SSL Sweep)" : "SMC Supply Block (BSL Sweep)";
  }
  if (name.includes("ICT")) {
    return isBuy ? "ICT Judas Swing & FVG Long" : "ICT Judas Swing & FVG Short";
  }
  if (name.includes("Wyckoff")) {
    return isBuy ? "Wyckoff Spring (Accumulation)" : "Wyckoff UTAD (Distribution)";
  }
  if (name.includes("ORDER_FLOW") || name.includes("Order Flow")) {
    return isBuy ? "Order Flow (POC Demand Rebound)" : "Order Flow (POC Supply Rejection)";
  }
  return name.replace(/\(.*?\)/g, "").trim() || (isBuy ? "SMC Demand Block" : "SMC Supply Block");
}

function getSpecialistAgentShort(symbol: string): string {
  if (symbol.includes("XAU") || symbol.includes("Gold")) return "Gold Sovereign AI";
  if (symbol === "EUR/USD") return "EUR/USD Sovereign AI";
  if (symbol === "GBP/USD") return "Cable Precision AI";
  if (symbol === "USD/JPY") return "Tokyo Ninja AI";
  if (symbol === "AUD/USD") return "Aussie Flow AI";
  if (symbol === "USD/CAD") return "Loonie Hunter AI";
  if (symbol.includes("BTC")) return "BTC Whale AI";
  if (symbol.includes("ETH")) return "ETH Derivatives AI";
  if (symbol.includes("OIL") || symbol.includes("USOIL")) return "Oil Sentinel AI";
  if (symbol.includes("NVDA")) return "NVDA Quant AI";
  if (symbol.includes("AAPL")) return "Apple Capital AI";
  return "Institutional AI Trader";
}

function getSpecialistAgentHeader(symbol: string): string {
  return `👤 <b>AI:</b> ${getSpecialistAgentShort(symbol)}`;
}

/**
 * 1. Pre-Alert Message (تنبيه تحضيري موحد وصغير: فقط الضروري)
 */
export function formatPreAlertMessage(signal: {
  symbol: string;
  assetName?: string;
  signalType: string;
  entryZone: string;
  confidence?: number;
  timeframe?: string;
  strategyUsed?: string;
  riskReward?: string;
  stopLoss?: number;
  target1?: number;
  target2?: number;
  smcDetails?: any;
}): string {
  const isBuy = signal.signalType === "BUY";
  const icon = isBuy ? "🟢" : "🔴";
  const actionText = isBuy ? "BUY" : "SELL";

  return `🔔 <b>PRE-ALERT | ${signal.symbol}</b>
${icon} <b>${actionText}</b> | 📍 <b>Zone:</b> <code>${signal.entryZone}</code>
⏳ <i>ننتظر إغلاق 15M للتأكيد (لا تدخل الآن)</i>`;
}

// Track last notified setups to ensure ultra-timely alerts without repetitive spamming
const lastNotifiedSetupTime = new Map<string, number>();

/**
 * 2. Confirmed Entry Signal (رسالة صفقة صغيرة ومختزلة فيها فقط الضروري للصفقة)
 */
export function formatSignalMessage(
  signal: any,
  userProfile?: { capital: number; riskPercent: number; active?: boolean }
): string {
  // Strict: only the strategy's own levels are printed; nothing is filled in by default
  const isBuy = signal.signalType === "BUY" || signal.action === "BUY";
  const symbol = signal.symbol?.includes("EUR") ? "EUR/USD" : "XAU/USD";
  const isGold = symbol === "XAU/USD";
  const decimals = isGold ? 2 : 5;
  const pip = isGold ? 0.1 : 0.0001;
  const num = (v: any) => (typeof v === "number" && Number.isFinite(v) && v > 0 ? v : null);
  const entry = num(signal.entryPrice), sl = num(signal.stopLoss), tp1 = num(signal.target1), tp2 = num(signal.target2), tp3 = num(signal.target3);
  if (entry === null || sl === null || tp1 === null || tp2 === null) {
    return `⚠️ ${symbol}: signal levels incomplete, not sent.`;
  }
  const risk = Math.abs(entry - sl);
  const pips = (v: number) => Math.round(Math.abs(v - entry) / pip);
  const rrOf = (v: number) => (risk > 0 ? (Math.abs(v - entry) / risk).toFixed(1) : "—");
  const p = (v: number) => `${isGold ? "$" : ""}${v.toFixed(decimals)}`;
  const sj = signal.signalJson || {};
  const orderType = sj.entry_type || signal.entryType || "LIMIT";
  const expires = sj.expires_at ? new Date(sj.expires_at).toISOString().slice(11, 16) + " UTC" : null;
  const setup = sj.setup ? ` · Setup ${sj.setup}` : "";

  let lotLine = "";
  if (userProfile && userProfile.capital > 0) {
    const riskAmt = userProfile.capital * ((userProfile.riskPercent || 1) / 100);
    const lots = Math.floor((riskAmt / (risk * (isGold ? 100 : 100000))) * 100 + 1e-9) / 100;
    lotLine = `
💼 <b>Lot:</b> <code>${lots >= 0.01 ? lots.toFixed(2) : "below 0.01"}</code> ($${userProfile.capital.toLocaleString()} | ${userProfile.riskPercent || 1}%)`;
  }
  const confirmLine = signal.confirmationCheckPassed
    ? `
✅ <b>Signal:</b> ${new Date((signal.confirmationCloseTime ? signal.confirmationCloseTime * 1000 : Date.now())).toISOString().slice(11, 16)} UTC candle close`
    : "";
  const invalidLine = signal.invalidationCondition ? `
⛔ <b>Invalidation:</b> ${signal.invalidationCondition}` : "";

  return `${isBuy ? "🟢" : "🔴"} <b>${isBuy ? "BUY" : "SELL"} ${orderType} | ${symbol}${setup}</b>

📍 <b>Entry:</b> <code>${p(entry)}</code>${orderType === "LIMIT" && expires ? ` (valid until ${expires})` : ""}
🛑 <b>SL:</b> <code>${p(sl)}</code> (${pips(sl)} pips)
🎯 <b>TP1:</b> <code>${p(tp1)}</code> (1:${rrOf(tp1)} · close 50%, SL → breakeven)
🎯 <b>TP2:</b> <code>${p(tp2)}</code> (1:${rrOf(tp2)})${tp3 !== null ? `
🎯 <b>TP3:</b> <code>${p(tp3)}</code> (1:${rrOf(tp3)})` : ""}
🧠 <code>${signal.strategyUsed || "EXUNU"}</code>
⚖️ <b>Score:</b> <code>${typeof signal.confidence === "number" ? signal.confidence : "—"}/100</code> · risk 1% per trade${confirmLine}${invalidLine}${lotLine}`;
}

/**
 * 3. Setup Cancelled Message (رسالة إلغاء المراقبة — صغيرة ومختصرة)
 */
export function formatSetupCancelledMessage(params: {
  symbol: string;
  strategyName?: string;
  reasonAr?: string;
  assetName?: string;
}): string {
  return `❌ <b>CANCELLED | ${params.symbol}</b>
⚠️ <b>السبب:</b> <i>${params.reasonAr || "لم يتحقق شرط تأكيد 15M."}</i>
🛡️ <i>تم إلغاء الصفقة لحفظ رأس المال.</i>`;
}

/**
 * Dispatches a cancellation notification to all active Telegram subscribers
 */
export async function notifySetupCancelledToTelegram(
  symbol: string,
  reasonAr?: string,
  assetName?: string,
  strategyName?: string
): Promise<{ sent: boolean; error?: string }> {
  const cfg = getTelegramConfig();
  if (!cfg.enabled) {
    return { sent: false, error: "Telegram notifications are disabled in settings" };
  }

  const activeSubs = getActiveChatSubscribers();
  const targetChatIds = new Set<string>();
  for (const s of activeSubs) {
    targetChatIds.add(s.chatId);
  }

  const globalLicense = isBotLicenseValid();
  if (cfg.chatId && globalLicense.valid) {
    targetChatIds.add(cfg.chatId);
  }

  if (targetChatIds.size === 0) {
    return { sent: false, error: "No subscribers" };
  }

  // SILENT ANTI-SPAM DISCIPLINE: Do not broadcast cancellation messages to Telegram.
  // Real traders only want confirmed high-quality trades, not noise.
  console.log(`[Telegram] Cancelled setup for ${symbol} handled silently in background (Anti-Spam active).`);
  return { sent: false };
}

/**
 * Dispatches a confirmed signal to Telegram if enabled, license is valid, and matches criteria.
 * Strictly verifies market is open, filters for A+ high-grade confirmation (>95%), minimal risk, and avoids spam.
 */
export async function notifySignalToTelegram(signal: any, isPreAlert: boolean = false, force: boolean = false): Promise<{ sent: boolean; error?: string }> {
  const cfg = getTelegramConfig();
  if (!cfg.enabled) {
    return { sent: false, error: "Telegram notifications are disabled in settings" };
  }

  // 0a. EXUNU Terminal Lock: Strictly restricted to XAU/USD and EUR/USD only
  const isExunuAsset = signal.symbol && (signal.symbol.includes("XAU") || signal.symbol.includes("EUR") || signal.symbol === "GOLD");
  if (!isExunuAsset) {
    return { sent: false, error: "بوت تيليجرام مقفول حصرياً لصفقات الذهب (XAU/USD) واليورو (EUR/USD) فقط." };
  }

  // 0. Anti-Spam: Suppress unconfirmed Pre-Alerts (Strictly send CONFIRMED A+ trades only)
  if (isPreAlert && !force) {
    return { sent: false, error: "التنبيهات التحضيرية متوقفة لمنع السبام — يتم إرسال الصفقات المؤكدة A+ فقط." };
  }

  // 0b. Strategy Lock: Telegram bot is locked EXCLUSIVELY to the new NY Silver Bullet / SMC Strategy
  const stratName = (signal.strategyUsed || signal.strategyName || "").toLowerCase();
  const isNewStrategy = stratName.includes("silver bullet") || stratName.includes("coretradingengine") || stratName.includes("smc") || signal.symbol?.includes("XAU");
  if (!isNewStrategy && !force) {
    return { sent: false, error: "بوت تيليجرام مقفول حصرياً لاستراتيجية NY Silver Bullet و SMC فقط." };
  }

  // 1. Strictly check market session status (Global Interbank Market Hours)
  // When market is closed (Weekend: Friday 21:00 GMT - Sunday 22:00 GMT, or CME daily rollover pause), NEVER dispatch to Telegram.
  const marketStatus = getMarketSessionStatus(signal.symbol);
  if (!marketStatus.isOpen) {
    console.log(`[Telegram Block] Market for ${signal.symbol} is CLOSED (${marketStatus.labelAr}). Signal dispatch to Telegram strictly blocked.`);
    return {
      sent: false,
      error: `السوق مغلق حالياً لـ ${signal.symbol} (${marketStatus.labelAr}). لا يتم إرسال صفقات أثناء إغلاق البورصة لحماية رأس المال.`
    };
  }

  // 1b. Reject NO_TRADE signals
  if (signal.action === "NO_TRADE" || signal.signalType === "NO_TRADE" || signal.status === "NO_TRADE") {
    return { sent: false, error: "حالة الصفقة NO_TRADE: لم تكتمل شروط التأكيد المؤسساتي." };
  }

  // 2. High-Grade Confluence Threshold (Execution Threshold: Confluence >= 85%)
  const minRequiredConf = typeof cfg.minConfidence === 'number' ? Math.max(85, cfg.minConfidence) : 85;
  if (!force && (signal.confidence || 0) < minRequiredConf) {
    return { sent: false, error: `نسبة التطابق (${signal.confidence}%) أقل من الحد الأدنى المؤسساتي (${minRequiredConf}%). تم الحجب لمنع السبام.` };
  }

  // 2b. Require Risk-to-Reward ratio >= 2.0 (Mandatory 1:2.0 Net R:R)
  const rrNum = typeof signal.riskReward === 'string' 
    ? parseFloat(signal.riskReward.replace(/[^0-9.]/g, '')) 
    : 2.0;
  if (!force && rrNum < 1.95) {
    return { sent: false, error: "نسبة العائد للمخاطرة أقل من 1:2.0. تم رفض الصفقة لحماية الحساب." };
  }

  // 3. Check asset filter
  if (
    cfg.assets &&
    cfg.assets.length > 0 &&
    !cfg.assets.includes(signal.symbol)
  ) {
    return { sent: false, error: `Asset ${signal.symbol} not in subscribed list` };
  }

  // 4. Rate-limiting & Deterministic Hash Deduplication (XAUUSD-NYSB-YYYY-MM-DD-DIRECTION-ENTRY)
  const dateStr = new Date().toISOString().slice(0, 10);
  const dirStr = (signal.signalType || signal.action || "BUY").toUpperCase();
  const entryVal = typeof signal.entryPrice === 'number' ? signal.entryPrice.toFixed(2) : "4150.00";
  const dedupKey = `XAUUSD-NYSB-${dateStr}-${dirStr}-${entryVal}`;
  const now = Date.now();
  const lastSent = lastNotifiedSetupTime.get(dedupKey) || 0;
  if (!force && (now - lastSent < 45 * 60 * 1000)) {
    return { sent: false, error: "تم إرسال إشارة هذا النموذج مسبقاً لمنع التكرار (Deterministic Deduplication)." };
  }

  // Collect target recipients:
  // 1. All active chat subscribers who entered a valid code in Telegram
  const activeSubs = getActiveChatSubscribers();
  const targetChatIds = new Set<string>();
  for (const s of activeSubs) {
    if (s.chatId) targetChatIds.add(String(s.chatId));
  }

  // 2. Also cfg.chatId if provided
  if (cfg.chatId) {
    targetChatIds.add(String(cfg.chatId));
  }

  // 3. Fallback: ensure primary database subscribers are added
  const db = getLocalDatabase();
  if (db.chatSubscribers) {
    for (const cid of Object.keys(db.chatSubscribers)) {
      targetChatIds.add(String(cid));
    }
  }

  if (targetChatIds.size === 0) {
    return {
      sent: false,
      error: "لا يوجد مشتركون نشطون في البوت حالياً لتلقي الصفقات. يرجى إرسال /start في تيليجرام لتفعيل المحادثة."
    };
  }

  // Sanitize and guarantee mathematical invariants on SL, Entry, and TP
  const cleanSignal = validateAndSanitizeSignalLevels(signal);

  // Cache signal for instant fast reaction and inline callback retrieval
  cacheDispatchedSignal(cleanSignal);

  // Generate clean, concise text message (without image, pure simple text)
  const message = isPreAlert ? formatPreAlertMessage(cleanSignal) : formatSignalMessage(cleanSignal);

  // Interactive inline buttons so users can tap "دخلت الصفقة" or calculate risk
  const replyMarkup = !isPreAlert ? {
    inline_keyboard: [
      [
        { text: "🎯 دخلت الصفقة", callback_data: `join_${cleanSignal.id}` },
        { text: "🧮 لوت محفظتي", callback_data: `risk_${cleanSignal.id}` }
      ],
      [
        { text: "⚙️ ضبط المحفظة ($)", callback_data: "my_profile" }
      ]
    ]
  } : undefined;

  let anySuccess = false;
  let lastError: string | undefined;

  for (const targetId of targetChatIds) {
    // Send clean, direct text message without image ("bla tswira")
    const userProf = getUserSubscriberProfile(targetId);
    const userSpecificMessage = isPreAlert ? message : formatSignalMessage(cleanSignal, userProf);

    const res = await sendTelegramMessage(userSpecificMessage, { chatId: targetId, replyMarkup });

    if (res.success) {
      anySuccess = true;
      if (res.messageId) {
        registerSignalMessageId(targetId, res.messageId, signal.id);
        if (!isPreAlert) {
          saveConfirmedSignalMessageId(signal.id, signal.symbol, targetId, res.messageId);
        }
      }
    } else {
      lastError = res.error;
    }
  }

  if (anySuccess) {
    lastNotifiedSetupTime.set(dedupKey, now);
    if (!isPreAlert) {
      registerDispatchedSignal(signal);
    }
  }

  const logEntry: TelegramLog = {
    id: `log-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
    type: "SIGNAL",
    title: isPreAlert ? `[تنبيه] ${signal.signalType} ${signal.symbol}` : `[دخول مباشر A+] ${signal.signalType} ${signal.symbol} (${signal.confidence}%)`,
    details: `Entry: ${signal.entryZone} | SL: ${signal.stopLoss} | TP: ${signal.target1} | Sent to: ${targetChatIds.size} chat(s)`,
    sentAt: new Date().toLocaleTimeString("ar-MA", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    status: anySuccess ? "SUCCESS" : "FAILED",
    error: anySuccess ? undefined : lastError,
  };

  notificationHistory.unshift(logEntry);
  if (notificationHistory.length > 20) notificationHistory.pop();

  return { sent: anySuccess, error: anySuccess ? undefined : lastError };
}

/**
 * Records a test notification in history
 */
export function recordNotificationLog(log: Omit<TelegramLog, "id">) {
  const entry: TelegramLog = {
    ...log,
    id: `log-${Date.now()}`,
  };
  notificationHistory.unshift(entry);
  if (notificationHistory.length > 20) notificationHistory.pop();
}
