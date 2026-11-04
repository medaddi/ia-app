import React, { Suspense, lazy, useState, useEffect, useRef } from 'react';
import { MarketAsset, AISignal, NewsItem, SentimentData, Language } from './types';
import { apiFetch, apiJson, setToken, getToken, setSessionExpiry } from './api';
const SignalPerformanceTracker = lazy(() => import('./components/SignalPerformanceTracker').then(m => ({ default: m.SignalPerformanceTracker })));
const NewsAISection = lazy(() => import('./components/NewsAISection').then(m => ({ default: m.NewsAISection })));
const SentimentRadar = lazy(() => import('./components/SentimentRadar').then(m => ({ default: m.SentimentRadar })));
const TelegramSettingsModal = lazy(() => import('./components/TelegramSettingsModal').then(m => ({ default: m.TelegramSettingsModal })));
import { LoginScreen } from './components/LoginScreen';
import { PendingApproval } from './components/PendingApproval';
import { MobileBottomNav } from './components/MobileBottomNav';
import { AppLayout } from './components/layout/AppLayout';
import { InternalPageTemplate } from './components/layout/InternalPageTemplate';
const PairPerformanceView = lazy(() => import('./components/PairPerformanceView').then(m => ({ default: m.PairPerformanceView })));
const ExunuTerminalView = lazy(() => import('./components/ExunuTerminalView').then(m => ({ default: m.ExunuTerminalView })));
import { DashboardView } from './components/DashboardView';
import { isInstrument } from './instruments';
import { notifyEnabled, notifyNewSignals, subscribePush } from './notifications';
import { GoldLoader, LogoLoader } from './components/GoldLoader';
import { hideSplash } from './splash';
const AgentPanel = lazy(() => import('./components/AgentPanel').then(m => ({ default: m.AgentPanel })));
import type { AppUser } from './components/AccountView';
const AccountView = lazy(() => import('./components/AccountView').then(m => ({ default: m.AccountView })));
const AdminView = lazy(() => import('./components/AdminView').then(m => ({ default: m.AdminView })));
import { motion, AnimatePresence } from 'motion/react';

const TG_KEY = 'ld_tg_connect';  // the bot's one-time Connect token, kept through the login

const ACCOUNT_TABS = ['account', 'positions', 'history', 'settings'];

export default function App() {
  const [lang, setLang] = useState<Language>('fr');
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');
  const [activeTab, setActiveTab] = useState<string>('overview');

  // Session: token in localStorage (api.ts), user from /api/auth/me
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [isAuthChecking, setIsAuthChecking] = useState<boolean>(true);
  const [backendDown, setBackendDown] = useState<boolean>(false);

  const verifySession = async () => {
    if (!getToken()) {
      setIsAuthChecking(false);
      return;
    }
    try {
      const res = await apiFetch('/api/auth/me');
      if (res.ok) {
        setCurrentUser((await res.json()).user);
      } else {
        setToken(null);
        setCurrentUser(null);
      }
      setBackendDown(false);
    } catch {
      // Free hosting sleeps when idle: the first request can take ~30-60 s, so retry instead of logging out
      setBackendDown(true);
      setTimeout(verifySession, 5000);
      return;
    }
    setIsAuthChecking(false);
  };

  useEffect(() => { verifySession(); }, []);

  const handleLogout = async () => {
    try { await apiFetch('/api/auth/logout', { method: 'POST' }); } catch { /* offline: still log out locally */ }
    setToken(null);
    setSessionExpiry(null);
    setCurrentUser(null);
  };

  // A login stays open until logout; only a session the server refuses (logged out elsewhere, account disabled) shows the login page
  const [sessionEnded, setSessionEnded] = useState(false);

  // Telegram "Connect": the bot's button opens the app with ?tg=<one-time token>; it waits through the login,
  // then links that Telegram chat to the account that logged in
  const [tgPending, setTgPending] = useState<boolean>(() => {
    try {
      const q = new URLSearchParams(window.location.search).get('tg');
      if (q) { sessionStorage.setItem(TG_KEY, q); window.history.replaceState(null, '', window.location.pathname); }
      return !!sessionStorage.getItem(TG_KEY);
    } catch { return false; }
  });
  const [tgNotice, setTgNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [tgAsk, setTgAsk] = useState<{ token: string; firstName: string; problem: string | null } | null>(null);
  const tgText = (en: string, fr: string, ar: string) => (lang === 'fr' ? fr : lang === 'ar' ? ar : en);
  useEffect(() => {
    if (!currentUser || currentUser.status === 'pending') return;
    let token: string | null = null;
    try { token = sessionStorage.getItem(TG_KEY); sessionStorage.removeItem(TG_KEY); } catch { /* storage blocked */ }
    if (!token) return;
    setTgPending(false);
    apiJson<{ firstName: string; problem: string | null }>(`/api/telegram/connect/${encodeURIComponent(token)}`)
      .then(r => setTgAsk({ token: token!, firstName: r.firstName, problem: r.problem }))
      .catch((e: Error) => setTgNotice({ ok: false, text: e.message }));
  }, [currentUser?.id, currentUser?.status]);
  const tgAccept = async () => {
    if (!tgAsk) return;
    try {
      const r = await apiJson<{ user: AppUser }>('/api/telegram/connect', { method: 'POST', body: JSON.stringify({ token: tgAsk.token }) });
      setCurrentUser(r.user);
      setTgNotice({ ok: true, text: tgText('Telegram is linked to your account. Go back to the bot: everything is there.', 'Telegram est lié à votre compte. Retournez au bot : tout y est.', 'تيليغرام تربط بحسابك. رجع للبوت: كلشي تما.') });
    } catch (e: any) {
      setTgNotice({ ok: false, text: e.message });
    }
    setTgAsk(null);
  };
  useEffect(() => { if (!tgNotice) return; const id = setTimeout(() => setTgNotice(null), 9000); return () => clearTimeout(id); }, [tgNotice]);
  // Sidebar "Link Telegram": opens the bot; the Accept happens in the tab its invitation opens, so this one checks the
  // account every 5 s for 3 minutes to show the linked Telegram as soon as it is there
  const [tgWatch, setTgWatch] = useState(0);
  const linkTelegram = async () => {
    const win = window.open('about:blank', '_blank');  // opened in the click itself, or the browser blocks it
    try {
      const r = await apiJson<{ link: string | null }>('/api/telegram/bot');
      if (!r.link) throw new Error(tgText('The bot is not set up yet.', 'Le bot n’est pas encore configuré.', 'البوت مازال ما تعدل.'));
      if (win) win.location.href = r.link; else window.location.href = r.link;
      setTgWatch(Date.now());
    } catch (e: any) {
      win?.close();
      setTgNotice({ ok: false, text: e.message });
    }
  };
  useEffect(() => {
    if (!tgWatch || currentUser?.telegramLinked) return;
    const id = setInterval(async () => {
      if (Date.now() - tgWatch > 180000) { clearInterval(id); return; }
      try { const r = await apiJson<{ user: AppUser }>('/api/me'); if (r.user.telegramLinked) { setCurrentUser(r.user); clearInterval(id); } } catch { /* next try */ }
    }, 5000);
    return () => clearInterval(id);
  }, [tgWatch, currentUser?.telegramLinked]);
  const unlinkTelegram = async () => {
    if (!window.confirm(tgText('Disconnect Telegram? The bot stops sending you the trades.', 'Déconnecter Telegram ? Le bot n’enverra plus les trades.', 'قطع ربط تيليغرام؟ البوت غادي يوقف يصيفط ليك الصفقات.'))) return;
    try {
      const r = await apiJson<{ user: AppUser }>('/api/me/telegram-link', { method: 'DELETE' });
      setCurrentUser(r.user);
      setTgNotice({ ok: true, text: tgText('Telegram disconnected from your account.', 'Telegram déconnecté de votre compte.', 'تيليغرام تقطع من حسابك.') });
    } catch (e: any) {
      setTgNotice({ ok: false, text: e.message });
    }
  };
  const tgDialog = tgAsk && currentUser ? (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="tg-accept-title">
      <div className="w-full max-w-sm glass-strong rounded-3xl border border-line p-6 text-center shadow-2xl">
        <span className="mx-auto w-14 h-14 rounded-2xl bg-[#229ED9] flex items-center justify-center" aria-hidden="true">
          <svg viewBox="0 0 24 24" className="w-7 h-7 fill-white"><path d="M9.8 15.3 9.6 19c.4 0 .6-.2.8-.4l2-1.9 4.1 3c.8.4 1.3.2 1.5-.7l2.7-12.7c.3-1.1-.4-1.6-1.1-1.3L3.7 10.8c-1.1.4-1 1-.2 1.3l4.1 1.3 9.5-6c.4-.3.9-.1.6.2z" /></svg>
        </span>
        <h2 id="tg-accept-title" className="mt-4 text-base font-semibold text-white">{tgText('Link Telegram to your account?', 'Lier Telegram à votre compte ?', 'ربط تيليغرام بحسابك؟')}</h2>
        <p className="mt-2 text-xs text-slate-400 leading-relaxed">
          {tgText('Telegram', 'Telegram', 'تيليغرام')} <b className="text-slate-100">{tgAsk.firstName || '—'}</b> → {tgText('account', 'compte', 'الحساب')} <b className="text-gold-200">{currentUser.username}</b><br />
          {tgText('The bot will send you every trade with your lot. One Telegram per account.', 'Le bot vous enverra chaque trade avec votre lot. Un Telegram par compte.', 'البوت غادي يصيفط ليك كل صفقة باللوت ديالك. تيليغرام واحد لكل حساب.')}
        </p>
        {tgAsk.problem && <p className="mt-3 rounded-xl bg-rose-500/10 border border-rose-500/30 px-3 py-2 text-xs text-rose-200">{tgAsk.problem}</p>}
        <div className="mt-5 grid grid-cols-2 gap-2">
          <button onClick={() => setTgAsk(null)} className="h-11 rounded-xl border border-line text-sm text-slate-300 hover:bg-white/[0.04] cursor-pointer">{tgText('Cancel', 'Annuler', 'إلغاء')}</button>
          <button onClick={tgAccept} disabled={!!tgAsk.problem} className="h-11 rounded-xl text-sm font-semibold text-ink-strong bg-gold-gradient cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">{tgText('Accept', 'Accepter', 'قبول')}</button>
        </div>
      </div>
    </div>
  ) : null;
  const tgBanner = (tgPending && !currentUser) || tgNotice ? (
    <div role="status" className={`fixed z-[100] top-[max(12px,env(safe-area-inset-top))] left-1/2 -translate-x-1/2 w-[min(92vw,460px)] glass-strong rounded-2xl border px-4 py-3 flex items-center gap-3 shadow-2xl ${tgNotice && !tgNotice.ok ? 'border-rose-500/40' : 'border-sky-400/40'}`}>
      <span className="w-9 h-9 shrink-0 rounded-xl bg-[#229ED9] flex items-center justify-center" aria-hidden="true">
        <svg viewBox="0 0 24 24" className="w-5 h-5 fill-white"><path d="M9.8 15.3 9.6 19c.4 0 .6-.2.8-.4l2-1.9 4.1 3c.8.4 1.3.2 1.5-.7l2.7-12.7c.3-1.1-.4-1.6-1.1-1.3L3.7 10.8c-1.1.4-1 1-.2 1.3l4.1 1.3 9.5-6c.4-.3.9-.1.6.2z" /></svg>
      </span>
      <p className="min-w-0 flex-1 text-xs text-slate-100">
        {tgNotice ? tgNotice.text : tgText('Log in, then accept: your Telegram will be linked to your account.', 'Connectez-vous puis acceptez : votre Telegram sera lié à votre compte.', 'دخل لحسابك ومن بعد قبل: التيليغرام ديالك غادي يتربط بيه.')}
      </p>
      {tgNotice && <button onClick={() => setTgNotice(null)} className="text-slate-400 hover:text-white text-lg leading-none cursor-pointer" aria-label="Close">×</button>}
    </div>
  ) : null;
  useEffect(() => {
    const onExpired = () => { setCurrentUser(null); setSessionEnded(true); };
    window.addEventListener('ld-session-expired', onExpired);
    return () => window.removeEventListener('ld-session-expired', onExpired);
  }, []);

  const toggleTheme = () => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  // Live data from the backend only (no client-side fallback data)
  const [assets, setAssets] = useState<MarketAsset[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('XAU/USD');
  const [signals, setSignals] = useState<AISignal[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);
  const selectedAsset = assets.find(a => a.symbol === selectedSymbol) || assets[0] || null;

  // Assistant drawer & Telegram Modal & Tools Drawer
  const [isAssistantOpen, setIsAssistantOpen] = useState<boolean>(false);
  const [isTelegramOpen, setIsTelegramOpen] = useState<boolean>(false);
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState<boolean>(false);

  const [lastSyncTime, setLastSyncTime] = useState<number>(Date.now());
  const [isSyncingLive, setIsSyncingLive] = useState<boolean>(false);
  const symbolRef = useRef(selectedSymbol);
  symbolRef.current = selectedSymbol;

  const loadPrices = async () => {
    try {
      const a = await apiJson<{ assets: MarketAsset[] }>('/api/market/assets');
      if (a.assets?.length) setAssets(a.assets);
      setLastSyncTime(Date.now());
      setBackendDown(false);
    } catch {
      setBackendDown(true);
    }
  };
  const langRef = useRef(lang);
  langRef.current = lang;
  const loadSignals = async () => {
    try {
      const list = (await apiJson<{ signals: AISignal[] }>('/api/signals')).signals || [];
      setSignals(list);
      notifyNewSignals(list, langRef.current);  // browser notification for every new trade
    } catch { /* next poll retries */ }
  };
  const loadNews = async () => {
    try { setNews((await apiJson<{ news: NewsItem[] }>('/api/news')).news || []); } catch { /* next poll retries */ }
  };
  const loadSentiment = async () => {
    try { setSentiment((await apiJson<{ sentiment: SentimentData }>(`/api/sentiment?symbol=${encodeURIComponent(symbolRef.current)}`)).sentiment); } catch { /* next poll retries */ }
  };

  const syncAllMarketData = async () => {
    setIsSyncingLive(true);
    await Promise.all([loadPrices(), loadSignals(), loadNews(), loadSentiment()]);
    setIsSyncingLive(false);
  };

  // Prices and signals every second (live), news and sentiment every 2 min; refresh when the tab comes back
  useEffect(() => {
    if (!currentUser || currentUser.status === 'pending') return;  // a pending account only sees its waiting page
    syncAllMarketData();
    const live = (fn: () => Promise<void>) => { let busy = false; return () => { if (busy || document.hidden) return; busy = true; fn().finally(() => { busy = false; }); }; };
    // The dashboard and the chart refresh themselves; these lists (header badge, notifications) only need a slow pace
    const every = 15000;
    const ids = [setInterval(live(loadPrices), every), setInterval(live(loadSignals), every), setInterval(() => { loadNews(); loadSentiment(); }, 120000),
      // Tab in the background with notifications on: keep checking for new trades (browsers allow about once a minute there)
      setInterval(() => { if (document.hidden && notifyEnabled()) loadSignals(); }, 30000)];
    const onVisible = () => { if (document.visibilityState === 'visible') syncAllMarketData(); };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('online', onVisible);
    return () => {
      ids.forEach(clearInterval);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('online', onVisible);
    };
  }, [currentUser?.id, currentUser?.status]);

  // Admin: how many self sign-ups wait for approval (badge on "Users"), checked every minute
  const [pendingUsers, setPendingUsers] = useState(0);
  useEffect(() => {
    if (currentUser?.role !== 'admin') return;
    const load = () => { if (!document.hidden) apiJson<{ users: AppUser[] }>('/api/users').then(r => setPendingUsers(r.users.filter(u => u.status === 'pending').length)).catch(() => {}); };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [currentUser?.id, currentUser?.role, activeTab]);

  // A clicked trade notification opens the chart on its pair (service worker message, direct click, or a new window ?symbol=)
  useEffect(() => {
    const open = (sym: unknown) => {
      if (typeof sym !== 'string' || !isInstrument(sym)) return;
      setSelectedSymbol(sym);
      setActiveTab('chart');
    };
    const q = new URLSearchParams(window.location.search).get('symbol');
    if (q) { open(q); window.history.replaceState(null, '', window.location.pathname); }
    if (notifyEnabled()) subscribePush();  // refresh the push subscription (phones rotate it)
    const onEvent = (e: Event) => open((e as CustomEvent).detail);
    const onMsg = (e: MessageEvent) => { if (e.data?.type === 'ld-open-symbol') open(e.data.symbol); };
    window.addEventListener('ld-open-symbol', onEvent);
    navigator.serviceWorker?.addEventListener('message', onMsg);
    return () => { window.removeEventListener('ld-open-symbol', onEvent); navigator.serviceWorker?.removeEventListener('message', onMsg); };
  }, []);

  useEffect(() => { if (currentUser) loadSentiment(); }, [selectedSymbol]);

  const setSelectedAsset = (a: MarketAsset | null) => { if (a) setSelectedSymbol(a.symbol); };
  // The intro fades out once there is a real screen to show: the login or the waiting page at once, the app once its data is in
  useEffect(() => {
    if (isAuthChecking) return;
    if (!currentUser || currentUser.status === 'pending') hideSplash();
    else if (selectedAsset) hideSplash(true);  // the dashboard (or chart) is filling in under the intro
  },
    [isAuthChecking, currentUser?.id, currentUser?.status, !!selectedAsset]);

  const isAr = lang === 'ar';
  const isFr = lang === 'fr';


  // 0. Render Login Screen if user is not authenticated
  if (!isAuthChecking && !currentUser) {
    return (
      <>
        {tgBanner}
        <LoginScreen
          onLoginSuccess={(user) => { setSessionEnded(false); setCurrentUser(user); }}
          sessionEnded={sessionEnded}
          lang={lang}
          setLang={setLang}
          theme={theme}
        />
      </>
    );
  }

  // A self sign-up waiting for the admin: only the waiting page, it opens the app by itself once approved
  if (!isAuthChecking && currentUser?.status === 'pending') {
    return <PendingApproval user={currentUser} lang={lang} onApproved={setCurrentUser} onLogout={handleLogout} />;
  }

  if (!selectedAsset || isAuthChecking) {
    return (
      <GoldLoader label={backendDown
        ? (lang === 'fr' ? 'Le serveur se réveille, cela peut prendre une minute…' : isAr ? 'الخادم كيفيق، يقدر ياخد دقيقة…' : 'The server is waking up, this can take a minute…')
        : (lang === 'fr' ? 'Chargement des stratégies or et forex…' : isAr ? 'جاري تحميل استراتيجيات الذهب والفوركس…' : 'Loading the gold and forex strategies…')} />
    );
  }

  return (
    <>
      {tgBanner}
      {tgDialog}
      <AppLayout
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        lang={lang}
        setLang={setLang}
        theme={theme}
        onToggleTheme={toggleTheme}
        selectedAsset={selectedAsset}
        onSelectAsset={(sym) => {
          const found = assets.find(a => a.symbol === sym || a.symbol.includes(sym));
          if (found) setSelectedSymbol(found.symbol);
        }}
        activeSignalsCount={signals.filter((s) => s.isActionableNow).length}
        pendingUsers={pendingUsers}
        isSyncingLive={isSyncingLive}
        onForceRefresh={() => syncAllMarketData()}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        isMobileDrawerOpen={isMobileDrawerOpen}
        setIsMobileDrawerOpen={setIsMobileDrawerOpen}
        currentUser={currentUser ? { id: String(currentUser.id), username: currentUser.username, role: currentUser.role, telegramLinked: currentUser.telegramLinked, telegramName: currentUser.telegramName } : null}
        onLinkTelegram={linkTelegram}
        onUnlinkTelegram={unlinkTelegram}
        onLogout={handleLogout}
      >
        <Suspense fallback={<PageFallback />}>
        <AnimatePresence initial={false}>
          {activeTab === 'overview' && (
            <motion.div
              key="overview"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <DashboardView lang={lang} onOpenChart={sym => { setSelectedSymbol(sym); setActiveTab('chart'); }} />
            </motion.div>
          )}

          {(activeTab === 'chart' || activeTab === 'technical') && (
            <motion.div
              key="chart"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <ExunuTerminalView
                initialSymbol={isInstrument(selectedSymbol) ? selectedSymbol : 'XAU/USD'}
                onSymbolChange={sym => setSelectedSymbol(sym)}
                onOpenTelegram={() => setIsTelegramOpen(true)}
                lang={lang}
              />
            </motion.div>
          )}

          {activeTab === 'performance' && (
            <motion.div
              key="performance"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <InternalPageTemplate subtitle={isFr ? 'Chaque signal envoyé, suivi jusqu’au TP ou au SL.' : isAr ? 'كل إشارة تصيفطات، متبوعة حتى TP ولا SL.' : 'Every signal sent, followed to its TP or SL.'}>
                <SignalPerformanceTracker
                  lang={lang}
                  theme={theme}
                  onOpenTelegram={() => setIsTelegramOpen(true)}
                />
              </InternalPageTemplate>
            </motion.div>
          )}



          {activeTab === 'pairs' && (
            <motion.div
              key="pairs"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <InternalPageTemplate subtitle={isFr ? 'Choisissez une paire : le bilan de sa stratégie et ses trades clôturés.' : isAr ? 'ختار زوج: النتائج ديال الاستراتيجية ديالو والصفقات المسدودة.' : 'Pick a pair: its strategy’s track record and closed trades.'}>
                <PairPerformanceView lang={lang} initialSymbol={selectedSymbol} />
              </InternalPageTemplate>
            </motion.div>
          )}

          {activeTab === 'news' && (
            <motion.div
              key="news"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <InternalPageTemplate subtitle={isFr ? 'Les annonces économiques fortes : un trade à 30 min près arrive avec un avertissement.' : isAr ? 'الأخبار الاقتصادية القوية: الصفقة اللي قريبة منها ب 30 دقيقة كتجي مع تنبيه.' : 'High-impact economic news: a trade within 30 min of one comes with a warning.'}>
                <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
                  <div className="xl:col-span-8 min-w-0">
                    <NewsAISection news={news} lang={lang} theme={theme} onRefreshNews={loadNews} />
                  </div>
                  <div className="xl:col-span-4 min-w-0 xl:sticky xl:top-0">
                    <SentimentRadar sentiment={sentiment} lang={lang} theme={theme} />
                  </div>
                </div>
              </InternalPageTemplate>
            </motion.div>
          )}

          {activeTab === 'admin' && currentUser?.role === 'admin' && (
            <motion.div
              key="admin"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <InternalPageTemplate subtitle={isFr ? 'Comptes, validations et liens Telegram.' : isAr ? 'الحسابات، الموافقات وربط تيليغرام.' : 'Accounts, approvals and Telegram links.'}>
                <AdminView lang={lang} theme={theme} me={currentUser} />
              </InternalPageTemplate>
            </motion.div>
          )}

          {ACCOUNT_TABS.includes(activeTab) && currentUser && (
            <motion.div
              key="account"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <InternalPageTemplate subtitle={isFr ? 'Votre risque, vos trades et vos résultats.' : isAr ? 'المخاطرة، الصفقات والنتائج ديالك.' : 'Your risk, your trades and your results.'}>
                <AccountView lang={lang} theme={theme} user={currentUser} onUserChange={setCurrentUser} signals={signals} assets={assets} />
              </InternalPageTemplate>
            </motion.div>
          )}
        </AnimatePresence>
        </Suspense>

      </AppLayout>

      {/* 4. Tools Sidebar Drawer (Optional quick drawer) */}
      <AgentPanel isOpen={isAssistantOpen} onClose={() => setIsAssistantOpen(false)} lang={lang} />




      {/* 6. Telegram Bot Alerts Modal */}
      <Suspense fallback={null}>
        {isTelegramOpen && <TelegramSettingsModal
          isOpen={isTelegramOpen}
          onClose={() => setIsTelegramOpen(false)}
          lang={lang}
          theme={theme}
        />}

      </Suspense>

      {/* 7. Mobile Bottom Navigation Bar (Visible exclusively on mobile screens) */}
      <MobileBottomNav
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        lang={lang}
        theme={theme}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        onOpenMenu={() => setIsMobileDrawerOpen(true)}
        activeSignalsCount={signals.filter((s) => s.isActionableNow).length}
      />
    </>
  );
}


// Shown for the moment a page's code is downloaded the first time (each page is its own small file)
function PageFallback() {
  return (
    <div className="min-h-[50vh] flex items-center justify-center" role="status" aria-busy="true" aria-label="Loading">
      <LogoLoader small />
    </div>
  );
}
