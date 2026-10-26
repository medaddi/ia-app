import React, { useState, useEffect, useRef } from 'react';
import { MarketAsset, AISignal, NewsItem, SentimentData, Language } from './types';
import { apiFetch, apiJson, setToken, getToken } from './api';
import { LiveTickerBar } from './components/LiveTickerBar';
import { SignalPerformanceTracker } from './components/SignalPerformanceTracker';
import { NewsAISection } from './components/NewsAISection';
import { SentimentRadar } from './components/SentimentRadar';
import { TelegramSettingsModal } from './components/TelegramSettingsModal';
import { ToolsSidebarDrawer } from './components/ToolsSidebarDrawer';
import { LoginScreen } from './components/LoginScreen';
import { MobileBottomNav } from './components/MobileBottomNav';
import { DesignSystemShowcase } from './components/DesignSystemShowcase';
import { MarketsTableView } from './components/MarketsTableView';
import { AppLayout } from './components/layout/AppLayout';
import { InternalPageTemplate } from './components/layout/InternalPageTemplate';
import { ExunuTerminalView } from './components/ExunuTerminalView';
import { isInstrument } from './instruments';
import { LDEmblem } from './components/LiquidityDissectionLogo';
import { AgentPanel } from './components/AgentPanel';
import { AccountView, AppUser } from './components/AccountView';
import { AdminView } from './components/AdminView';
import { Cpu } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

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
    setCurrentUser(null);
  };

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
  const [isToolsDrawerOpen, setIsToolsDrawerOpen] = useState<boolean>(false);
  const [isDesignSystemOpen, setIsDesignSystemOpen] = useState<boolean>(false);
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
  const loadSignals = async () => {
    try { setSignals((await apiJson<{ signals: AISignal[] }>('/api/signals')).signals || []); } catch { /* next poll retries */ }
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

  // Prices every 5 s, signals every 15 s, news and sentiment every 2 min; refresh when the tab comes back
  useEffect(() => {
    if (!currentUser) return;
    syncAllMarketData();
    const ids = [setInterval(loadPrices, 5000), setInterval(loadSignals, 15000), setInterval(() => { loadNews(); loadSentiment(); }, 120000)];
    const onVisible = () => { if (document.visibilityState === 'visible') syncAllMarketData(); };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('online', onVisible);
    return () => {
      ids.forEach(clearInterval);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('online', onVisible);
    };
  }, [currentUser?.id]);

  useEffect(() => { if (currentUser) loadSentiment(); }, [selectedSymbol]);

  const setSelectedAsset = (a: MarketAsset | null) => { if (a) setSelectedSymbol(a.symbol); };

  const isAr = lang === 'ar';
  const isFr = lang === 'fr';

  const isLight = theme === 'light';

  // 0. Render Login Screen if user is not authenticated
  if (!isAuthChecking && !currentUser) {
    return (
      <LoginScreen
        onLoginSuccess={(user) => setCurrentUser(user)}
        lang={lang}
        theme={theme}
      />
    );
  }

  if (!selectedAsset || isAuthChecking) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={`min-h-screen flex flex-col items-center justify-center p-4 transition-colors ${
          isLight ? 'bg-paper text-slate-700' : 'bg-canvas text-slate-300'
        }`}
      >
        <LDEmblem className="w-14 h-14 mb-5" />
        <h2 className={`text-base font-semibold tracking-tight mb-1.5 ${isLight ? 'text-slate-900' : 'text-white'}`}>LiquidityDissection</h2>
        <p className={`text-xs text-center max-w-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
          {backendDown
            ? (lang === 'fr' ? 'Le serveur se réveille (hébergement gratuit), cela peut prendre une minute…' : isAr ? 'الخادم يستيقظ (استضافة مجانية)، قد يستغرق ذلك دقيقة…' : 'The server is waking up (free hosting), this can take a minute…')
            : (lang === 'fr' ? 'Chargement des stratégies or et forex…' : isAr ? 'جاري تحميل استراتيجيات الذهب والفوركس…' : 'Loading the gold and forex strategies…')}
        </p>
        <div className={`mt-5 h-0.5 w-40 overflow-hidden rounded-full ${isLight ? 'bg-paper-line-2' : 'bg-line'}`}>
          <div className="h-full w-1/2 rounded-full bg-gold-gradient animate-shimmer" />
        </div>
      </div>
    );
  }

  return (
    <>
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
        activeSignalsCount={signals.filter((s) => s.status === 'ACTIVE').length}
        isSyncingLive={isSyncingLive}
        onForceRefresh={() => syncAllMarketData()}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        onOpenDesignSystem={() => setIsDesignSystemOpen(true)}
        isMobileDrawerOpen={isMobileDrawerOpen}
        setIsMobileDrawerOpen={setIsMobileDrawerOpen}
        currentUser={currentUser ? { id: String(currentUser.id), username: currentUser.username, role: currentUser.role } : null}
        onLogout={handleLogout}
        tickerBarSlot={
          <LiveTickerBar
            assets={assets}
            selectedSymbol={selectedAsset?.symbol || 'XAU/USD'}
            onSelectAsset={(asset) => setSelectedAsset(asset)}
            lang={lang}
            theme={theme}
            isSyncing={isSyncingLive}
            onForceRefresh={() => syncAllMarketData()}
            lastSyncTime={lastSyncTime}
          />
        }
      >
        <AnimatePresence mode="wait">
          {activeTab === 'overview' && (
            <motion.div
              key="overview"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <ExunuTerminalView
                initialSymbol={(selectedAsset?.symbol as any) || 'XAU/USD'}
                onOpenTelegram={() => setIsTelegramOpen(true)}
                lang={lang}
              />
            </motion.div>
          )}

          {activeTab === 'markets' && (
            <motion.div
              key="markets"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Marchés & Surveillance d\'Actifs' : isAr ? 'مراقبة أصول الأسواق' : 'Markets & Pair Surveillance'}
                subtitle={isFr ? 'Analyse multi-marchés des régimes, stratégies dynamiques et scores de confirmation.' : isAr ? 'تحليل هيكل السوق، وتحديد أفضل استراتيجية لكل زوج بشكل مستقل.' : 'Pair-specific market regime detection, dynamic strategy selection, and multi-layer confirmation scores.'}
                badge={{ label: 'Live Pricing Engine', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Marchés' : isAr ? 'الأسواق' : 'Markets' }
                ]}
              >
                <MarketsTableView
                  assets={assets}
                  signals={signals}
                  selectedSymbol={selectedAsset?.symbol || 'XAU/USD'}
                  onSelectAsset={(asset) => {
                    setSelectedAsset(asset);
                  }}
                  onNavigateTab={(tab) => setActiveTab(tab)}
                  lang={lang}
                />
              </InternalPageTemplate>
            </motion.div>
          )}

          {(activeTab === 'chart' || activeTab === 'technical') && (
            <motion.div
              key="chart"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <ExunuTerminalView
                initialSymbol={(selectedAsset?.symbol as any) || 'XAU/USD'}
                onOpenTelegram={() => setIsTelegramOpen(true)}
                lang={lang}
              />
            </motion.div>
          )}

          {activeTab === 'analysis' && (
            <motion.div
              key="analysis"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Stratégies : or & forex (FXAlexG)' : isAr ? 'الاستراتيجيات: الذهب والفوركس (FXAlexG)' : 'Strategies: gold & forex (FXAlexG)'}
                subtitle={isFr ? 'Règles déterministes, checklist et score en direct pour chaque instrument.' : isAr ? 'قواعد ثابتة، قائمة شروط ونقاط مباشرة لكل أداة.' : 'Deterministic rules, live checklist and score for each instrument.'}
                badge={{ label: 'v1.0.0 · 2 strategies', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Stratégie IA' : isAr ? 'الاستراتيجية' : 'AI Strategy' }
                ]}
              >
                {/* Same shared SMC analysis as the dashboard, agents and Telegram */}
                <ExunuTerminalView initialSymbol={isInstrument(selectedAsset?.symbol) ? selectedAsset.symbol : 'XAU/USD'} lang={lang} />
              </InternalPageTemplate>
            </motion.div>
          )}

          {activeTab === 'performance' && (
            <motion.div
              key="performance"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Audit & Registre de Performance' : isAr ? 'سجل التدقيق والأداء الموثق' : 'Audit & Performance Ledger'}
                subtitle={isFr ? 'Transparence totale: taux de réussite réel et facteur de profit des signaux.' : isAr ? 'نسبة النجاح الحقيقية ومعامل الربح ديال الإشارات.' : 'Real win rate and profit factor of the signals.'}
                badge={{ label: 'Verified Ledger · 99.8%', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Audit' : isAr ? 'التدقيق' : 'Audit' }
                ]}
              >
                <SignalPerformanceTracker
                  lang={lang}
                  theme={theme}
                  onOpenTelegram={() => setIsTelegramOpen(true)}
                />
              </InternalPageTemplate>
            </motion.div>
          )}



          {activeTab === 'news' && (
            <motion.div
              key="news"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Macro-Économie & Sentiment en Direct' : isAr ? 'الأخبار والماكرو والسيولة الحية' : 'Macro & Market Sentiment'}
                subtitle={isFr ? 'Impact des annonces économiques majeures et flux institutionnels.' : isAr ? 'تحليل مباشر لبيانات الفائدة، التضخم ومشاعر كبار المتداولين.' : 'Real-time macroeconomic intelligence, geopolitical catalysts, and institutional sentiment.'}
                badge={{ label: 'Macro Intelligence OTC', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Actualités' : isAr ? 'الأخبار' : 'Macro & News' }
                ]}
              >
                <NewsAISection
                  news={news}
                  lang={lang}
                  theme={theme}
                  onRefreshNews={loadNews}
                />
                <SentimentRadar sentiment={sentiment} lang={lang} theme={theme} />
              </InternalPageTemplate>
            </motion.div>
          )}

          {activeTab === 'admin' && currentUser?.role === 'admin' && (
            <motion.div
              key="admin"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Administration des utilisateurs' : isAr ? 'إدارة المستخدمين' : 'User administration'}
                subtitle={isFr ? 'Créez les comptes. Chaque utilisateur indique ses lots et a ses propres statistiques.' : isAr ? 'كتصاوب الحسابات. كل مستخدم كيدخل اللوت ديالو وعندو الإحصائيات ديالو.' : 'Create accounts. Each user enters their own lots and has their own statistics.'}
                badge={{ label: 'Admin', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: 'Admin' }
                ]}
              >
                <AdminView lang={lang} theme={theme} me={currentUser} />
              </InternalPageTemplate>
            </motion.div>
          )}

          {ACCOUNT_TABS.includes(activeTab) && currentUser && (
            <motion.div
              key="account"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Mon compte, trades & historique' : isAr ? 'حسابي، صفقاتي والسجل' : 'My account, trades & history'}
                subtitle={isFr ? 'Trades pris avec votre lot, historique, taux de réussite et perte journalière max.' : isAr ? 'الصفقات باللوت ديالك، السجل، نسبة النجاح والخسارة اليومية.' : 'Trades taken with your lot, history, win rate and daily loss limit.'}
                badge={{ label: currentUser.role === 'admin' ? 'Admin' : 'Trader', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Compte' : isAr ? 'الحساب' : 'Account' }
                ]}
              >
                <AccountView lang={lang} theme={theme} user={currentUser} onUserChange={setCurrentUser} signals={signals} assets={assets} />
              </InternalPageTemplate>
            </motion.div>
          )}
        </AnimatePresence>

        {/* System Architecture Blueprint (Explaining the 24/7 Engine matching user vision) */}
        <div className="mt-10 p-6 rounded-2xl border border-white/[0.08] bg-surface-3 shadow-xl hover:border-gold-500/30 transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gold-500/10 text-gold-500 flex items-center justify-center border border-gold-500/25">
                <Cpu className="w-4 h-4 text-gold-500" />
              </div>
              <h4 className="font-black text-sm text-white tracking-tight">
                {isAr ? 'بنية النظام المؤسساتي (Architecture)' : 'Institutional System Architecture:'}
              </h4>
            </div>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/25">
              {isAr ? 'عقود الذهب الفورية (OTC)' : 'OTC Spot Gold Connected'}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-start">
            <div className="p-3.5 rounded-xl border border-white/[0.06] bg-surface hover:border-gold-500/40 transition-all duration-150">
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-2 h-2 rounded-full bg-gold-500"></div>
                <span className="font-bold text-xs text-gold-500">1. Realtime Feeds</span>
              </div>
              <p className="text-xs leading-relaxed text-zinc-400">
                {isAr ? 'بيانات حية مباشرة للذهب الفوري المؤسساتي (XAU/USD) عبر خوادم Interbank OTC' : 'Live Institutional Spot Gold (XAU/USD) real-time feed'}
              </p>
            </div>

            <div className="p-3.5 rounded-xl border border-white/[0.06] bg-surface hover:border-gold-500/40 transition-all duration-150">
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-2 h-2 rounded-full bg-gold-500"></div>
                <span className="font-bold text-xs text-gold-500">2. SMC Algorithms</span>
              </div>
              <p className="text-xs leading-relaxed text-zinc-400">
                {isAr ? 'كشف سحب السيولة (BSL/SSL) وكتل الأوامر (OB) وتغير الهيكل (CHoCH)' : 'Order Block detection, Liquidity Sweeps & Structure Breaks'}
              </p>
            </div>

            <div className="p-3.5 rounded-xl border border-white/[0.06] bg-surface hover:border-gold-500/40 transition-all duration-150">
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-2 h-2 rounded-full bg-amber-500"></div>
                <span className="font-bold text-xs text-amber-400">3. Trade journal</span>
              </div>
              <p className="text-xs leading-relaxed text-zinc-400">
                {isAr ? 'كل مستخدم كيسجل اللوت ديالو، الإحصائيات والخسارة اليومية القصوى' : 'Each user logs their lot, stats and daily loss limit'}
              </p>
            </div>

            <div className="p-3.5 rounded-xl border border-white/[0.06] bg-surface hover:border-gold-500/40 transition-all duration-150">
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                <span className="font-bold text-xs text-emerald-400">4. Auto Telegram Bot</span>
              </div>
              <p className="text-xs leading-relaxed text-zinc-400">
                {isAr ? 'إرسال الصفقات والتنبيهات وإغلاق الأهداف فوراً إلى قناة التليجرام' : 'Instant TP/SL alerts dispatched directly to Telegram Desk'}
              </p>
            </div>
          </div>
        </div>
      </AppLayout>

      {/* 4. Tools Sidebar Drawer (Optional quick drawer) */}
      <AgentPanel isOpen={isAssistantOpen} onClose={() => setIsAssistantOpen(false)} lang={lang} />

      <ToolsSidebarDrawer
        isOpen={isToolsDrawerOpen}
        onClose={() => setIsToolsDrawerOpen(false)}
        activeTab={activeTab}
        onSelectTab={(tabId) => setActiveTab(tabId)}
        lang={lang}
        theme={theme}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        activeSignalsCount={signals.filter((s) => s.status === 'ACTIVE').length}
      />



      {/* 6. Telegram Bot Alerts Modal */}
      <TelegramSettingsModal
        isOpen={isTelegramOpen}
        onClose={() => setIsTelegramOpen(false)}
        lang={lang}
        theme={theme}
      />

      {/* 6.5 Vanguard Neo-Precision Design System Inspector */}
      <DesignSystemShowcase
        isOpen={isDesignSystemOpen}
        onClose={() => setIsDesignSystemOpen(false)}
        lang={lang}
        theme={theme}
      />

      {/* 7. Mobile Bottom Navigation Bar (Visible exclusively on mobile screens) */}
      <MobileBottomNav
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        lang={lang}
        theme={theme}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        onOpenMenu={() => setIsMobileDrawerOpen(true)}
        activeSignalsCount={signals.filter((s) => s.status === 'ACTIVE').length}
      />
    </>
  );
}
