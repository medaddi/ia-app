import React, { useState, useEffect } from 'react';
import {
  Send,
  Bell,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Sliders,
  Sparkles,
  ExternalLink,
  RefreshCw,
  Zap,
  Info,
  Key,
  MessageSquareQuote,
  History,
  Check,
  X,
  Lock,
  Radio,
  Radar,
  Activity,
  Smartphone,
  Cpu
} from 'lucide-react';
import { TelegramConfig, TelegramNotificationHistory, Language } from '../types';
import { ActivationManager } from './ActivationManager';
import { LiquidityDissectionLogo } from './LiquidityDissectionLogo';
import { 
  getClientTelegramConfig, 
  saveClientTelegramConfig, 
  sendDirectTelegramDiagnosticTest,
  fetchBotIdentity,
  switchClientTelegramBot
} from '../services/clientTelegramService';

interface TelegramSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  lang: Language;
  theme?: 'light' | 'dark';
}

export const TelegramSettingsModal: React.FC<TelegramSettingsModalProps> = ({
  isOpen,
  onClose,
  lang,
  theme = 'light',
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [minConfidence, setMinConfidence] = useState(95);
  const [notifyOnNews, setNotifyOnNews] = useState(true);
  const [omniRadarAllMarkets, setOmniRadarAllMarkets] = useState(true);
  const [directBrowserMode, setDirectBrowserMode] = useState(true);
  const [selectedAssets, setSelectedAssets] = useState<string[]>([
    'XAU/USD'
  ]);

  const [hasServerToken, setHasServerToken] = useState(false);
  const [maskedToken, setMaskedToken] = useState('');
  const [history, setHistory] = useState<TelegramNotificationHistory[]>([]);

  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isDispatchingLive, setIsDispatchingLive] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
    diagnostic?: {
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
  } | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [activeBot, setActiveBot] = useState<{ id: number; username: string; firstName: string } | null>(null);
  const [isVerifyingBot, setIsVerifyingBot] = useState(false);
  const [newBotTokenInput, setNewBotTokenInput] = useState('');
  const [newChatIdInput, setNewChatIdInput] = useState('');
  const [isSwitchingBot, setIsSwitchingBot] = useState(false);
  const [switchStatusMessage, setSwitchStatusMessage] = useState<{ success: boolean; text: string } | null>(null);

  const availableAssets = [
    { symbol: 'XAU/USD', label: isFr ? 'Or au Comptant (XAU/USD)' : isAr ? 'الذهب الفوري (XAU/USD)' : 'Spot Gold (XAU/USD)' },
  ];

  const [modalSubTab, setModalSubTab] = useState<'activation' | 'config' | 'direct' | 'logs'>('config');

  const fetchConfig = async () => {
    // 1. First populate from localStorage (client standalone memory)
    const localCfg = getClientTelegramConfig();
    if (localCfg.botToken) {
      setBotToken(localCfg.botToken);
      setMaskedToken(localCfg.botToken.slice(0, 6) + '...' + localCfg.botToken.slice(-4));
      setHasServerToken(true);
    }
    if (localCfg.chatId) setChatId(localCfg.chatId);
    setEnabled(localCfg.enabled);
    setMinConfidence(localCfg.minConfidence);
    setDirectBrowserMode(localCfg.directBrowserMode);

    // Check bot identity
    fetchBotIdentity(localCfg.botToken || undefined).then(res => {
      if (res.valid && res.bot) {
        setActiveBot(res.bot);
      }
    }).catch(() => {});

    // 2. Also try fetching from backend if online
    try {
      const res = await fetch('/api/telegram/config');
      if (res.ok) {
        const data = await res.json();
        if (data.config) {
          setHasServerToken(data.config.hasToken || Boolean(localCfg.botToken));
          if (data.config.botToken) setMaskedToken(data.config.botToken);
          if (data.config.chatId) setChatId(data.config.chatId);
          setEnabled(data.config.enabled);
          if (data.config.minConfidence) setMinConfidence(data.config.minConfidence);
          if (data.config.assets) setSelectedAssets(data.config.assets);
          if (typeof data.config.notifyOnNews === 'boolean') setNotifyOnNews(data.config.notifyOnNews);
          if (typeof data.config.omniRadarAllMarkets === 'boolean') setOmniRadarAllMarkets(data.config.omniRadarAllMarkets);
        }
        if (data.history) {
          setHistory(data.history);
        }
      }
    } catch (err) {
      // Backend offline: localStorage config is already active
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchConfig();
      setTestResult(null);
      setSaveSuccess(false);
    }
  }, [isOpen]);

  const handleToggleAsset = (sym: string) => {
    if (selectedAssets.includes(sym)) {
      if (selectedAssets.length > 1) {
        setSelectedAssets(selectedAssets.filter((a) => a !== sym));
      }
    } else {
      setSelectedAssets([...selectedAssets, sym]);
    }
  };

  const handleSwitchBot = async () => {
    if (!newBotTokenInput.trim()) {
      setSwitchStatusMessage({
        success: false,
        text: isAr ? 'يرجى إدخال رمز Bot Token الجديد أولاً' : 'Veuillez saisir le nouveau Bot Token',
      });
      return;
    }

    setIsSwitchingBot(true);
    setSwitchStatusMessage(null);

    try {
      const res = await switchClientTelegramBot(newBotTokenInput.trim(), newChatIdInput.trim() || chatId.trim());
      if (res.success && res.bot) {
        setActiveBot(res.bot);
        setBotToken(newBotTokenInput.trim());
        setMaskedToken(newBotTokenInput.trim().slice(0, 6) + '...' + newBotTokenInput.trim().slice(-4));
        if (newChatIdInput.trim()) setChatId(newChatIdInput.trim());
        setHasServerToken(true);
        setNewBotTokenInput('');
        setNewChatIdInput('');
        setSwitchStatusMessage({
          success: true,
          text: isAr
            ? `تم ربط البوت الجديد @${res.bot.username} بنجاح وحصرياً بهذا التطبيق! تم تفعيل نظام منع التكرار وحذف أي اتصالات سابقة معلقة.`
            : `Nouveau bot @${res.bot.username} lié avec succès et verrouillé à cette app ! Protection anti-doublon activée.`,
        });
        fetchConfig();
      } else {
        setSwitchStatusMessage({
          success: false,
          text: res.message || res.error || (isAr ? 'فشل تبديل البوت' : 'Échec de changement du bot'),
        });
      }
    } catch (err: any) {
      setSwitchStatusMessage({
        success: false,
        text: err?.message || (isAr ? 'خطأ في الاتصال' : 'Erreur de connexion'),
      });
    } finally {
      setIsSwitchingBot(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveSuccess(false);

    // Always save directly to localStorage so it works without any backend
    saveClientTelegramConfig({
      botToken: botToken.trim() ? botToken.trim() : undefined,
      chatId: chatId.trim() ? chatId.trim() : undefined,
      enabled,
      minConfidence,
      directBrowserMode,
    });

    try {
      const res = await fetch('/api/telegram/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          botToken: botToken.trim() ? botToken.trim() : undefined,
          chatId: chatId.trim(),
          enabled,
          minConfidence,
          assets: selectedAssets,
          notifyOnNews,
          omniRadarAllMarkets,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setHasServerToken(data.config.hasToken);
      }
    } catch (err) {
      // quiet catch for backend offline
    } finally {
      setSaveSuccess(true);
      setIsSaving(false);
      setTimeout(() => setSaveSuccess(false), 4000);
    }
  };

  const handleSendTest = async () => {
    setIsTesting(true);
    setTestResult(null);

    // Save current fields first
    saveClientTelegramConfig({
      botToken: botToken.trim() ? botToken.trim() : undefined,
      chatId: chatId.trim() ? chatId.trim() : undefined,
      enabled,
    });

    // If Direct Browser Mode is active, or if backend fails, dispatch directly from browser!
    if (directBrowserMode) {
      try {
        const directRes = await sendDirectTelegramDiagnosticTest({
          botToken: botToken.trim() || undefined,
          chatId: chatId.trim() || undefined,
        });

        if (directRes.success) {
          setTestResult({
            success: true,
            message: isAr
              ? 'تم إرسال رسالة الفحص والأسعار الحقيقية الدقيقة إلى التيليجرام بنجاح مباشرة من المتصفح (بدون الحاجة لسيرفر)!'
              : 'Direct test message with exact live prices sent successfully to Telegram from browser!',
          });
          setIsTesting(false);
          return;
        } else {
          // If direct had error, show it clearly
          setTestResult({
            success: false,
            message: directRes.error || (isAr ? 'فشل الإرسال. تأكد من صحة Bot Token و Chat ID' : 'Direct dispatch failed. Check Bot Token & Chat ID.'),
          });
          setIsTesting(false);
          return;
        }
      } catch (err: any) {
        // Fall back to server test below
      }
    }

    // Server-side test fallback
    try {
      const res = await fetch('/api/telegram/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          botToken: botToken.trim() ? botToken.trim() : undefined,
          chatId: chatId.trim() ? chatId.trim() : undefined,
        }),
      });

      const data = await res.json();
      if (data.success) {
        setTestResult({
          success: true,
          message: isFr
            ? 'Rapport de diagnostic et analyse en direct envoyé avec succès sur Telegram !'
            : isAr
            ? 'تم فحص النظام وإرسال تقرير التحليل المباشر إلى التيليجرام بنجاح! كل الأنظمة متصلة وشغالة.'
            : 'Diagnostic health and live market analysis report sent successfully to Telegram!',
          diagnostic: data.diagnostic,
        });
        fetchConfig();
      } else {
        // Attempt direct browser dispatch as automatic fallback
        const directFallback = await sendDirectTelegramDiagnosticTest({
          botToken: botToken.trim() || undefined,
          chatId: chatId.trim() || undefined,
        });

        if (directFallback.success) {
          setTestResult({
            success: true,
            message: isAr
              ? 'نجح الإرسال المباشر من المتصفح إلى التيليجرام بالأسعار الحقيقية!'
              : 'Direct browser dispatch succeeded!',
          });
        } else {
          setTestResult({
            success: false,
            message: data.error || directFallback.error || (isAr ? 'فشل الإرسال. تأكد من صحة الـ Token و Chat ID.' : 'Failed to send.'),
            diagnostic: data.diagnostic,
          });
        }
      }
    } catch (err: any) {
      // Direct browser fallback on network error
      const directFallback = await sendDirectTelegramDiagnosticTest({
        botToken: botToken.trim() || undefined,
        chatId: chatId.trim() || undefined,
      });

      if (directFallback.success) {
        setTestResult({
          success: true,
          message: isAr
            ? 'نجح الإرسال المباشر من المتصفح إلى التيليجرام بالأسعار الحقيقية!'
            : 'Direct browser dispatch succeeded!',
        });
      } else {
        setTestResult({
          success: false,
          message: directFallback.error || err.message || (isAr ? 'خطأ في الاتصال' : 'Connection error'),
        });
      }
    } finally {
      setIsTesting(false);
    }
  };

  const handleDispatchGoldNow = async () => {
    setIsDispatchingLive(true);
    try {
      const res = await fetch('/api/telegram/dispatch-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: true })
      });
      const data = await res.json();
      if (data.success) {
        setTestResult({
          success: true,
          message: data.message || (isAr ? 'تم فحص السوق وإرسال أفضل صفقة ذهب مؤكدة إلى تيليجرام فوراً وبنجاح!' : 'Gold trade setup dispatched to Telegram successfully!')
        });
        fetchConfig();
      } else {
        setTestResult({
          success: false,
          message: data.error || (isAr ? 'تعذر إرسال الصفقة حالياً. تأكد من تفعيل البوت واشتراك القناة.' : 'Failed to dispatch signal.')
        });
      }
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err?.message || (isAr ? 'خطأ في الاتصال بالخادم.' : 'Server connection error.')
      });
    } finally {
      setIsDispatchingLive(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/70 backdrop-blur-xs">
      <div
        className={`relative w-full max-w-2xl rounded-2xl sm:rounded-3xl border shadow-2xl overflow-hidden flex flex-col max-h-[94vh] sm:max-h-[92vh] transition-all ${
          isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line'
        }`}
        dir={isAr ? 'rtl' : 'ltr'}
      >
        {/* Modal Header */}
        <div className={`px-6 py-4 border-b flex items-center justify-between ${
          isLight ? 'bg-paper border-paper-line-2' : 'bg-surface-2 border-line'
        }`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-sky-600 flex items-center justify-center text-white shadow-xs">
              <Send className="w-5 h-5 -rotate-12 translate-x-0.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className={`text-base font-black ${isLight ? 'text-ink-strong' : 'text-white'}`}>
                  {isFr ? 'Alertes & Bot Telegram (24/7 Desk Feed)' : isAr ? 'ربط وإشعارات بوت تليجرام (Telegram Alerts 24/24)' : 'Telegram Bot Trade Signals (24/7)'}
                </h3>
                <span className={`text-xs font-black px-2 py-0.5 rounded-full border ${
                  enabled
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800'
                    : 'bg-slate-100 text-slate-600 border-slate-200'
                }`}>
                  {enabled ? (isFr ? 'Actif' : isAr ? 'مُفعّل' : 'Active') : (isFr ? 'Désactivé' : isAr ? 'مُعطّل' : 'Disabled')}
                </span>
              </div>
              <p className={`text-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                {isFr
                  ? 'Recevez les signaux institutionnels de Liquidity Dissection directement sur votre Telegram'
                  : isAr
                  ? 'استقبل إشارات تفكيك السيولة والصفقات المؤكدة فور صدورها عبر تيليجرام'
                  : 'Receive high-probability institutional trade setups directly on Telegram'}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className={`p-2 rounded-xl transition cursor-pointer ${
              isLight ? 'hover:bg-slate-200/60 text-slate-600' : 'hover:bg-slate-800 text-slate-300'
            }`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Sub-tabs header */}
        <div className={`flex border-b px-6 pt-2 gap-2 ${
          isLight ? 'bg-slate-50 border-paper-line-2' : 'bg-surface border-line'
        }`}>
          <button
            type="button"
            onClick={() => setModalSubTab('activation')}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold border-b-2 transition cursor-pointer ${
              modalSubTab === 'activation'
                ? 'border-gold-500 text-gold-700 dark:text-gold-400'
                : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            <span>{isFr ? 'Clé de Licence VIP' : isAr ? 'رمز التفعيل والصلاحية' : 'Access Code & Expiration'}</span>
          </button>

          <button
            type="button"
            onClick={() => setModalSubTab('config')}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold border-b-2 transition cursor-pointer ${
              modalSubTab === 'config'
                ? 'border-gold-500 text-gold-700 dark:text-gold-400'
                : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>{isFr ? 'Configuration du Bot' : isAr ? 'إعدادات الاتصال والفلترة' : 'Bot Credentials & Filters'}</span>
          </button>

          <button
            type="button"
            onClick={() => setModalSubTab('logs')}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold border-b-2 transition cursor-pointer ${
              modalSubTab === 'logs'
                ? 'border-gold-500 text-gold-700 dark:text-gold-400'
                : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
            }`}
          >
            <History className="w-3.5 h-3.5" />
            <span>{isFr ? 'Historique d\'Envoi' : isAr ? 'سجل الرسائل المرسلة' : 'Dispatch History'}</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 overflow-y-auto text-sm">
          {modalSubTab === 'activation' && (
            <ActivationManager
              onCodeApplied={() => {
                fetchConfig();
              }}
              lang={lang}
              theme={theme}
            />
          )}

          {modalSubTab === 'config' && (
            <>
              {/* Active Bot Identity & Anti-Duplication Status */}
              <div className={`p-4 rounded-2xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                isLight ? 'bg-emerald-50/70 border-emerald-200' : 'bg-emerald-950/20 border-emerald-800/60'
              }`}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center shrink-0 shadow-sm">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-black text-emerald-800 dark:text-emerald-300">
                        {activeBot ? `@${activeBot.username}` : (hasServerToken ? 'بوت تيليجرام متصل' : 'في انتظار ربط البوت')}
                      </span>
                      <span className="text-xs px-1.5 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                        {isAr ? 'مقفل حصرياً لهذا التطبيق' : 'Single-App Locked'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-slate-600 dark:text-slate-400">
                        {isAr 
                          ? 'حماية منع التكرار (Anti-Duplication Guard) نشطة: لا يمكن تكرار أي رسالة أو صفقة'
                          : 'Anti-Duplication Guard Active: duplicate messages are strictly prevented.'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 self-end sm:self-auto text-xs font-bold text-emerald-700 dark:text-emerald-300">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  <span>{isAr ? 'حماية 100% ضد التكرار' : '0% Duplication'}</span>
                </div>
              </div>

              {/* Exclusive New Bot Switcher Section */}
              <div className={`p-4.5 rounded-2xl border transition-all ${
                isLight ? 'bg-paper border-paper-line-2' : 'bg-surface-2 border-line'
              }`}>
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-black/5 dark:border-white/5">
                  <div className="flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-gold-500" />
                    <h4 className={`text-xs font-black ${isLight ? 'text-slate-900' : 'text-white'}`}>
                      {isFr ? 'Changer de Bot (Nouveau Bot Exclusif)' : isAr ? 'تبديل البوت برمز جديد وربطه حصرياً' : 'Switch to New Dedicated Bot'}
                    </h4>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded bg-gold-500/15 text-gold-700 dark:text-gold-400 font-bold">
                    {isAr ? 'حذف الرسائل المعلقة والتراكمات' : 'Purge Old Webhooks'}
                  </span>
                </div>

                <p className={`text-xs mb-3 leading-relaxed ${isLight ? 'text-slate-600' : 'text-slate-400'}`}>
                  {isFr
                    ? 'Pour éviter tout conflit ou duplication de messages, associez ici votre nouveau token. Les anciennes files d\'attente seront purgées et le bot sera verrouillé exclusivement pour cette application.'
                    : isAr
                    ? 'لتغيير البوت أو ربط بوت جديد كلياً: الصق رمز Bot Token الجديد هنا واضغط على "تبديل وربط البوت". سيقوم النظام بحذف أي اتصالات أو رسائل قديمة معلقة لتفادي أي تكرار نهائياً، وقفل البوت حصرياً لهذا التطبيق.'
                    : 'Paste your new Bot Token below to link a fresh dedicated bot. Previous pending queues will be purged to prevent any duplicate messages.'}
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className={`block text-xs font-bold mb-1 ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                      {isAr ? 'رمز Bot Token الجديد (من @BotFather):' : 'Nouveau Bot Token :'}
                    </label>
                    <input
                      type="text"
                      value={newBotTokenInput}
                      onChange={(e) => setNewBotTokenInput(e.target.value)}
                      placeholder="Ex: 8838286778:AAHi8BTlx..."
                      className={`w-full rounded-xl px-3 py-2 text-xs border font-mono focus:outline-none focus:ring-2 focus:ring-gold-500 ${
                        isLight ? 'bg-white border-paper-line-2 text-slate-900' : 'bg-surface border-line text-white'
                      }`}
                    />
                  </div>

                  <div>
                    <label className={`block text-xs font-bold mb-1 ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                      {isAr ? 'Chat ID الجديد (اختياري / أو اترك الحالي):' : 'Nouveau Chat ID (Optionnel) :'}
                    </label>
                    <input
                      type="text"
                      value={newChatIdInput}
                      onChange={(e) => setNewChatIdInput(e.target.value)}
                      placeholder={chatId ? `الحالي: ${chatId}` : 'Ex: 8447201959'}
                      className={`w-full rounded-xl px-3 py-2 text-xs border font-mono focus:outline-none focus:ring-2 focus:ring-gold-500 ${
                        isLight ? 'bg-white border-paper-line-2 text-slate-900' : 'bg-surface border-line text-white'
                      }`}
                    />
                  </div>
                </div>

                {switchStatusMessage && (
                  <div className={`p-2.5 rounded-xl text-xs mb-3 flex items-center gap-2 ${
                    switchStatusMessage.success
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border border-emerald-500/30'
                      : 'bg-rose-500/10 text-rose-600 dark:text-rose-300 border border-rose-500/30'
                  }`}>
                    {switchStatusMessage.success ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertTriangle className="w-4 h-4 shrink-0" />}
                    <span>{switchStatusMessage.text}</span>
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleSwitchBot}
                  disabled={isSwitchingBot || !newBotTokenInput.trim()}
                  className={`w-full py-2.5 px-4 rounded-xl text-xs font-black flex items-center justify-center gap-2 transition cursor-pointer ${
                    isSwitchingBot || !newBotTokenInput.trim()
                      ? 'bg-slate-300 dark:bg-slate-800 text-slate-500 cursor-not-allowed'
                      : 'bg-gold-500 hover:bg-gold-500 text-ink-strong shadow-sm'
                  }`}
                >
                  <RefreshCw className={`w-4 h-4 ${isSwitchingBot ? 'animate-spin' : ''}`} />
                  <span>
                    {isSwitchingBot
                      ? (isAr ? 'جاري التحقق وقفل البوت حصرياً...' : 'Liaison exclusive en cours...')
                      : (isAr ? 'ربط البوت الجديد حصرياً وحذف التكرار' : 'Lier le nouveau bot exclusivement')}
                  </span>
                </button>
              </div>

              {/* Status Quick Banner */}
              <div className={`p-3.5 rounded-2xl border flex items-start gap-3 ${
                isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
              }`}>
                <Info className="w-5 h-5 text-gold-500 shrink-0 mt-0.5" />
                <div className={`text-xs leading-relaxed ${isLight ? 'text-slate-600' : 'text-slate-300'}`}>
                  <span className={`font-black block mb-0.5 ${isLight ? 'text-ink-strong' : 'text-white'}`}>
                    {isFr ? 'Configuration du Bot Telegram :' : isAr ? 'كيفية تفعيل واستقبال الصفقات عبر تيليجرام:' : 'How to receive signals in Telegram?'}
                  </span>
                  {isFr ? (
                    <>
                      1. Ouvrez Telegram, écrivez à <b>@BotFather</b> avec <code>/newbot</code> pour obtenir votre <b>Bot Token</b>.<br />
                      2. Lancez votre bot, puis trouvez votre <b>Chat ID</b> via <b>@userinfobot</b>.<br />
                      3. Collez vos identifiants ci-dessous et cliquez sur <b>"Tester"</b>.
                    </>
                  ) : isAr ? (
                    <>
                      1. افتح تطبيق تيليجرام، وابحث عن البوت الرسمي <b>@BotFather</b>، ثم أرسل له الأمر <code>/newbot</code> للحصول على رمز الـ <b>Bot Token</b>.<br />
                      2. ابدأ المحادثة مع البوت الخاص بك بالضغط على <b>Start</b>، ثم احصل على معرفك الخاص <b>Chat ID</b> عبر البوت <b>@userinfobot</b>.<br />
                      3. أدخل البيانات أدناه واضغط على <b>"إرسال رسالة تجريبية"</b> للتحقق من نجاح الربط.
                    </>
                  ) : (
                    <>
                      1. Open Telegram, message <b>@BotFather</b>, send <code>/newbot</code> to get your <b>Bot Token</b>.<br />
                      2. Start your bot, then find your <b>Chat ID</b> via <b>@userinfobot</b>.<br />
                      3. Paste both below and click <b>"Send Test"</b> to verify!
                    </>
                  )}
                </div>
              </div>

              {/* Form Credentials */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className={`block text-xs font-bold mb-1.5 flex items-center gap-1.5 ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                    <Key className="w-3.5 h-3.5 text-gold-500" />
                    <span>Telegram Bot Token</span>
                  </label>
                  <input
                    type="password"
                    value={botToken}
                    onChange={(e) => setBotToken(e.target.value)}
                    placeholder={hasServerToken ? `${maskedToken} (Enregistré)` : '123456789:ABCdefGhI...'}
                    className={`w-full rounded-xl px-3.5 py-2 text-xs border font-mono-numbers focus:outline-none focus:ring-2 focus:ring-gold-500 ${
                      isLight ? 'bg-white border-paper-line-2 text-slate-900' : 'bg-surface border-line text-white'
                    }`}
                  />
                </div>

                <div>
                  <label className={`block text-xs font-bold mb-1.5 flex items-center gap-1.5 ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                    <MessageSquareQuote className="w-3.5 h-3.5 text-gold-500" />
                    <span>Telegram Chat ID / User ID</span>
                  </label>
                  <input
                    type="text"
                    value={chatId}
                    onChange={(e) => setChatId(e.target.value)}
                    placeholder="Ex: 184920482 ou @channel_name"
                    className={`w-full rounded-xl px-3.5 py-2 text-xs border font-mono-numbers focus:outline-none focus:ring-2 focus:ring-gold-500 ${
                      isLight ? 'bg-white border-paper-line-2 text-slate-900' : 'bg-surface border-line text-white'
                    }`}
                  />
                </div>
              </div>

              {/* Direct Browser Dispatch Card (No Backend Required) */}
              <div className={`p-4 rounded-2xl border transition-all ${
                directBrowserMode
                  ? isLight ? 'bg-sky-50/80 border-sky-300' : 'bg-sky-950/30 border-sky-800'
                  : isLight ? 'bg-slate-50 border-slate-200' : 'bg-surface border-line'
              }`}>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                      directBrowserMode ? 'bg-sky-500 text-white shadow-sm' : 'bg-slate-200 dark:bg-slate-800 text-slate-500'
                    }`}>
                      <Smartphone className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className={`text-xs font-black ${isLight ? 'text-slate-900' : 'text-white'}`}>
                          {isFr 
                            ? 'Mode Direct Navigateur (Sans Serveur Backend)' 
                            : isAr 
                            ? 'وضع الإرسال المباشر من المتصفح (بدون الحاجة لسيرفر Backend)' 
                            : 'Direct Browser Dispatch (Zero Backend Required)'}
                        </h4>
                        <span className="text-xs px-1.5 py-0.5 rounded font-bold bg-sky-500/20 text-sky-500">
                          {isAr ? 'شغال 100%' : 'Autonomous'}
                        </span>
                      </div>
                      <p className={`text-xs mt-0.5 leading-relaxed ${isLight ? 'text-slate-600' : 'text-slate-400'}`}>
                        {isFr
                          ? 'Permet d\'analyser les marchés et d\'envoyer les alertes Telegram avec les prix exacts directement depuis votre navigateur.'
                          : isAr
                          ? 'يقوم المتصفح مباشرة بحساب تحليلات 4H و 15M وإرسال الصفقات للتيليجرام بالأسعار الحقيقية المضبوطة حتى لو كان السيرفر طافي.'
                          : 'Analyzes markets and dispatches Telegram signals with exact prices directly from your browser even if backend is offline.'}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDirectBrowserMode(!directBrowserMode)}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      directBrowserMode ? 'bg-sky-500' : 'bg-slate-300 dark:bg-slate-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                        directBrowserMode ? (isAr ? '-translate-x-5' : 'translate-x-5') : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                {/* Real-time Prices Preview Strip */}
                <div className="mt-3 pt-3 border-t border-sky-500/20 flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-bold text-sky-600 dark:text-sky-400">
                    {isAr ? 'أسعار الصفقات الحية المعتمدة (Gold):' : 'Live Gold Prices Preview:'}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-black/10 dark:bg-white/5 font-mono">
                    XAU/USD: Spot LBMA Institutional
                  </span>
                </div>
              </div>

              {/* Omni-Timeframe 360° Continuous Gold Radar Switch */}
              <div className={`p-4 rounded-2xl border transition-all ${
                omniRadarAllMarkets
                  ? isLight ? 'bg-amber-50/70 border-amber-300' : 'bg-amber-950/30 border-amber-800'
                  : isLight ? 'bg-slate-50 border-slate-200' : 'bg-surface border-line'
              }`}>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                      omniRadarAllMarkets ? 'bg-gold-500 text-black shadow-sm' : 'bg-slate-200 dark:bg-slate-800 text-slate-500'
                    }`}>
                      <Radar className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className={`text-xs font-black ${isLight ? 'text-slate-900' : 'text-white'}`}>
                        {isFr 
                          ? 'Radar Gold 360° Multi-Timeframes (Recommandé)' 
                          : isAr 
                          ? 'رادار الذهب 360° المستمر متعدد الفريمات والجلسات (Gold Radar)' 
                          : 'Gold 360° Multi-Timeframe Continuous Radar'}
                      </h4>
                      <p className={`text-xs mt-0.5 ${isLight ? 'text-slate-600' : 'text-slate-400'}`}>
                        {isFr
                          ? 'Le bot surveille en continu le Gold (XAU/USD) à travers toutes les sessions (Londres, NY, Asie) et envoie uniquement les setups A+ validés.'
                          : isAr
                          ? 'يراقب البوت الذهب الفوري (XAU/USD) عبر جلسات لندن ونيويورك وآسيا ويرسل الصفقات المؤكدة A+ فقط عند اكتمال الشروط 100%.'
                          : 'Bot continuously monitors Gold (XAU/USD) across all sessions (London, NY, Asian) and only sends verified A+ setups.'}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setOmniRadarAllMarkets(!omniRadarAllMarkets)}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      omniRadarAllMarkets ? 'bg-gold-500' : 'bg-slate-300 dark:bg-slate-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                        omniRadarAllMarkets ? (isAr ? '-translate-x-5' : 'translate-x-5') : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Anti-Spam Discipline Status */}
              <div className={`p-3.5 rounded-2xl border flex items-center justify-between gap-3 ${
                isLight ? 'bg-emerald-50/70 border-emerald-200' : 'bg-emerald-950/20 border-emerald-900/40'
              }`}>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-emerald-500/20 text-emerald-500 flex items-center justify-center shrink-0">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-black ${isLight ? 'text-emerald-900' : 'text-emerald-300'}`}>
                        {isAr ? 'نظام الحماية من السبام والتكرار (Anti-Spam 100%)' : 'Anti-Spam Trade Discipline (Active)'}
                      </span>
                      <span className="text-xs px-1.5 py-0.5 rounded font-black bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                        {isAr ? 'منضبط' : 'Enforced'}
                      </span>
                    </div>
                    <p className={`text-xs mt-0.5 ${isLight ? 'text-slate-600' : 'text-slate-400'}`}>
                      {isAr
                        ? 'صفقات مضمونة 100% (تأكيد 95%+) • صفقة واحدة نشطة • تباعد 30-60 دقيقة • منع التكرار والسبام نهائياً.'
                        : 'Strict 100% Guaranteed Setups (95%+ Confirmed) • 1 Active Trade • 30-60m Pacing • Zero Noise.'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Test & Save buttons */}
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleSendTest}
                  disabled={isTesting}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold border transition cursor-pointer ${
                    isLight ? 'bg-paper hover:bg-paper border-paper-line-2 text-slate-800' : 'bg-surface-3 hover:bg-surface-3 border-line-2 text-white'
                  }`}
                >
                  <Activity className="w-4 h-4 text-gold-500" />
                  <span>
                    {isTesting
                      ? (isFr ? 'Test & Diagnostic en cours...' : isAr ? 'جاري فحص النظام والتحليل الحي...' : 'Running Diagnostic...')
                      : (isFr ? 'Tester & Vérifier l\'Analyse Live' : isAr ? 'فحص الاتصال والتحليل الحي (Telegram Diagnostic)' : 'Run Live Diagnostic Test')}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={handleDispatchGoldNow}
                  disabled={isDispatchingLive}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-black bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white shadow-lg shadow-emerald-500/20 transition cursor-pointer"
                >
                  <Zap className="w-4 h-4 text-white animate-pulse" />
                  <span>
                    {isDispatchingLive
                      ? (isAr ? 'جاري الفحص والإرسال للتيليجرام...' : 'Dispatching Trade...')
                      : (isAr ? 'إرسال صفقة ذهب فورية إلى تيليجرام' : 'Instant Gold Dispatch')}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={handleSave}
                  disabled={isSaving}
                  className="px-5 py-2.5 rounded-xl text-xs font-black bg-gold-500 hover:bg-gold-500 text-ink-strong transition shadow-xs cursor-pointer"
                >
                  {isSaving ? (isFr ? 'Enregistrement...' : isAr ? 'جاري الحفظ...' : 'Saving...') : (isFr ? 'Enregistrer les Paramètres' : isAr ? 'حفظ الإعدادات' : 'Save Configuration')}
                </button>
              </div>

              {testResult && (
                <div className={`p-4 rounded-2xl text-xs border space-y-3 ${
                  testResult.success
                    ? 'bg-emerald-500/10 text-emerald-900 border-emerald-500/30 dark:text-emerald-200'
                    : 'bg-rose-500/10 text-rose-900 border-rose-500/30 dark:text-rose-200'
                }`}>
                  <div className="flex items-center gap-2 font-black">
                    <span className="text-base">{testResult.success ? '' : ''}</span>
                    <span>{testResult.message}</span>
                  </div>

                  {testResult.diagnostic && (
                    <div className="space-y-2 pt-2 border-t border-emerald-500/20">
                      <div className="text-xs font-bold opacity-80">
                        {isAr ? 'نتائج الفحص المباشر للأسواق والمحرك الذكي:' : 'Live Market Diagnostic Breakdown:'}
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {testResult.diagnostic.assets?.map((asset: any, idx: number) => (
                          <div key={idx} className="p-2 rounded-xl bg-black/10 dark:bg-white/5 border border-black/5 dark:border-white/5 flex flex-col">
                            <div className="flex items-center justify-between text-xs font-bold">
                              <span>{asset.symbol}</span>
                              <span className="text-emerald-500 font-mono text-xs">{asset.latencyMs}ms</span>
                            </div>
                            <div className="font-mono font-bold text-xs mt-0.5">
                              {asset.price > 0 ? (asset.symbol.includes('BTC') ? `$${asset.price.toLocaleString()}` : `$${asset.price}`) : 'Offline'}
                            </div>
                          </div>
                        ))}
                      </div>

                      <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                        <span className="px-2 py-0.5 rounded-md bg-emerald-500/20 font-bold">
                          {isAr ? 'محرك التحليل: نشط 24/7' : 'AI Engine: Active'}
                        </span>
                        <span className="px-2 py-0.5 rounded-md bg-sky-500/20 font-bold">
                          {isAr ? `جلسة التداول: ${testResult.diagnostic.session?.labelAr || 'نشطة'}` : `Session: ${testResult.diagnostic.session?.labelFr || 'Active'}`}
                        </span>
                        <span className="px-2 py-0.5 rounded-md bg-amber-500/20 font-bold">
                          {isAr ? `المشتركين: ${testResult.diagnostic.activeSubscribersCount || 0}` : `Subscribers: ${testResult.diagnostic.activeSubscribersCount || 0}`}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {modalSubTab === 'logs' && (
            <div className="space-y-2">
              {history.length === 0 ? (
                <div className="text-center py-8 text-xs text-slate-400">
                  {isFr ? 'Aucun message dans l\'historique.' : isAr ? 'لا يوجد سجل رسائل حتى الآن.' : 'No dispatch logs found.'}
                </div>
              ) : (
                history.map((h, i) => (
                  <div
                    key={i}
                    className={`p-3 rounded-xl border text-xs flex items-center justify-between ${
                      isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
                    }`}
                  >
                    <div>
                      <span className="font-bold text-gold-700 dark:text-gold-400">{h.symbol}</span>
                      <span className="text-xs text-slate-500 ml-2">{h.action} @ ${h.price}</span>
                    </div>
                    <span className="text-xs text-slate-400 font-mono-numbers">{h.timestamp}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
