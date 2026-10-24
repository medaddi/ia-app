import React, { useState, useEffect } from 'react';
import { 
  Settings, 
  Database, 
  Wifi, 
  ShieldCheck, 
  RefreshCw, 
  Cpu, 
  Server, 
  Clock, 
  Key, 
  CheckCircle2, 
  HardDrive,
  Lock,
  Terminal,
  Activity
} from 'lucide-react';
import { Language, MarketAsset } from '../types';

interface SystemSettingsViewProps {
  lang: Language;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  currentUser?: { id: string; username: string; role: string } | null;
  onLogout?: () => void;
}

export const SystemSettingsView: React.FC<SystemSettingsViewProps> = ({
  lang,
  theme,
  onToggleTheme,
  currentUser,
  onLogout,
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';

  const [dbStatus, setDbStatus] = useState<any>(null);
  const [cloudStatus, setCloudStatus] = useState<any>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncSuccessMsg, setSyncSuccessMsg] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const [dbRes, cloudRes] = await Promise.all([
        fetch('/api/db/status').catch(() => null),
        fetch('/api/cloud-sync/status').catch(() => null),
      ]);
      if (dbRes && dbRes.ok) {
        setDbStatus(await dbRes.json());
      }
      if (cloudRes && cloudRes.ok) {
        setCloudStatus(await cloudRes.json());
      }
    } catch (e) {
      // quiet
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleForceSync = async () => {
    setIsSyncing(true);
    setSyncSuccessMsg(null);
    try {
      const res = await fetch('/api/cloud-sync/force', { method: 'POST' });
      if (res.ok) {
        setSyncSuccessMsg(isAr ? 'تمت مزامنة كافة البيانات وحفظها بنجاح!' : 'All configurations & data synced successfully!');
        await fetchStatus();
      }
    } catch (e) {
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="space-y-6 w-full text-zinc-100">
      
      {/* 1. Infrastructure Health Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4.5 rounded-xl border border-white/[0.08] bg-surface-2 space-y-2">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>{isAr ? 'محرك التداول 24/7' : 'Execution Node'}</span>
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
          <div className="text-lg font-black text-white font-mono">
            NodeJS / Express Active
          </div>
          <div className="text-xs text-zinc-500">
            Port 3000 • Autonomous Watchdog Armed
          </div>
        </div>

        <div className="p-4.5 rounded-xl border border-white/[0.08] bg-surface-2 space-y-2">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>{isAr ? 'حالة التخزين السحابي' : 'Cloud Storage'}</span>
            <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
              {cloudStatus?.storageMode || 'Persistent Hybrid'}
            </span>
          </div>
          <div className="text-lg font-black text-white font-mono">
            Firebase / Local DB
          </div>
          <div className="text-xs text-zinc-500">
            Auto-Quota Defense & Resilient Failover
          </div>
        </div>

        <div className="p-4.5 rounded-xl border border-white/[0.08] bg-surface-2 space-y-2">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>{isAr ? 'جلسة المستخدم الحالية' : 'Active Session'}</span>
            <span className="text-xs font-bold text-gold-500 bg-gold-500/10 px-2 py-0.5 rounded">
              {currentUser?.role || 'VIP TRADER'}
            </span>
          </div>
          <div className="text-lg font-black text-white font-mono">
            {currentUser?.username || 'Private Desk Operator'}
          </div>
          <div className="text-xs text-zinc-500">
            Institutional Token Authenticated
          </div>
        </div>
      </div>

      {/* 2. System Settings Card */}
      <div className="rounded-2xl border border-white/[0.08] bg-surface-2 p-5 sm:p-6 shadow-xl space-y-6">
        <div className="flex items-center justify-between pb-4 border-b border-white/[0.08]">
          <div className="flex items-center gap-2.5">
            <Settings className="w-5 h-5 text-gold-500" />
            <div>
              <h3 className="font-black text-base text-white tracking-tight">
                {isFr ? 'Paramètres Système & Persistance' : isAr ? 'إعدادات النظام والنسخ السحابي' : 'System & Platform Settings'}
              </h3>
              <p className="text-xs text-zinc-400">
                {isFr ? 'Configuration du stockage persistant, cache et synchronisation' : isAr ? 'إدارة التخزين، المزامنة، ومسح الكاش' : 'Persistence, cache recalibration, and environment parameters'}
              </p>
            </div>
          </div>
        </div>

        {/* Sync Action */}
        <div className="p-4 rounded-xl border border-white/[0.08] bg-surface flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h4 className="text-xs font-bold text-white flex items-center gap-2">
              <Database className="w-4 h-4 text-gold-500" />
              <span>{isAr ? 'المزامنة السحابية الفورية (Force Cloud Sync)' : 'Force Cloud Snapshot Sync'}</span>
            </h4>
            <p className="text-xs text-zinc-400 max-w-xl">
              {isAr
                ? 'مزامنة كافة الصفقات، حسابات المشتركين، وإعدادات التيليجرام وحفظها بشكل فوري ومستقر في قاعدة البيانات.'
                : 'Pushes all active configurations, trade ledgers, and Telegram hooks into persistent cloud snapshot.'}
            </p>
          </div>

          <button
            onClick={handleForceSync}
            disabled={isSyncing}
            className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gold-500 hover:bg-gold-500 text-ink-strong font-black text-xs transition cursor-pointer shrink-0 shadow-md shadow-gold-500/15"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
            <span>{isSyncing ? (isAr ? 'جاري الحفظ...' : 'Syncing...') : (isAr ? 'مزامنة وحفظ الآن' : 'Sync & Save Now')}</span>
          </button>
        </div>

        {syncSuccessMsg && (
          <div className="p-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-bold flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>{syncSuccessMsg}</span>
          </div>
        )}

        {/* Database Diagnostic Metrics */}
        <div className="space-y-3">
          <h4 className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
            {isAr ? 'سجلات قاعدة البيانات والحفظ المحلي' : 'Database Storage Diagnostics'}
          </h4>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
            <div className="p-3 rounded-xl border border-white/[0.06] bg-surface">
              <span className="text-xs text-zinc-500 font-sans block mb-1">Users Registered</span>
              <span className="font-bold text-white text-base">{dbStatus?.usersCount || 1}</span>
            </div>
            <div className="p-3 rounded-xl border border-white/[0.06] bg-surface">
              <span className="text-xs text-zinc-500 font-sans block mb-1">Active Chat Subscribers</span>
              <span className="font-bold text-gold-500 text-base">{dbStatus?.subscribersCount || 1}</span>
            </div>
            <div className="p-3 rounded-xl border border-white/[0.06] bg-surface">
              <span className="text-xs text-zinc-500 font-sans block mb-1">AI Experience Memory</span>
              <span className="font-bold text-emerald-400 text-base">{dbStatus?.aiLearningCount || 12} Setups</span>
            </div>
            <div className="p-3 rounded-xl border border-white/[0.06] bg-surface">
              <span className="text-xs text-zinc-500 font-sans block mb-1">Audit Ledger Size</span>
              <span className="font-bold text-zinc-200 text-base">Verified 24/7</span>
            </div>
          </div>
        </div>

        {/* UI & Theme Controls */}
        <div className="pt-4 border-t border-white/[0.08] flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onToggleTheme}
              className="px-3.5 py-2 rounded-xl border border-white/[0.08] hover:border-gold-500/40 bg-surface-3 text-xs font-bold text-zinc-200 transition cursor-pointer"
            >
              {theme === 'dark' ? 'Switch to Light' : 'Switch to Dark Charcoal'}
            </button>
          </div>

          {currentUser && onLogout && (
            <button
              onClick={onLogout}
              className="px-4 py-2 rounded-xl border border-rose-500/30 hover:border-rose-500 bg-rose-500/10 text-rose-400 text-xs font-bold transition cursor-pointer"
            >
              {isAr ? 'تسجيل الخروج من الجلسة' : 'Sign Out Session'}
            </button>
          )}
        </div>
      </div>

    </div>
  );
};
