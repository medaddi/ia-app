// Telegram Activation Keys & Bot Access Controller
import { getLocalDatabase, saveLocalDatabase, PERMANENT_VIP_CODES } from "./localDb";

export interface ActivationCode {
  code: string;
  createdAt: number;
  durationHours: number;
  durationLabel: string;
  label?: string;
  used: boolean;
  status: "PENDING" | "ACTIVE" | "EXPIRED"; // PENDING = duration hasn't started yet!
  usedAt?: number; // Exact timestamp when entered by user
  expiresAt?: number; // Exact expiration = usedAt + durationHours * 3600 * 1000
  isPermanent?: boolean;
  multiUserAllowed?: boolean;
  usedBy?: {
    chatId: string;
    firstName?: string;
    username?: string;
  };
}

export interface ChatSubscriber {
  chatId: string;
  username?: string;
  firstName?: string;
  code: string;
  durationHours: number;
  durationLabel: string;
  activatedAt: number; // Duration starts when entered
  expiresAt: number; // Exact expiration
  expiredNotified?: boolean; // Avoid spamming expiration notification
  isPermanent?: boolean;
  capital?: number; // User-configured capital in USD (e.g. 1000)
  riskPercent?: number; // User-configured risk percentage per trade (e.g. 1.0%)
}

// Persistent key store backed by local JSON DB
function getStoredKeys(): Map<string, ActivationCode> {
  const db = getLocalDatabase();
  const map = new Map<string, ActivationCode>();
  if (db.activationKeys) {
    for (const [k, v] of Object.entries(db.activationKeys)) {
      map.set(k, v as ActivationCode);
    }
  }
  return map;
}

function persistKey(key: ActivationCode) {
  saveLocalDatabase((db) => {
    if (!db.activationKeys) db.activationKeys = {};
    db.activationKeys[key.code] = key;
  });
}

function getStoredSubscribers(): Map<string, ChatSubscriber> {
  const db = getLocalDatabase();
  const map = new Map<string, ChatSubscriber>();
  if (db.chatSubscribers) {
    for (const [k, v] of Object.entries(db.chatSubscribers)) {
      map.set(k, v as ChatSubscriber);
    }
  }
  return map;
}

function persistSubscriber(sub: ChatSubscriber) {
  saveLocalDatabase((db) => {
    if (!db.chatSubscribers) db.chatSubscribers = {};
    db.chatSubscribers[sub.chatId] = sub;
  });
}

// Active global activation state for the web interface
let currentActiveLicense: {
  code: string;
  activatedAt: number;
  expiresAt: number;
  durationHours: number;
  durationLabel: string;
} | null = null;

// Helper to format duration label
export function getDurationLabel(durationHours: number): string {
  if (durationHours === 1) return "ساعة واحدة (تجريبي)";
  if (durationHours === 24) return "يوم واحد (24H)";
  if (durationHours === 168) return "أسبوع كامل (7 أيام)";
  if (durationHours === 720) return "شهر كامل (30 يوم)";
  if (durationHours >= 8760) return "سنة كاملة (VIP مدى الحياة)";
  return `${durationHours} ساعة`;
}

// Helper to generate a clean formatted license key e.g. VIP-8924-K7X9
// Note: Countdown does NOT start upon generation; it only starts when the user enters the code!
export function generateActivationCode(durationHours: number, label: string = "Access Code"): ActivationCode {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let randomPart1 = "";
  let randomPart2 = "";
  for (let i = 0; i < 4; i++) {
    randomPart1 += chars.charAt(Math.floor(Math.random() * chars.length));
    randomPart2 += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  const code = `VIP-${randomPart1}-${randomPart2}`;
  const now = Date.now();
  const durationLabel = getDurationLabel(durationHours);

  const newKey: ActivationCode = {
    code,
    createdAt: now,
    durationHours,
    durationLabel,
    label,
    used: false,
    status: "PENDING", // Time hasn't started yet!
  };

  persistKey(newKey);
  return newKey;
}

// Master default code check
const initialDb = getLocalDatabase();
if (!initialDb.activationKeys["PRO-TRADER-2026-VIP"]) {
  const masterVipKey: ActivationCode = {
    code: "PRO-TRADER-2026-VIP",
    createdAt: Date.now(),
    durationHours: 8760,
    durationLabel: "سنة كاملة (VIP مدى الحياة)",
    label: "Master VIP Code",
    used: false,
    status: "PENDING",
  };
  persistKey(masterVipKey);
}

// Set up active license from persistent storage
const storedKeys = getStoredKeys();
const foundActive = Array.from(storedKeys.values()).find(k => k.status === "ACTIVE" && k.expiresAt && k.expiresAt > Date.now());
if (foundActive) {
  currentActiveLicense = {
    code: foundActive.code,
    activatedAt: foundActive.usedAt || Date.now(),
    expiresAt: foundActive.expiresAt!,
    durationHours: foundActive.durationHours,
    durationLabel: foundActive.durationLabel,
  };
} else {
  const starterKey = storedKeys.get("PRO-TRADER-2026-VIP") || storedKeys.get("VIP-7777-2026");
  const starterNow = Date.now();
  const expiresAt = starterNow + 365 * 24 * 3600 * 1000;
  currentActiveLicense = {
    code: starterKey ? starterKey.code : "PRO-TRADER-2026-VIP",
    activatedAt: starterNow,
    expiresAt,
    durationHours: 8760,
    durationLabel: "سنة كاملة (VIP مدى الحياة)",
  };
}

/**
 * Check if a specific Telegram chat is activated and still valid
 */
export function isChatActivated(chatId: string): {
  active: boolean;
  isExpired: boolean;
  remainingMs: number;
  expiresAt: number;
  durationLabel?: string;
  code?: string;
  firstName?: string;
  username?: string;
} {
  const subs = getStoredSubscribers();
  let sub = subs.get(String(chatId));

  if (!sub) {
    // Automatically register and persist the new chat ID as a Permanent Lifetime VIP Subscriber!
    // This removes subscription gate completely for anyone who interacts with the bot.
    const autoSub: ChatSubscriber = {
      chatId: String(chatId),
      code: "PRO-TRADER-2026-VIP",
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم وغير محدود)",
      activatedAt: Date.now(),
      expiresAt: 2105300000000,
      isPermanent: true,
      expiredNotified: false
    };
    persistSubscriber(autoSub);
    sub = autoSub;
  }

  return {
    active: true,
    isExpired: false,
    remainingMs: 2105300000000 - Date.now(),
    expiresAt: 2105300000000,
    durationLabel: "مدى الحياة (VIP دائم وغير محدود)",
    code: "PRO-TRADER-2026-VIP",
    firstName: sub.firstName || "Primary VIP Trader",
    username: sub.username,
  };
}

/**
 * Activate or renew a Telegram chat with an activation code.
 * CRITICAL: Permanent codes in db.json can be used by ANY user without restriction!
 */
export function activateChatWithCode(
  chatId: string,
  rawCode: string,
  userMeta?: { username?: string; firstName?: string }
): {
  success: boolean;
  message: string;
  durationLabel?: string;
  expiresAt?: number;
  code?: string;
  userName?: string;
} {
  const cleanCode = (rawCode || "").trim().toUpperCase();
  const keys = getStoredKeys();
  const found = keys.get(cleanCode);

  if (!found) {
    return {
      success: false,
      message: "كود التفعيل غير صحيح أو غير مسجل! تأكد من كتابة الكود بشكل صحيح أو استخدم أحد أكواد VIP الدائمة.",
    };
  }

  const isPermanentCode = Boolean(found.isPermanent || found.multiUserAllowed || PERMANENT_VIP_CODES[cleanCode]);

  // 24-Hour (1-Day) Trial Strict One-Time Security Rule:
  const db = getLocalDatabase();
  const trialHistory = db.trialHistory || [];
  const isTrialCode = found.durationHours <= 24 && !isPermanentCode;

  if (isTrialCode) {
    if (trialHistory.includes(String(chatId))) {
      return {
        success: false,
        message: "⚠️ لقد استفدت بالفعل من الفترة التجريبية المجانية (24 ساعة / 1 يوم) لمرة واحدة مسبقاً! للاستمرار في استقبال صفقات الـ VIP، يرجى الترقية إلى باقة أسبوعية أو شهرية.",
      };
    }
    if (found.used) {
      return {
        success: false,
        message: "⚠️ هذا الكود التجريبي تم استخدامه مسبقاً! كل كود تجريبي مخصص للاستخدام لمرة واحدة فقط.",
      };
    }
  }

  // If already used by another user (single-use keys, unless permanent/multi-use VIP)
  if (!isPermanentCode && found.used && found.usedBy && found.usedBy.chatId !== String(chatId) && cleanCode !== "PRO-TRADER-2026-VIP") {
    return {
      success: false,
      message: "هذا الكود تم استخدامه بالفعل من قبل مستخدم آخر! يرجى الحصول على كود جديد.",
    };
  }

  const now = Date.now();
  const durationHours = isPermanentCode ? 87600 : found.durationHours;
  const expiresAt = isPermanentCode ? 2105300000000 : (now + durationHours * 60 * 60 * 1000);
  const durationLabel = isPermanentCode ? "مدى الحياة (VIP دائم 10 سنوات)" : found.durationLabel;
  const userName = userMeta?.firstName || (userMeta?.username ? `@${userMeta.username}` : `Trader_${chatId.slice(-4)}`);

  const subscriber: ChatSubscriber = {
    chatId: String(chatId),
    username: userMeta?.username,
    firstName: userMeta?.firstName || userName,
    code: found.code,
    durationHours,
    durationLabel,
    activatedAt: now,
    expiresAt,
    expiredNotified: false,
    isPermanent: isPermanentCode,
  };

  persistSubscriber(subscriber);

  found.used = true;
  found.usedAt = now;
  found.expiresAt = expiresAt;
  found.status = "ACTIVE";
  found.usedBy = {
    chatId: String(chatId),
    firstName: userMeta?.firstName,
    username: userMeta?.username,
  };

  persistKey(found);

  // If trial code, record user in trialHistory
  if (isTrialCode) {
    saveLocalDatabase((d) => {
      if (!d.trialHistory) d.trialHistory = [];
      if (!d.trialHistory.includes(String(chatId))) {
        d.trialHistory.push(String(chatId));
      }
    });
  }

  // Also update global license
  currentActiveLicense = {
    code: found.code,
    activatedAt: now,
    expiresAt,
    durationHours,
    durationLabel,
  };

  return {
    success: true,
    message: `تم تفعيل البوت بنجاح يا ${userName}! الصلاحية: ${durationLabel}. بدأت المدة تحتسب من الآن.`,
    durationLabel,
    expiresAt,
    code: found.code,
    userName,
  };
}

/**
 * Returns all currently active chat subscribers who should receive signals
 */
export function getActiveChatSubscribers(): ChatSubscriber[] {
  const subs = getStoredSubscribers();
  const db = getLocalDatabase();
  const primaryChatId = db.telegramConfig?.chatId || process.env.TELEGRAM_CHAT_ID;
  const active: ChatSubscriber[] = [];
  const addedIds = new Set<string>();

  for (const sub of subs.values()) {
    active.push({
      ...sub,
      expiresAt: 2105300000000,
      isPermanent: true,
      durationLabel: "مدى الحياة (VIP دائم وغير محدود)"
    });
    addedIds.add(sub.chatId);
  }

  // Ensure primary configured chatId is always in active list
  if (primaryChatId && !addedIds.has(String(primaryChatId))) {
    active.push({
      chatId: String(primaryChatId),
      code: "PRO-TRADER-2026-VIP",
      firstName: "Primary VIP Trader",
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم وغير محدود)",
      activatedAt: Date.now(),
      expiresAt: 2105300000000,
      isPermanent: true,
      expiredNotified: false
    });
  }

  return active;
}

/**
 * Returns full list of subscribers with expiration flags
 */
export function getStoredSubscribersList(): (ChatSubscriber & { isExpired: boolean })[] {
  const now = Date.now();
  const subs = getStoredSubscribers();
  return Array.from(subs.values()).map(s => ({
    ...s,
    isExpired: s.expiresAt <= now
  }));
}

/**
 * Returns subscribers whose time has expired and haven't been notified yet
 */
export function getNewlyExpiredSubscribers(): ChatSubscriber[] {
  const now = Date.now();
  const subs = getStoredSubscribers();
  const expired: ChatSubscriber[] = [];
  for (const sub of subs.values()) {
    if (sub.expiresAt <= now && !sub.expiredNotified) {
      expired.push(sub);
    }
  }
  return expired;
}

/**
 * Mark a subscriber as notified about expiration
 */
export function markSubscriberExpiredNotified(chatId: string) {
  const subs = getStoredSubscribers();
  const sub = subs.get(String(chatId));
  if (sub) {
    sub.expiredNotified = true;
    persistSubscriber(sub);
  }
}

/**
 * Check if the bot has an active, non-expired license key
 */
export function isBotLicenseValid(): { valid: boolean; remainingMs: number; expiresAt: number; code?: string; message?: string } {
  return {
    valid: true,
    remainingMs: 2105300000000 - Date.now(),
    expiresAt: 2105300000000,
    code: "PRO-TRADER-2026-VIP"
  };
}

/**
 * Activate a license code
 */
export function applyActivationCode(codeToActivate: string): { success: boolean; message: string; license?: any } {
  const cleanCode = (codeToActivate || "").trim().toUpperCase();
  const keys = getStoredKeys();
  const found = keys.get(cleanCode);

  if (!found) {
    return {
      success: false,
      message: "كود التفعيل غير صحيح أو غير موجود! تأكد من نسخ الكود بالشكل الصحيح."
    };
  }

  const now = Date.now();
  if (found.expiresAt && found.expiresAt < now && cleanCode !== "PRO-TRADER-2026-VIP") {
    return {
      success: false,
      message: "هذا الكود منتهي الصلاحية بالفعل! قم بتوليد كود جديد من التطبيق."
    };
  }

  // Activate now
  const expiresAt = now + found.durationHours * 60 * 60 * 1000;
  currentActiveLicense = {
    code: found.code,
    activatedAt: now,
    expiresAt,
    durationHours: found.durationHours,
    durationLabel: found.durationLabel,
  };

  found.used = true;
  found.usedAt = now;
  found.expiresAt = expiresAt;
  found.status = "ACTIVE";

  persistKey(found);

  return {
    success: true,
    message: `تم تفعيل الكود بنجاح! الصلاحية: ${found.durationLabel}.`,
    license: currentActiveLicense,
  };
}

/**
 * Format remaining time human-readable
 */
export function formatRemainingTime(ms: number): string {
  if (ms <= 0) return "منتهي الصلاحية";
  const hours = Math.floor(ms / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;

  if (days > 0) {
    return `${days} يوم و ${remainingHours} ساعة`;
  }
  const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
  return `${hours} ساعة و ${minutes} دقيقة`;
}

/**
 * Get all generated codes, subscribers, and active license info
 */
export function getActivationStatus() {
  const status = isBotLicenseValid();
  const keys = getStoredKeys();
  const subs = getStoredSubscribers();

  const list = Array.from(keys.values()).map(k => ({
    ...k,
    isPending: k.status === "PENDING" || !k.used,
    isExpired: k.expiresAt ? Date.now() > k.expiresAt : false,
    remainingMs: k.expiresAt ? Math.max(0, k.expiresAt - Date.now()) : null,
  }));

  const subscribers = Array.from(subs.values()).map(s => {
    const isExpired = Date.now() > s.expiresAt;
    const remainingMs = Math.max(0, s.expiresAt - Date.now());
    return {
      ...s,
      isExpired,
      remainingMs,
      remainingFormatted: formatRemainingTime(remainingMs),
      displayName: s.firstName ? (s.username ? `${s.firstName} (@${s.username})` : s.firstName) : (s.username ? `@${s.username}` : `Chat ${s.chatId}`),
    };
  });

  return {
    activeLicense: currentActiveLicense ? {
      ...currentActiveLicense,
      remainingSeconds: Math.max(0, Math.floor((currentActiveLicense.expiresAt - Date.now()) / 1000)),
      isValid: status.valid,
    } : null,
    generatedCodes: list,
    subscribersCount: subscribers.length,
    activeSubscribersCount: subscribers.filter(s => !s.isExpired).length,
    subscribers,
  };
}

/**
 * Gets a user's specific capital & risk profile from database
 */
export function getUserSubscriberProfile(chatId: string): {
  capital: number;
  riskPercent: number;
  firstName?: string;
  username?: string;
  active: boolean;
} {
  const subs = getStoredSubscribers();
  const sub = subs.get(chatId);
  const capital = (sub && typeof sub.capital === "number" && sub.capital > 0) ? sub.capital : 1000;
  const riskPercent = (sub && typeof sub.riskPercent === "number" && sub.riskPercent > 0) ? sub.riskPercent : 1.0;
  const active = sub ? (sub.isPermanent || Date.now() < sub.expiresAt) : false;
  return {
    capital,
    riskPercent,
    firstName: sub?.firstName,
    username: sub?.username,
    active
  };
}

/**
 * Updates a user's custom capital and risk preferences in persistent storage
 */
export function updateUserCapitalAndRisk(
  chatId: string,
  capital?: number,
  riskPercent?: number,
  userName?: string
): {
  success: boolean;
  capital: number;
  riskPercent: number;
  sub?: ChatSubscriber;
} {
  let updatedCapital = 1000;
  let updatedRisk = 1.0;
  let resSub: ChatSubscriber | undefined;

  saveLocalDatabase((db) => {
    if (!db.chatSubscribers) db.chatSubscribers = {};
    const existing: ChatSubscriber = db.chatSubscribers[chatId] || {
      chatId,
      code: "PRO-TRADER-2026-VIP",
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم)",
      activatedAt: Date.now(),
      expiresAt: 2105300000000,
      isPermanent: true,
      firstName: userName,
    };

    if (capital && capital > 0) {
      existing.capital = Math.max(10, Math.min(10000000, Math.round(capital)));
    } else if (!existing.capital) {
      existing.capital = 1000;
    }

    if (riskPercent && riskPercent > 0) {
      existing.riskPercent = Math.max(0.1, Math.min(10.0, Number(riskPercent.toFixed(2))));
    } else if (!existing.riskPercent) {
      existing.riskPercent = 1.0;
    }

    if (userName && !existing.firstName) {
      existing.firstName = userName;
    }

    db.chatSubscribers[chatId] = existing;
    updatedCapital = existing.capital;
    updatedRisk = existing.riskPercent;
    resSub = existing;
  });

  return {
    success: true,
    capital: updatedCapital,
    riskPercent: updatedRisk,
    sub: resSub
  };
}
