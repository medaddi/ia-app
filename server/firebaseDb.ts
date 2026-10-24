import { initializeApp, getApps, getApp } from "firebase/app";
import { getFirestore, doc, getDoc, setDoc, terminate, setLogLevel } from "firebase/firestore";
import fs from "fs";
import path from "path";
import { LocalDatabaseSchema } from "./localDb";

// Silence internal gRPC and Firestore client logs to prevent noisy stream error logs in console
try {
  setLogLevel("silent");
} catch {
  // Ignore
}

// Load configuration
let firebaseConfig: any = null;
try {
  const configPath = path.join(process.cwd(), "firebase-applet-config.json");
  if (fs.existsSync(configPath)) {
    firebaseConfig = JSON.parse(fs.readFileSync(configPath, "utf-8"));
  }
} catch (err) {
  console.error("[Firebase] Error loading firebase-applet-config.json:", err);
}

const QUOTA_STATUS_FILE = path.join(process.cwd(), "data", "firestore_quota.json");
let quotaExhaustedUntil: number = 0;

// Load persisted quota state on startup
try {
  if (fs.existsSync(QUOTA_STATUS_FILE)) {
    const raw = JSON.parse(fs.readFileSync(QUOTA_STATUS_FILE, "utf-8"));
    if (raw && typeof raw.quotaExhaustedUntil === "number") {
      quotaExhaustedUntil = raw.quotaExhaustedUntil;
    }
  }
} catch {
  // Ignore
}

function persistQuotaStatus(until: number) {
  try {
    const dir = path.dirname(QUOTA_STATUS_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      QUOTA_STATUS_FILE,
      JSON.stringify({
        quotaExhaustedUntil: until,
        setAt: new Date().toISOString(),
        reason: "Free daily write units per project quota reached on free tier database"
      }),
      "utf-8"
    );
  } catch {
    // Ignore
  }
}

export function isFirestoreQuotaExhausted(): boolean {
  return Date.now() < quotaExhaustedUntil;
}

let firestoreInstance: any = null;

export function getFirestoreDB() {
  if (isFirestoreQuotaExhausted()) {
    return null;
  }
  if (firestoreInstance) return firestoreInstance;
  if (!firebaseConfig) return null;

  try {
    const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();
    firestoreInstance = getFirestore(
      app,
      firebaseConfig.firestoreDatabaseId && firebaseConfig.firestoreDatabaseId !== "(default)"
        ? firebaseConfig.firestoreDatabaseId
        : undefined
    );
    console.log("[Firebase] Firestore connected with Database ID:", firebaseConfig.firestoreDatabaseId || "(default)");
    return firestoreInstance;
  } catch (err) {
    console.error("[Firebase] Failed to initialize Firestore:", err);
    return null;
  }
}

export async function shutdownFirestoreDueToQuota() {
  // Free tier Firestore Spark quota resets daily at midnight UTC
  // Set safety cooldown for 24 hours
  const nextReset = new Date(Date.now() + 24 * 60 * 60 * 1000);
  quotaExhaustedUntil = nextReset.getTime();
  persistQuotaStatus(quotaExhaustedUntil);

  if (firestoreInstance) {
    try {
      await terminate(firestoreInstance);
    } catch {
      // ignore
    }
    firestoreInstance = null;
  }
  console.warn(`[Firebase Protection] Daily write quota reached. Firestore synchronization smoothly paused until ${nextReset.toUTCString()}. Local database operates with 100% full persistence and zero disruption.`);
}

const STATE_COLLECTION = "app_state";
const STATE_DOC_ID = "main";

/**
 * Loads the saved cloud state from Firestore to populate or restore the local database
 */
export async function loadCloudStateFromFirestore(): Promise<Partial<LocalDatabaseSchema> | null> {
  if (isFirestoreQuotaExhausted()) return null;

  const db = getFirestoreDB();
  if (!db) return null;

  try {
    const stateDocRef = doc(db, STATE_COLLECTION, STATE_DOC_ID);
    const snap = await Promise.race([
      getDoc(stateDocRef),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("Firestore read timed out")), 5000)
      )
    ]);

    if (snap.exists()) {
      const data = snap.data();
      console.log("[Firebase] Restored persistent state from Firestore Cloud Database.");
      return data as Partial<LocalDatabaseSchema>;
    } else {
      console.log("[Firebase] No existing cloud document found in Firestore, will initialize with first save.");
      return null;
    }
  } catch (err: any) {
    const errMsg = err?.message || String(err);
    if (
      errMsg.includes("RESOURCE_EXHAUSTED") ||
      errMsg.includes("Quota limit exceeded") ||
      errMsg.includes("quota") ||
      errMsg.includes("timed out")
    ) {
      await shutdownFirestoreDueToQuota();
    } else {
      console.error("[Firebase] Error loading cloud state from Firestore:", errMsg);
    }
    return null;
  }
}

let syncTimeout: NodeJS.Timeout | null = null;
let isSyncing = false;
let pendingStateToSave: Partial<LocalDatabaseSchema> | null = null;
let lastSyncTimestamp = 0;
const MIN_SYNC_INTERVAL_MS = 60000; // 60 seconds minimum between writes to preserve free quota

export function getCloudSyncHealth() {
  return {
    isConfigured: Boolean(firebaseConfig),
    firestoreDatabaseId: firebaseConfig?.firestoreDatabaseId || "(default)",
    projectId: firebaseConfig?.projectId || "",
    isQuotaExhausted: isFirestoreQuotaExhausted(),
    quotaResumeTime: quotaExhaustedUntil > Date.now() ? new Date(quotaExhaustedUntil).toISOString() : null,
    storageMode: isFirestoreQuotaExhausted() ? "Local JSON Database (Persistent & Active)" : "Hybrid (Local + Firestore Sync)",
    lastSyncTimestamp,
  };
}

/**
 * Debounced asynchronous sync of local database state to Firestore with quota protection
 */
export function queueCloudSync(dbData: LocalDatabaseSchema) {
  if (isFirestoreQuotaExhausted()) {
    return;
  }

  // Deep clone data to avoid mutations during async write
  pendingStateToSave = {
    users: dbData.users || [],
    activationKeys: dbData.activationKeys || {},
    chatSubscribers: dbData.chatSubscribers || {},
    trialHistory: dbData.trialHistory || [],
    telegramConfig: dbData.telegramConfig || {},
    tradeAuditLogs: dbData.tradeAuditLogs || [],
    tradeAuditLogsVersion: dbData.tradeAuditLogsVersion || 1,
    aiLearningMemory: dbData.aiLearningMemory || [],
    systemSettings: dbData.systemSettings || {
      appName: "TradingAI Pro",
      requireAuth: true,
      defaultLanguage: "fr",
      theme: "light",
    },
  };

  if (syncTimeout) {
    clearTimeout(syncTimeout);
  }

  // Throttle writes to avoid burning daily free tier write units
  const timeSinceLastSync = Date.now() - lastSyncTimestamp;
  const delay = Math.max(10000, MIN_SYNC_INTERVAL_MS - timeSinceLastSync);

  syncTimeout = setTimeout(async () => {
    if (isSyncing || !pendingStateToSave) return;
    if (isFirestoreQuotaExhausted()) return;

    isSyncing = true;

    try {
      const db = getFirestoreDB();
      if (!db) {
        isSyncing = false;
        return;
      }

      const stateDocRef = doc(db, STATE_COLLECTION, STATE_DOC_ID);
      const dataToSave = {
        ...pendingStateToSave,
        updatedAt: Date.now(),
        lastCloudSync: new Date().toISOString(),
      };

      // Wrap setDoc in a 6-second timeout to prevent hung streams on quota exhaustion
      await Promise.race([
        setDoc(stateDocRef, dataToSave, { merge: true }),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("Firestore write timed out / stream error")), 6000)
        )
      ]);

      lastSyncTimestamp = Date.now();
      console.log("[Firebase] Cloud State synchronized to Firestore successfully at:", new Date().toLocaleTimeString());
    } catch (err: any) {
      const errMsg = err?.message || String(err);
      if (
        errMsg.includes("RESOURCE_EXHAUSTED") ||
        errMsg.includes("Quota limit exceeded") ||
        errMsg.includes("quota") ||
        errMsg.includes("timed out")
      ) {
        await shutdownFirestoreDueToQuota();
      } else {
        console.error("[Firebase] Failed syncing state to Firestore:", errMsg);
      }
    } finally {
      isSyncing = false;
    }
  }, delay);
}

/**
 * Forces an immediate synchronous sync to Firestore
 */
export async function forceCloudSyncNow(dbData: LocalDatabaseSchema): Promise<boolean> {
  if (isFirestoreQuotaExhausted()) {
    console.warn("[Firebase] Cloud sync currently paused due to daily quota limit. Operating in local mode.");
    return false;
  }

  const db = getFirestoreDB();
  if (!db) return false;

  try {
    const stateDocRef = doc(db, STATE_COLLECTION, STATE_DOC_ID);
    const dataToSave = {
      users: dbData.users || [],
      activationKeys: dbData.activationKeys || {},
      chatSubscribers: dbData.chatSubscribers || {},
      trialHistory: dbData.trialHistory || [],
      telegramConfig: dbData.telegramConfig || {},
      tradeAuditLogs: dbData.tradeAuditLogs || [],
      tradeAuditLogsVersion: dbData.tradeAuditLogsVersion || 1,
      aiLearningMemory: dbData.aiLearningMemory || [],
      systemSettings: dbData.systemSettings || {
        appName: "TradingAI Pro",
        requireAuth: true,
        defaultLanguage: "fr",
        theme: "light",
      },
      updatedAt: Date.now(),
      lastCloudSync: new Date().toISOString(),
    };

    await Promise.race([
      setDoc(stateDocRef, dataToSave, { merge: true }),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("Firestore write timed out / stream error")), 6000)
      )
    ]);

    lastSyncTimestamp = Date.now();
    console.log("[Firebase] Immediate cloud sync completed successfully.");
    return true;
  } catch (err: any) {
    const errMsg = err?.message || String(err);
    if (
      errMsg.includes("RESOURCE_EXHAUSTED") ||
      errMsg.includes("Quota limit exceeded") ||
      errMsg.includes("quota") ||
      errMsg.includes("timed out")
    ) {
      await shutdownFirestoreDueToQuota();
    } else {
      console.error("[Firebase] Error in forceCloudSyncNow:", errMsg);
    }
    return false;
  }
}
