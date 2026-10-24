import * as SQLite from 'expo-sqlite';

export interface UserSettings {
  id: string;
  accountBalance: number;
  riskPerTrade: number;
  language: 'ar' | 'fr' | 'en';
  hapticsEnabled: boolean;
  activeLicenseKey: string;
  isUnlocked: boolean;
}

export interface JournalEntry {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  lotSize: number;
  riskAmountUsd: number;
  status: 'PENDING' | 'RUNNING' | 'TP1_HIT' | 'TP2_HIT' | 'SL_HIT' | 'CLOSED';
  pnlUsd: number;
  setupStrategy: string;
  notes: string;
  createdAt: string;
}

let dbInstance: SQLite.SQLiteDatabase | null = null;

export async function getDatabase(): Promise<SQLite.SQLiteDatabase> {
  if (!dbInstance) {
    dbInstance = await SQLite.openDatabaseAsync('liquidity_dissection.db');
    await initDatabase(dbInstance);
  }
  return dbInstance;
}

async function initDatabase(db: SQLite.SQLiteDatabase) {
  // 1. User Settings Table
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS user_settings (
      id TEXT PRIMARY KEY,
      account_balance REAL DEFAULT 10000.0,
      risk_per_trade REAL DEFAULT 1.0,
      language TEXT DEFAULT 'ar',
      haptics_enabled INTEGER DEFAULT 1,
      active_license_key TEXT DEFAULT '',
      is_unlocked INTEGER DEFAULT 1
    );
  `);

  // 2. Journal Table
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS journal_entries (
      id TEXT PRIMARY KEY,
      symbol TEXT NOT NULL,
      direction TEXT NOT NULL,
      entry_price REAL NOT NULL,
      stop_loss REAL NOT NULL,
      take_profit_1 REAL NOT NULL,
      take_profit_2 REAL NOT NULL,
      lot_size REAL DEFAULT 0.1,
      risk_amount_usd REAL DEFAULT 100.0,
      status TEXT DEFAULT 'PENDING',
      pnl_usd REAL DEFAULT 0.0,
      setup_strategy TEXT,
      notes TEXT,
      created_at TEXT NOT NULL
    );
  `);

  // 3. News Cache Table
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS cached_news (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      title_ar TEXT,
      source TEXT,
      category TEXT,
      impact_asset TEXT,
      importance TEXT,
      is_lockout INTEGER DEFAULT 0,
      published_at TEXT
    );
  `);

  // Seed default settings if empty
  const existing = await db.getFirstAsync<{ id: string }>('SELECT id FROM user_settings LIMIT 1');
  if (!existing) {
    await db.runAsync(`
      INSERT INTO user_settings (id, account_balance, risk_per_trade, language, haptics_enabled, is_unlocked)
      VALUES ('primary_user', 10000.0, 1.0, 'ar', 1, 1);
    `);
  }
}

// User Settings CRUD
export async function loadUserSettings(): Promise<UserSettings> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<{
    id: string;
    account_balance: number;
    risk_per_trade: number;
    language: string;
    haptics_enabled: number;
    active_license_key: string;
    is_unlocked: number;
  }>('SELECT * FROM user_settings WHERE id = "primary_user" LIMIT 1');

  if (!row) {
    return {
      id: 'primary_user',
      accountBalance: 10000.0,
      riskPerTrade: 1.0,
      language: 'ar',
      hapticsEnabled: true,
      activeLicenseKey: '',
      isUnlocked: true
    };
  }

  return {
    id: row.id,
    accountBalance: row.account_balance,
    riskPerTrade: row.risk_per_trade,
    language: (row.language as 'ar' | 'fr' | 'en') || 'ar',
    hapticsEnabled: Boolean(row.haptics_enabled),
    activeLicenseKey: row.active_license_key || '',
    isUnlocked: Boolean(row.is_unlocked)
  };
}

export async function saveUserSettings(settings: Partial<UserSettings>): Promise<void> {
  const db = await getDatabase();
  const current = await loadUserSettings();
  const updated = { ...current, ...settings };

  await db.runAsync(
    `UPDATE user_settings 
     SET account_balance = ?, risk_per_trade = ?, language = ?, haptics_enabled = ?, active_license_key = ?, is_unlocked = ?
     WHERE id = "primary_user"`,
    [
      updated.accountBalance,
      updated.riskPerTrade,
      updated.language,
      updated.hapticsEnabled ? 1 : 0,
      updated.activeLicenseKey,
      updated.isUnlocked ? 1 : 0
    ]
  );
}

// Journal Entries CRUD
export async function loadJournalEntries(): Promise<JournalEntry[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<{
    id: string;
    symbol: string;
    direction: string;
    entry_price: number;
    stop_loss: number;
    take_profit_1: number;
    take_profit_2: number;
    lot_size: number;
    risk_amount_usd: number;
    status: string;
    pnl_usd: number;
    setup_strategy: string;
    notes: string;
    created_at: string;
  }>('SELECT * FROM journal_entries ORDER BY created_at DESC');

  return rows.map(r => ({
    id: r.id,
    symbol: r.symbol,
    direction: r.direction as 'BUY' | 'SELL',
    entryPrice: r.entry_price,
    stopLoss: r.stop_loss,
    takeProfit1: r.take_profit_1,
    takeProfit2: r.take_profit_2,
    lotSize: r.lot_size,
    riskAmountUsd: r.risk_amount_usd,
    status: r.status as any,
    pnlUsd: r.pnl_usd,
    setupStrategy: r.setup_strategy,
    notes: r.notes,
    createdAt: r.created_at
  }));
}

export async function saveJournalEntry(entry: JournalEntry): Promise<void> {
  const db = await getDatabase();
  await db.runAsync(
    `INSERT OR REPLACE INTO journal_entries 
     (id, symbol, direction, entry_price, stop_loss, take_profit_1, take_profit_2, lot_size, risk_amount_usd, status, pnl_usd, setup_strategy, notes, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      entry.id,
      entry.symbol,
      entry.direction,
      entry.entryPrice,
      entry.stopLoss,
      entry.takeProfit1,
      entry.takeProfit2,
      entry.lotSize,
      entry.riskAmountUsd,
      entry.status,
      entry.pnlUsd,
      entry.setupStrategy,
      entry.notes,
      entry.createdAt
    ]
  );
}
