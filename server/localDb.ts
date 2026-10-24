import fs from 'fs';
import path from 'path';
import { queueCloudSync, loadCloudStateFromFirestore, forceCloudSyncNow } from './firebaseDb';

// Define the local data directory and database file
const DATA_DIR = path.join(process.cwd(), 'data');
const DB_FILE = path.join(DATA_DIR, 'db.json');

export interface UserAccount {
  id: string;
  username: string;
  accessCode: string; // Master access code or user key
  role: 'admin' | 'user';
  createdAt: number;
  lastLoginAt?: number;
}

export interface AILearningMemoryItem {
  id: string;
  iteration: number;
  assetSymbol: string;
  marketBias: string;
  confidence: number;
  pattern: string;
  orderBlock?: string;
  liquiditySweep?: string;
  macroSynthesis: string;
  outcome: 'PENDING' | 'TARGET_HIT_TP1' | 'TARGET_HIT_TP2' | 'TARGET_HIT_TP3' | 'STOP_LOSS_HIT';
  rewardScore: number;
  timestamp: number;
}

export interface LocalDatabaseSchema {
  users: UserAccount[];
  sessions: {
    token: string;
    userId: string;
    username: string;
    role: string;
    expiresAt: number;
  }[];
  activationKeys: Record<string, any>;
  chatSubscribers: Record<string, any>;
  userTrades?: Record<string, any>;
  trialHistory?: string[]; // Chat IDs of users who already consumed a 1-hour trial code
  telegramConfig: any;
  tradeAuditLogs: any[];
  tradeAuditLogsVersion?: number;
  aiLearningMemory: AILearningMemoryItem[];
  savedSignals: any[];
  telegramMessageThreads?: {
    preAlerts?: Record<string, Record<string, number>>;
    confirmedSignals?: Record<string, Record<string, number>>;
  };
  systemSettings: {
    appName: string;
    requireAuth: boolean;
    defaultLanguage: string;
    theme: string;
  };
}

export const PERMANENT_VIP_CODES: Record<string, {
  code: string;
  durationHours: number;
  durationLabel: string;
  label: string;
  status: "ACTIVE";
  isPermanent: boolean;
  multiUserAllowed: boolean;
}> = {
  "PRO-TRADER-2026-VIP": {
    code: "PRO-TRADER-2026-VIP",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "Master Lifetime VIP Code",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-7777-2026": {
    code: "VIP-7777-2026",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "VIP Master Pass",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-FOREVER-2026": {
    code: "VIP-FOREVER-2026",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "VIP Forever Pass",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-LIFETIME-PASS": {
    code: "VIP-LIFETIME-PASS",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "VIP Lifetime Key",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-TRADING-PRO": {
    code: "VIP-TRADING-PRO",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "Pro Trader VIP",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-ALFRED-MILKER": {
    code: "VIP-ALFRED-MILKER",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "Alfred Milker VIP Master",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-UNLIMITED-2026": {
    code: "VIP-UNLIMITED-2026",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "Unlimited VIP Signal Key",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-MASTER-KEY": {
    code: "VIP-MASTER-KEY",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "Master Syndicate Key",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-SNIPER-4H": {
    code: "VIP-SNIPER-4H",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "4H Structure Sniper Pass",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
  "VIP-YEN8-R5K2": {
    code: "VIP-YEN8-R5K2",
    durationHours: 87600,
    durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
    label: "Liquidity Dissection VIP",
    status: "ACTIVE",
    isPermanent: true,
    multiUserAllowed: true,
  },
};

const DEFAULT_DB: LocalDatabaseSchema = {
  users: [
    {
      id: 'admin-1',
      username: 'admin',
      accessCode: 'PRO-TRADER-2026-VIP',
      role: 'admin',
      createdAt: Date.now(),
    },
    {
      id: 'user-vip',
      username: 'trader',
      accessCode: 'VIP-7777-2026',
      role: 'user',
      createdAt: Date.now(),
    }
  ],
  sessions: [],
  activationKeys: {
    "PRO-TRADER-2026-VIP": {
      code: "PRO-TRADER-2026-VIP",
      createdAt: Date.now(),
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      label: "Master Lifetime VIP Code",
      used: false,
      multiUserAllowed: true,
      isPermanent: true,
      status: "ACTIVE",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
    },
    "VIP-7777-2026": {
      code: "VIP-7777-2026",
      createdAt: Date.now(),
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      label: "VIP Master Pass",
      used: false,
      multiUserAllowed: true,
      isPermanent: true,
      status: "ACTIVE",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
    },
    "VIP-FOREVER-2026": {
      code: "VIP-FOREVER-2026",
      createdAt: Date.now(),
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      label: "VIP Forever Pass",
      used: false,
      multiUserAllowed: true,
      isPermanent: true,
      status: "ACTIVE",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
    },
    "VIP-LIFETIME-PASS": {
      code: "VIP-LIFETIME-PASS",
      createdAt: Date.now(),
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      label: "VIP Lifetime Key",
      used: false,
      multiUserAllowed: true,
      isPermanent: true,
      status: "ACTIVE",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
    },
    "VIP-TRADING-PRO": {
      code: "VIP-TRADING-PRO",
      createdAt: Date.now(),
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      label: "Pro Trader VIP",
      used: false,
      multiUserAllowed: true,
      isPermanent: true,
      status: "ACTIVE",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
    },
    "VIP-ALFRED-MILKER": {
      code: "VIP-ALFRED-MILKER",
      createdAt: Date.now(),
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      label: "Alfred Milker VIP Master",
      used: false,
      multiUserAllowed: true,
      isPermanent: true,
      status: "ACTIVE",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
    }
  },
  chatSubscribers: {
    "853330850": {
      chatId: "853330850",
      code: "PRO-TRADER-2026-VIP",
      firstName: "VIP Trader",
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
      isPermanent: true,
      expiredNotified: false
    },
    "8447201959": {
      chatId: "8447201959",
      code: "PRO-TRADER-2026-VIP",
      firstName: "Med3ddi",
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
      isPermanent: true,
      expiredNotified: false
    },
    "8247752240": {
      chatId: "8247752240",
      code: "VIP-YEN8-R5K2",
      firstName: "Me",
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      activatedAt: Date.now(),
      expiresAt: Date.now() + 87600 * 3600 * 1000,
      isPermanent: true,
      expiredNotified: false
    }
  },
  telegramConfig: {
    botToken: process.env.TELEGRAM_BOT_TOKEN || "8771006055:AAE-Ct5GmkqasGstJCXMYtG_peAqLSDhSQY",
    chatId: process.env.TELEGRAM_CHAT_ID || "853330850",
    enabled: true,
    minConfidence: 95,
    assets: ["XAU/USD"],
    notifyOnNews: true,
    omniRadarAllMarkets: false,
  },
  tradeAuditLogs: [],
  aiLearningMemory: [],
  savedSignals: [],
  systemSettings: {
    appName: "TradingAI Pro",
    requireAuth: true,
    defaultLanguage: "fr",
    theme: "light",
  }
};

// In-memory cache synced with disk
let cachedDb: LocalDatabaseSchema | null = null;

function ensureDataDirectory() {
  try {
    if (!fs.existsSync(DATA_DIR)) {
      fs.mkdirSync(DATA_DIR, { recursive: true });
    }
  } catch (err) {
    console.error('[LocalDB] Error creating data directory:', err);
  }
}

const DB_BACKUP_FILE = path.join(DATA_DIR, 'db.backup.json');

/**
 * Loads database from local JSON file (or initializes default / restores from backup)
 */
export function getLocalDatabase(): LocalDatabaseSchema {
  if (cachedDb) {
    return cachedDb;
  }

  ensureDataDirectory();

  try {
    if (fs.existsSync(DB_FILE)) {
      const raw = fs.readFileSync(DB_FILE, 'utf-8');
      cachedDb = JSON.parse(raw);
    } else if (fs.existsSync(DB_BACKUP_FILE)) {
      console.warn('[LocalDB] Restoring database from backup copy...');
      const backupRaw = fs.readFileSync(DB_BACKUP_FILE, 'utf-8');
      cachedDb = JSON.parse(backupRaw);
      fs.writeFileSync(DB_FILE, backupRaw, 'utf-8');
    } else {
      cachedDb = { ...DEFAULT_DB };
      fs.writeFileSync(DB_FILE, JSON.stringify(cachedDb, null, 2), 'utf-8');
      fs.writeFileSync(DB_BACKUP_FILE, JSON.stringify(cachedDb, null, 2), 'utf-8');
      console.log('[LocalDB] Initialized fresh persistent local database at data/db.json');
    }
  } catch (err) {
    console.error('[LocalDB] Failed reading db.json, attempting backup recovery:', err);
    try {
      if (fs.existsSync(DB_BACKUP_FILE)) {
        const backupRaw = fs.readFileSync(DB_BACKUP_FILE, 'utf-8');
        cachedDb = JSON.parse(backupRaw);
      } else {
        cachedDb = { ...DEFAULT_DB };
      }
    } catch {
      cachedDb = { ...DEFAULT_DB };
    }
  }

  // Ensure necessary sub-objects exist
  if (!cachedDb.activationKeys) cachedDb.activationKeys = {};
  if (!cachedDb.chatSubscribers) cachedDb.chatSubscribers = {};
  if (!cachedDb.trialHistory) cachedDb.trialHistory = [];

  // Guarantee all PERMANENT_VIP_CODES are always available and active in memory & disk
  let hasModifiedKeys = false;
  for (const [codeKey, keyDef] of Object.entries(PERMANENT_VIP_CODES)) {
    const existing = cachedDb.activationKeys[codeKey];
    if (!existing || existing.expiresAt < Date.now() + 365 * 24 * 3600 * 1000 || existing.status !== "ACTIVE") {
      cachedDb.activationKeys[codeKey] = {
        code: keyDef.code,
        createdAt: existing?.createdAt || Date.now(),
        durationHours: keyDef.durationHours,
        durationLabel: keyDef.durationLabel,
        label: keyDef.label,
        used: false,
        multiUserAllowed: true,
        isPermanent: true,
        status: "ACTIVE",
        activatedAt: Date.now(),
        expiresAt: 2105300000000, // 10 years / year 2036+
      };
      hasModifiedKeys = true;
    }
  }

  // Ensure default/configured chatId is always in chatSubscribers with permanent VIP status
  const primaryChatId = cachedDb.telegramConfig?.chatId || process.env.TELEGRAM_CHAT_ID;
  if (primaryChatId && !cachedDb.chatSubscribers[primaryChatId]) {
    cachedDb.chatSubscribers[primaryChatId] = {
      chatId: String(primaryChatId),
      code: "PRO-TRADER-2026-VIP",
      firstName: "Primary VIP Trader",
      durationHours: 87600,
      durationLabel: "مدى الحياة (VIP دائم 10 سنوات)",
      activatedAt: Date.now(),
      expiresAt: 2105300000000,
      isPermanent: true,
      expiredNotified: false,
    };
    hasModifiedKeys = true;
  }

  // Ensure all existing subscribers with permanent codes never expire
  for (const sub of Object.values(cachedDb.chatSubscribers)) {
    if (sub.isPermanent || PERMANENT_VIP_CODES[sub.code] || sub.chatId === primaryChatId) {
      if (sub.expiresAt < 2000000000000 || sub.expiredNotified) {
        sub.expiresAt = 2105300000000;
        sub.durationHours = 87600;
        sub.durationLabel = "مدى الحياة (VIP دائم 10 سنوات)";
        sub.isPermanent = true;
        sub.expiredNotified = false;
        hasModifiedKeys = true;
      }
    }
  }

  // Strict Gold-Only Telegram Config guarantee
  if (cachedDb.telegramConfig) {
    if (!cachedDb.telegramConfig.assets || cachedDb.telegramConfig.assets.some((a: string) => a !== 'XAU/USD')) {
      cachedDb.telegramConfig.assets = ['XAU/USD'];
      hasModifiedKeys = true;
    }
    if (cachedDb.telegramConfig.omniRadarAllMarkets !== false) {
      cachedDb.telegramConfig.omniRadarAllMarkets = false;
      hasModifiedKeys = true;
    }
  }

  if (hasModifiedKeys) {
    try {
      const dataStr = JSON.stringify(cachedDb, null, 2);
      fs.writeFileSync(DB_FILE, dataStr, 'utf-8');
      fs.writeFileSync(DB_BACKUP_FILE, dataStr, 'utf-8');
    } catch {
      // ignore
    }
  }
  if (!cachedDb.aiLearningMemory || cachedDb.aiLearningMemory.length === 0) {
    cachedDb.aiLearningMemory = [
      {
        id: "mem-xau-master-1",
        iteration: 101,
        assetSymbol: "XAU/USD",
        marketBias: "Bullish",
        confidence: 96,
        pattern: "Institutional Order Flow + SSL Sweep (Master Trader Blueprint)",
        orderBlock: "$2642.50 - $2648.00",
        liquiditySweep: "$2640.20",
        macroSynthesis: "Gold Asian Low sweep followed by 15M ChoCh displacement and 15M rejection wick. 1% Risk, 50% partial at TP1 (1:2 R:R), Breakeven secured, TP2 reached at 1:3.8 R:R.",
        outcome: "TARGET_HIT_TP2",
        rewardScore: 1.0,
        timestamp: Date.now() - 3600000 * 12,
      },
      {
        id: "mem-btc-master-2",
        iteration: 102,
        assetSymbol: "BTC/USDT",
        marketBias: "Bearish",
        confidence: 95,
        pattern: "Institutional Distribution + BSL Sweep (Master Trader Blueprint)",
        orderBlock: "$94800 - $95200",
        liquiditySweep: "$95500",
        macroSynthesis: "Bitcoin London Judas Swing above Asian High. 15M MSS body close, mitigated 15M FVG. SL placed 2 pips beyond high. TP1 locked at 1:2 R:R.",
        outcome: "TARGET_HIT_TP1",
        rewardScore: 0.98,
        timestamp: Date.now() - 3600000 * 8,
      },
      {
        id: "mem-eur-master-3",
        iteration: 103,
        assetSymbol: "EUR/USD",
        marketBias: "Bullish",
        confidence: 94,
        pattern: "London Killzone Asian Range Expansion + Demand OB",
        orderBlock: "1.0820 - 1.0835",
        liquiditySweep: "1.0812",
        macroSynthesis: "EUR/USD 1% risk strict lot calculation. 15M Sniper Confirmation Candle confirmed banks participation. 1:3.6 R:R secured.",
        outcome: "TARGET_HIT_TP2",
        rewardScore: 1.0,
        timestamp: Date.now() - 3600000 * 4,
      }
    ];
  }

  return cachedDb!;
}

/**
 * Saves database state atomically to disk with immediate backup mirroring and cloud sync to Firestore 24/7
 */
export function saveLocalDatabase(updater?: ((db: LocalDatabaseSchema) => void) | Partial<LocalDatabaseSchema>): LocalDatabaseSchema {
  const db = getLocalDatabase();
  if (typeof updater === 'function') {
    updater(db);
  } else if (typeof updater === 'object' && updater !== null) {
    Object.assign(db, updater);
  }

  ensureDataDirectory();

  try {
    const dataStr = JSON.stringify(db, null, 2);
    const tempFile = path.join(DATA_DIR, `db.tmp.${Date.now()}`);
    
    // 1. Atomic write to temp file then rename
    fs.writeFileSync(tempFile, dataStr, 'utf-8');
    fs.renameSync(tempFile, DB_FILE);
    
    // 2. Mirror to backup file for safety
    fs.writeFileSync(DB_BACKUP_FILE, dataStr, 'utf-8');
  } catch (err) {
    console.error('[LocalDB] Failed saving db.json atomically:', err);
  }

  // 3. Queue asynchronous cloud synchronization to Firebase Firestore (24/7 persistent backend)
  try {
    queueCloudSync(db);
  } catch (err) {
    console.error('[LocalDB] Failed queueing cloud sync to Firebase:', err);
  }

  return db;
}

let isCloudInitialized = false;

/**
 * Initializes and restores state from Firestore cloud database on server startup
 */
export async function initDatabaseFromCloud(): Promise<void> {
  if (isCloudInitialized) return;
  isCloudInitialized = true;

  try {
    console.log('[LocalDB] Connecting to 24/7 Cloud Firestore to restore persistent data...');
    const cloudData = await loadCloudStateFromFirestore();

    if (cloudData) {
      const current = getLocalDatabase();
      // Merge cloud data over current defaults/file
      cachedDb = {
        ...current,
        users: cloudData.users && cloudData.users.length > 0 ? cloudData.users : current.users,
        activationKeys: cloudData.activationKeys ? { ...current.activationKeys, ...cloudData.activationKeys } : current.activationKeys,
        chatSubscribers: cloudData.chatSubscribers ? { ...current.chatSubscribers, ...cloudData.chatSubscribers } : current.chatSubscribers,
        trialHistory: Array.isArray(cloudData.trialHistory) ? cloudData.trialHistory : current.trialHistory,
        telegramConfig: cloudData.telegramConfig ? { ...current.telegramConfig, ...cloudData.telegramConfig } : current.telegramConfig,
        tradeAuditLogs: Array.isArray(cloudData.tradeAuditLogs) && cloudData.tradeAuditLogs.length > 0 ? cloudData.tradeAuditLogs : current.tradeAuditLogs,
        aiLearningMemory: Array.isArray(cloudData.aiLearningMemory) && cloudData.aiLearningMemory.length > 0 ? cloudData.aiLearningMemory : current.aiLearningMemory,
        systemSettings: cloudData.systemSettings ? { ...current.systemSettings, ...cloudData.systemSettings } : current.systemSettings,
      };

      // Persist merged state to local disk
      ensureDataDirectory();
      const dataStr = JSON.stringify(cachedDb, null, 2);
      fs.writeFileSync(DB_FILE, dataStr, 'utf-8');
      fs.writeFileSync(DB_BACKUP_FILE, dataStr, 'utf-8');
      console.log('[LocalDB] Persistent state successfully restored from Firestore 24/7 backend!');
    } else {
      // If cloud is empty, seed it with the current database
      console.log('[LocalDB] Firestore is empty, seeding cloud database with initial state...');
      const current = getLocalDatabase();
      await forceCloudSyncNow(current);
    }
  } catch (err) {
    console.error('[LocalDB] Error during cloud database initialization:', err);
  }
}

// ----------------------------------------------------
// Authentication & User Management Helpers
// ----------------------------------------------------

export function verifyUserLogin(username: string, accessCode: string): {
  success: boolean;
  message?: string;
  user?: { id: string; username: string; role: string };
  token?: string;
  expiresAt?: number;
} {
  const db = getLocalDatabase();
  const cleanUsername = (username || '').trim().toLowerCase();
  const cleanCode = (accessCode || '').trim().toUpperCase();

  // 1. Check if user exists in database with matching code
  let foundUser = db.users.find(
    (u) => u.username.toLowerCase() === cleanUsername && u.accessCode.toUpperCase() === cleanCode
  );

  // 2. Also allow any valid VIP Activation Key created in activation.ts to log in directly!
  const hasMatchingKey = db.activationKeys[cleanCode];
  if (!foundUser && cleanCode.startsWith('VIP-') && hasMatchingKey) {
    // Auto-create or login with code
    foundUser = {
      id: `user-${Date.now()}`,
      username: cleanUsername || `trader_${cleanCode.slice(-4)}`,
      accessCode: cleanCode,
      role: 'user',
      createdAt: Date.now(),
      lastLoginAt: Date.now(),
    };
    saveLocalDatabase((d) => {
      d.users.push(foundUser!);
    });
  }

  // 3. Fallback master admin access code
  if (!foundUser && cleanCode === 'PRO-TRADER-2026-VIP') {
    foundUser = {
      id: 'admin-master',
      username: cleanUsername || 'admin',
      accessCode: 'PRO-TRADER-2026-VIP',
      role: 'admin',
      createdAt: Date.now(),
      lastLoginAt: Date.now(),
    };
    saveLocalDatabase((d) => {
      if (!d.users.some(u => u.accessCode === 'PRO-TRADER-2026-VIP')) {
        d.users.push(foundUser!);
      }
    });
  }

  if (!foundUser) {
    return {
      success: false,
      message: 'اسم المستخدم أو كود الدخول غير صحيح! تأكد من الحساب والكود.'
    };
  }

  // Generate a local secure session token
  const token = `tok_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;
  const expiresAt = Date.now() + 30 * 24 * 60 * 60 * 1000; // 30 days valid session

  saveLocalDatabase((d) => {
    // Update user last login
    const target = d.users.find(u => u.id === foundUser!.id);
    if (target) {
      target.lastLoginAt = Date.now();
    }
    // Clean old expired sessions
    d.sessions = d.sessions.filter(s => s.expiresAt > Date.now());
    // Store new session
    d.sessions.push({
      token,
      userId: foundUser!.id,
      username: foundUser!.username,
      role: foundUser!.role,
      expiresAt,
    });
  });

  return {
    success: true,
    user: {
      id: foundUser.id,
      username: foundUser.username,
      role: foundUser.role,
    },
    token,
    expiresAt,
  };
}

export function validateSessionToken(token?: string): {
  valid: boolean;
  user?: { id: string; username: string; role: string };
} {
  if (!token) return { valid: false };

  const db = getLocalDatabase();
  const session = db.sessions.find(s => s.token === token && s.expiresAt > Date.now());

  if (!session) {
    return { valid: false };
  }

  return {
    valid: true,
    user: {
      id: session.userId,
      username: session.username,
      role: session.role,
    }
  };
}

export function registerNewUser(username: string, accessCode: string, role: 'admin' | 'user' = 'user'): {
  success: boolean;
  message?: string;
  user?: UserAccount;
} {
  const db = getLocalDatabase();
  const cleanUsername = (username || '').trim();
  const cleanCode = (accessCode || '').trim().toUpperCase();

  if (!cleanUsername || !cleanCode) {
    return { success: false, message: 'يرجى إدخال اسم المستخدم وكود التفعيل' };
  }

  if (db.users.some(u => u.username.toLowerCase() === cleanUsername.toLowerCase())) {
    return { success: false, message: 'اسم المستخدم مسجل مسبقاً، اختر اسماً آخر' };
  }

  const newUser: UserAccount = {
    id: `user-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
    username: cleanUsername,
    accessCode: cleanCode,
    role,
    createdAt: Date.now(),
    lastLoginAt: Date.now(),
  };

  saveLocalDatabase((d) => {
    d.users.push(newUser);
  });

  return {
    success: true,
    user: newUser,
  };
}

export function logoutSession(token: string) {
  saveLocalDatabase((d) => {
    d.sessions = d.sessions.filter(s => s.token !== token);
  });
}

// ----------------------------------------------------
// AI Learning Memory Persistence (Never Forgets)
// ----------------------------------------------------

export function recordAILearningMemory(item: Omit<AILearningMemoryItem, 'id' | 'timestamp'>): AILearningMemoryItem {
  const newItem: AILearningMemoryItem = {
    ...item,
    id: `aimem-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
    timestamp: Date.now(),
  };

  saveLocalDatabase((db) => {
    if (!db.aiLearningMemory) db.aiLearningMemory = [];
    // Keep up to 1000 detailed memory experiences in persistent JSON
    db.aiLearningMemory.unshift(newItem);
    if (db.aiLearningMemory.length > 1000) {
      db.aiLearningMemory = db.aiLearningMemory.slice(0, 1000);
    }
  });

  return newItem;
}

export function getAILearningHistory(limit: number = 50): AILearningMemoryItem[] {
  const db = getLocalDatabase();
  return (db.aiLearningMemory || []).slice(0, limit);
}

