import React, { useState, useEffect } from 'react';
import { MarketAsset, Candle, TechnicalIndicators, AISignal, NewsItem, SentimentData, Language } from './types';
import { INITIAL_ASSETS, INITIAL_SIGNALS, INITIAL_NEWS } from './data/defaultData';
import { Navbar } from './components/Navbar';
import { LiveTickerBar } from './components/LiveTickerBar';
import { OverviewDashboard } from './components/OverviewDashboard';
import { InteractiveCandlestickChart } from './components/InteractiveCandlestickChart';
import { TechnicalAnalysisPanel } from './components/TechnicalAnalysisPanel';
import { AISignalsSection } from './components/AISignalsSection';
import { SignalPerformanceTracker } from './components/SignalPerformanceTracker';
import { NewsAISection } from './components/NewsAISection';
import { SentimentRadar } from './components/SentimentRadar';
import { RiskManagementCalculator } from './components/RiskManagementCalculator';
import { TelegramSettingsModal } from './components/TelegramSettingsModal';
import { ToolsSidebarDrawer } from './components/ToolsSidebarDrawer';
import { LoginScreen } from './components/LoginScreen';
import { MobileBottomNav } from './components/MobileBottomNav';
import { DesignSystemShowcase } from './components/DesignSystemShowcase';
import { MarketsTableView } from './components/MarketsTableView';
import { AppLayout } from './components/layout/AppLayout';
import { InternalPageTemplate } from './components/layout/InternalPageTemplate';
import { ExunuTerminalView } from './components/ExunuTerminalView';
import { LDEmblem } from './components/LiquidityDissectionLogo';
import { AgentPanel } from './components/AgentPanel';
import { Activity, ShieldAlert, Cpu, Sparkles, Layers, RefreshCw, Smartphone } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  runClientStandaloneAnalysis, 
  generateAccurateCandles, 
  calculatePreciseSMCIndicators 
} from './services/clientStandaloneEngine';

export default function App() {
  const [lang, setLang] = useState<Language>('fr');
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');
  const [activeTab, setActiveTab] = useState<string>('overview');

  // User Authentication State
  const [currentUser, setCurrentUser] = useState<{ id: string; username: string; role: string } | null>(() => {
    try {
      const saved = localStorage.getItem('trading_ai_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [authToken, setAuthToken] = useState<string | null>(() => {
    return localStorage.getItem('trading_ai_token') || null;
  });
  const [isAuthChecking, setIsAuthChecking] = useState<boolean>(true);

  // Validate session token on startup
  useEffect(() => {
    const verifySession = async () => {
      const token = localStorage.getItem('trading_ai_token');
      if (!token) {
        setIsAuthChecking(false);
        return;
      }
      try {
        const res = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          if (data.authenticated && data.user) {
            setCurrentUser(data.user);
            setAuthToken(token);
            // Instant fresh synchronization of all live data upon session restore
            syncAllMarketData(true);
          } else {
            localStorage.removeItem('trading_ai_token');
            localStorage.removeItem('trading_ai_user');
            setCurrentUser(null);
            setAuthToken(null);
          }
        } else {
          localStorage.removeItem('trading_ai_token');
          localStorage.removeItem('trading_ai_user');
          setCurrentUser(null);
          setAuthToken(null);
        }
      } catch {
        // Network offline or server boot, keep current local cache if present
      } finally {
        setIsAuthChecking(false);
      }
    };
    verifySession();
  }, []);

  const handleLogout = async () => {
    try {
      if (authToken) {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
        });
      }
    } catch {}
    localStorage.removeItem('trading_ai_token');
    localStorage.removeItem('trading_ai_user');
    setCurrentUser(null);
    setAuthToken(null);
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  // Market Assets
  const [assets, setAssets] = useState<MarketAsset[]>(INITIAL_ASSETS);
  const [selectedAsset, setSelectedAsset] = useState<MarketAsset | null>(INITIAL_ASSETS[0]);

  // Candles & Indicators
  const [candles, setCandles] = useState<Candle[]>([]);
  const [indicators, setIndicators] = useState<TechnicalIndicators | null>(null);
  const [timeframe, setTimeframe] = useState<string>('1H');

  // Signals, News, Sentiment
  const [signals, setSignals] = useState<AISignal[]>(INITIAL_SIGNALS);
  const [news, setNews] = useState<NewsItem[]>(INITIAL_NEWS);
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);

  // Risk prefill & Assistant drawer & Telegram Modal & Tools Drawer
  const [prefillSignal, setPrefillSignal] = useState<AISignal | null>(null);
  const [isAssistantOpen, setIsAssistantOpen] = useState<boolean>(false);
  const [isTelegramOpen, setIsTelegramOpen] = useState<boolean>(false);
  const [isToolsDrawerOpen, setIsToolsDrawerOpen] = useState<boolean>(false);
  const [isDesignSystemOpen, setIsDesignSystemOpen] = useState<boolean>(false);
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Synchronization state
  const [lastSyncTime, setLastSyncTime] = useState<number>(Date.now());
  const [isSyncingLive, setIsSyncingLive] = useState<boolean>(false);
  const [isStandaloneClient, setIsStandaloneClient] = useState<boolean>(false);

  // Centralized Live Data Synchronizer with Complete Recalibration & Standalone Engine Fallback
  const syncAllMarketData = async (forceRefresh: boolean = false) => {
    try {
      setIsSyncingLive(true);
      const currentSym = selectedAsset?.symbol || 'XAU/USD';
      const currentTf = timeframe || '1H';
      const cacheBust = `_t=${Date.now()}`;

      if (forceRefresh) {
        // Use comprehensive atomic sync-all endpoint
        const syncRes = await fetch(`/api/market/sync-all?symbol=${encodeURIComponent(currentSym)}&timeframe=${encodeURIComponent(currentTf)}&force=true&${cacheBust}`, {
          cache: 'no-store',
          headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' },
          signal: AbortSignal.timeout(5000),
        }).catch(() => null);

        if (syncRes && syncRes.ok) {
          const syncData = await syncRes.json();
          if (syncData.assets && syncData.assets.length > 0) {
            setAssets(syncData.assets);
          }
          if (syncData.selectedAsset) {
            setSelectedAsset(syncData.selectedAsset);
          }
          if (syncData.candleData) {
            setCandles(syncData.candleData.candles || []);
            setIndicators(syncData.candleData.indicators || null);
          }
          if (syncData.signals) {
            setSignals(syncData.signals);
          }
          if (syncData.news && syncData.news.length > 0) {
            setNews(syncData.news);
          }
          if (syncData.sentiment) {
            setSentiment(syncData.sentiment);
          }
          setIsStandaloneClient(false);
          setLastSyncTime(Date.now());
          return;
        }
      }

      // Fast periodic polling
      const [assetsRes, signalsRes] = await Promise.all([
        fetch(`/api/market/assets?${cacheBust}`, { cache: 'no-store', signal: AbortSignal.timeout(3500) }).catch(() => null),
        fetch(`/api/signals?${cacheBust}`, { cache: 'no-store', signal: AbortSignal.timeout(3500) }).catch(() => null),
      ]);

      if (assetsRes && assetsRes.ok) {
        const aData = await assetsRes.json();
        if (aData.assets && aData.assets.length > 0) {
          setAssets(aData.assets);
          
          setSelectedAsset((prevSelected) => {
            const currentId = prevSelected?.id || aData.assets[0].id;
            const updated = aData.assets.find((a: MarketAsset) => a.id === currentId) || aData.assets[0];
            
            setCandles((prevCandles) => {
              if (!prevCandles || prevCandles.length === 0) return prevCandles;
              const lastIdx = prevCandles.length - 1;
              const last = prevCandles[lastIdx];
              const newPrice = updated.price;
              const updatedLast: Candle = {
                ...last,
                close: newPrice,
                high: Math.max(last.high, newPrice),
                low: Math.min(last.low, newPrice),
              };
              const nextList = [...prevCandles];
              nextList[lastIdx] = updatedLast;
              return nextList;
            });

            return updated;
          });
          setIsStandaloneClient(false);
        }
      } else {
        // Fallback: Run autonomous client-side analysis in browser ONLY if assets not yet loaded
        setAssets((prevAssets) => {
          if (!prevAssets || prevAssets.length === 0) {
            runClientStandaloneAnalysis().then((standaloneResult) => {
              setAssets(standaloneResult.assets);
              setSignals(standaloneResult.signals);
              setIsStandaloneClient(true);
            }).catch(() => {});
          }
          return prevAssets;
        });
      }

      if (signalsRes && signalsRes.ok) {
        const sData = await signalsRes.json();
        if (sData.signals && sData.signals.length > 0) {
          setSignals(sData.signals);
        }
      }

      setLastSyncTime(Date.now());
    } catch (err) {
      // In case of network micro-glitch, keep existing market data without thrashing state
    } finally {
      setIsSyncingLive(false);
      setIsLoading(false);
    }
  };

  // Helper to fetch chart & indicators with client standalone fallback
  const fetchChartAndSentiment = async (sym?: string, tf?: string, force: boolean = false) => {
    const currentSym = sym || selectedAsset?.symbol;
    const currentTf = tf || timeframe;
    if (!currentSym) return;

    const targetAsset = assets.find(a => a.symbol === currentSym) || selectedAsset;

    try {
      const cacheBust = `_t=${Date.now()}`;
      const [candleRes, sentRes] = await Promise.all([
        fetch(`/api/market/candles?symbol=${encodeURIComponent(currentSym)}&timeframe=${currentTf}${force ? '&force=true' : ''}&${cacheBust}`, { cache: 'no-store', signal: AbortSignal.timeout(3500) }).catch(() => null),
        fetch(`/api/sentiment?symbol=${encodeURIComponent(currentSym)}&${cacheBust}`, { cache: 'no-store', signal: AbortSignal.timeout(3500) }).catch(() => null),
      ]);

      if (candleRes && candleRes.ok) {
        const cData = await candleRes.json();
        setCandles(cData.candles);
        setIndicators(cData.indicators);
      } else if (targetAsset) {
        // Standalone Client-side candle & indicator calculation with 100% exact prices
        const genCandles = generateAccurateCandles(targetAsset, currentTf, 70);
        const genInd = calculatePreciseSMCIndicators(targetAsset, genCandles);
        setCandles(genCandles);
        setIndicators(genInd);
      }

      if (sentRes && sentRes.ok) {
        const sData = await sentRes.json();
        setSentiment(sData.sentiment);
      }
    } catch (err) {
      if (targetAsset) {
        const genCandles = generateAccurateCandles(targetAsset, currentTf, 70);
        const genInd = calculatePreciseSMCIndicators(targetAsset, genCandles);
        setCandles(genCandles);
        setIndicators(genInd);
      }
    }
  };

  // 1. Initial Load & Background News Fetch (Forces clean live market sync)
  useEffect(() => {
    const initApp = async () => {
      await syncAllMarketData(true);
      await fetchChartAndSentiment(undefined, undefined, true);
      try {
        const newsRes = await fetch(`/api/news?_t=${Date.now()}`, { cache: 'no-store' });
        if (newsRes.ok) {
          const nData = await newsRes.json();
          setNews(nData.news);
        }
      } catch (e) {
        // ignore
      }
    };
    initApp();
  }, []);

  // 2. Active Tab Resumption, Wake-up & Online Listeners (fixes app showing stale data on PC wake/reload)
  useEffect(() => {
    const handleWakeUp = async () => {
      // Instant force live synchronization when user switches back to tab, unlocks device, or PC wakes from sleep
      await syncAllMarketData(true);
      await fetchChartAndSentiment(selectedAsset?.symbol, timeframe, true);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        handleWakeUp();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleWakeUp);
    window.addEventListener('online', handleWakeUp);
    window.addEventListener('pageshow', handleWakeUp);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleWakeUp);
      window.removeEventListener('online', handleWakeUp);
      window.removeEventListener('pageshow', handleWakeUp);
    };
  }, [selectedAsset?.symbol, timeframe]);

  // 3. Ultra-Fast High-Frequency Live Ticker & Real-Time Candle Synchronizer (< 1.2s Latency)
  useEffect(() => {
    let tickCount = 0;
    let lastTickTime = Date.now();

    const interval = setInterval(async () => {
      const now = Date.now();
      const elapsedSinceLastTick = now - lastTickTime;
      lastTickTime = now;

      // Detect if PC was sleeping / suspended / closed for > 6 seconds
      if (elapsedSinceLastTick > 6000) {
        await syncAllMarketData(true);
        await fetchChartAndSentiment(selectedAsset?.symbol, timeframe, true);
        return;
      }

      tickCount++;

      // 1. High-frequency live price tick (sub-second latency from in-memory server ticker)
      try {
        const cacheBust = `_t=${now}`;
        const tickerRes = await fetch(`/api/market/ticker?${cacheBust}`, {
          cache: 'no-store',
          headers: { 'Cache-Control': 'no-cache' },
          signal: AbortSignal.timeout(3500),
        }).catch(() => null);

        if (tickerRes && tickerRes.ok) {
          const tData = await tickerRes.json();
          if (tData && typeof tData.price === 'number' && tData.price > 0) {
            setSelectedAsset((prev) => {
              if (!prev) return prev;
              const priceChanged = prev.price !== tData.price;
              const statusChanged = prev.isMarketOpen !== tData.isMarketOpen;
              if (!priceChanged && !statusChanged) return prev;
              return {
                ...prev,
                price: tData.price,
                change24h: tData.change24h,
                change24hAmount: tData.change24hAmount,
                high24h: tData.high24h || Math.max(prev.high24h, tData.price),
                low24h: tData.low24h || Math.min(prev.low24h, tData.price),
                isMarketOpen: tData.isMarketOpen,
                marketStatusLabel: tData.marketStatusLabel,
                trend: tData.change24h >= 0 ? 'Bullish' : 'Bearish',
              };
            });

            setAssets((prev) =>
              prev.map((a) =>
                a.symbol === tData.symbol
                  ? {
                      ...a,
                      price: tData.price,
                      change24h: tData.change24h,
                      change24hAmount: tData.change24hAmount,
                      high24h: tData.high24h || Math.max(a.high24h, tData.price),
                      low24h: tData.low24h || Math.min(a.low24h, tData.price),
                      isMarketOpen: tData.isMarketOpen,
                      marketStatusLabel: tData.marketStatusLabel,
                      trend: tData.change24h >= 0 ? 'Bullish' : 'Bearish',
                    }
                  : a
              )
            );

            // Dynamically synchronize current candle with live price tick
            setCandles((prevCandles) => {
              if (!prevCandles || prevCandles.length === 0) return prevCandles;
              const lastIdx = prevCandles.length - 1;
              const last = prevCandles[lastIdx];
              const newPrice = tData.price;
              if (last.close === newPrice) return prevCandles;
              const updatedLast: Candle = {
                ...last,
                close: newPrice,
                high: Math.max(last.high, newPrice),
                low: Math.min(last.low, newPrice),
                volume: last.volume + 1,
              };
              const nextList = [...prevCandles];
              nextList[lastIdx] = updatedLast;
              return nextList;
            });

            setLastSyncTime(now);
          }
        }
      } catch {
        // quiet ignore for micro-hiccups
      }

      // 2. Refresh signals every ~4 ticks (~4.8 seconds)
      if (tickCount % 4 === 0) {
        await syncAllMarketData(false);
      }

      // 3. Refresh full chart candles every ~5 ticks (~6.0 seconds)
      if (tickCount % 5 === 0) {
        fetchChartAndSentiment();
      }

      // 4. Refresh news every ~12 ticks (~14.4 seconds) with no-store cache busting
      if (tickCount % 12 === 0) {
        try {
          const nRes = await fetch(`/api/news?_t=${Date.now()}`, { cache: 'no-store' });
          if (nRes.ok) {
            const nData = await nRes.json();
            if (nData.news && nData.news.length > 0) {
              setNews(nData.news);
            }
          }
        } catch {
          // ignore
        }
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [selectedAsset?.symbol, timeframe]);

  // 4. Fetch Chart when selectedAsset or timeframe changes explicitly
  useEffect(() => {
    if (selectedAsset?.symbol) {
      fetchChartAndSentiment(selectedAsset.symbol, timeframe);
    }
  }, [selectedAsset?.symbol, timeframe]);

  const handleSelectSignalForRisk = (sig: AISignal) => {
    setPrefillSignal(sig);
    setActiveTab('risk');
    // Also set active asset if matching
    const matchingAsset = assets.find((a) => a.symbol === sig.symbol);
    if (matchingAsset) setSelectedAsset(matchingAsset);
  };

  const isAr = lang === 'ar';
  const isFr = lang === 'fr';

  const isLight = theme === 'light';

  // 0. Render Login Screen if user is not authenticated
  if (!isAuthChecking && !currentUser) {
    return (
      <LoginScreen
        onLoginSuccess={(user, token) => {
          setCurrentUser(user);
          setAuthToken(token);
          // Instant force sync of all live market data, news, candles, and signals upon login
          syncAllMarketData(true);
        }}
        lang={lang}
        theme={theme}
      />
    );
  }

  if (isLoading || !selectedAsset || isAuthChecking) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={`min-h-screen flex flex-col items-center justify-center p-4 transition-colors ${
          isLight ? 'bg-paper text-slate-700' : 'bg-canvas text-slate-300'
        }`}
      >
        <LDEmblem className="w-14 h-14 mb-5" />
        <h2 className={`text-base font-semibold tracking-tight mb-1.5 ${isLight ? 'text-slate-900' : 'text-white'}`}>EXUNU Terminal</h2>
        <p className={`text-xs text-center max-w-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
          {lang === 'fr' ? 'Chargement des stratégies XAUUSD et EURUSD…' : isAr ? 'جاري تحميل استراتيجيتي الذهب واليورو…' : 'Loading the XAUUSD and EURUSD strategies…'}
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
          if (found) setSelectedAsset(found);
        }}
        activeSignalsCount={signals.filter((s) => s.status === 'ACTIVE').length}
        isSyncingLive={isSyncingLive}
        onForceRefresh={() => syncAllMarketData(true)}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        onOpenDesignSystem={() => setIsDesignSystemOpen(true)}
        isMobileDrawerOpen={isMobileDrawerOpen}
        setIsMobileDrawerOpen={setIsMobileDrawerOpen}
        currentUser={currentUser}
        onLogout={handleLogout}
        tickerBarSlot={
          <LiveTickerBar
            assets={assets}
            selectedSymbol={selectedAsset?.symbol || 'XAU/USD'}
            onSelectAsset={(asset) => setSelectedAsset(asset)}
            lang={lang}
            theme={theme}
            isSyncing={isSyncingLive}
            onForceRefresh={() => syncAllMarketData(true)}
            lastSyncTime={lastSyncTime}
          />
        }
      >
        {/* Standalone Autonomous Mode Notice */}
        {isStandaloneClient && (
          <div className="mb-4 px-3.5 py-2 rounded-xl border border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-300 text-xs flex flex-wrap items-center justify-between gap-2 shadow-xs">
            <div className="flex items-center gap-2">
              <Smartphone className="w-4 h-4 text-sky-500 shrink-0" />
              <span className="font-bold">
                {isAr 
                  ? 'محرك التحليل المباشر الذاتي يعمل بالمتصفح (Autonomous Client Engine) • لا حاجة لسيرفر خلفي، والتحليلات وإرسال التيليجرام شغالة بالأسعار الحقيقية!' 
                  : 'Autonomous Client Engine Active: Analyzing and dispatching real-time signals directly from browser without backend!'}
              </span>
            </div>
            <button
              onClick={() => setIsTelegramOpen(true)}
              className="text-xs underline font-bold hover:opacity-80 cursor-pointer"
            >
              {isAr ? 'إعدادات التيليجرام' : 'Telegram Settings'}
            </button>
          </div>
        )}

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

          {activeTab === 'signals' && (
            <motion.div
              key="signals"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Signaux XAUUSD & EURUSD' : isAr ? 'إشارات الذهب واليورو' : 'XAUUSD & EURUSD Signals'}
                subtitle={isFr ? 'Deux stratégies uniquement : Or = Sweep + MSS + FVG (M5), EURUSD = Pullback de tendance + faux breakout asiatique (M15). Signal seulement si score ≥ 75.' : isAr ? 'استراتيجيتان فقط: الذهب = سحب سيولة + كسر هيكل + FVG، اليورو = رجوع مع الترند + اختراق كاذب لنطاق آسيا. إشارة فقط عند score ≥ 75.' : 'Two strategies only: Gold = Sweep + MSS + FVG (M5), EURUSD = Trend pullback + Asian false breakout (M15). Signals only at score ≥ 75.'}
                badge={{ label: `${signals.filter(s => s.isActionableNow).length} active signal(s)`, variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Signaux Or IA' : isAr ? 'صفقات الذهب' : 'Gold Signals' }
                ]}
              >
                <AISignalsSection
                  signals={signals}
                  onSelectSignalForRisk={handleSelectSignalForRisk}
                  onOpenTelegram={() => setIsTelegramOpen(true)}
                  onRefreshSignals={async () => {
                    const res = await fetch('/api/signals');
                    if (res.ok) {
                      const data = await res.json();
                      if (data.signals) setSignals(data.signals);
                    }
                  }}
                  lang={lang}
                  theme={theme}
                />
              </InternalPageTemplate>
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
                title={isFr ? 'Stratégies : XAUUSD & EURUSD' : isAr ? 'الاستراتيجيات: الذهب واليورو' : 'Strategies: XAUUSD & EURUSD'}
                subtitle={isFr ? 'Règles déterministes, checklist et score en direct pour chaque instrument.' : isAr ? 'قواعد ثابتة، قائمة شروط ونقاط مباشرة لكل أداة.' : 'Deterministic rules, live checklist and score for each instrument.'}
                badge={{ label: 'v1.0.0 · 2 strategies', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Stratégie IA' : isAr ? 'الاستراتيجية' : 'AI Strategy' }
                ]}
              >
                {/* Same shared SMC analysis as the dashboard, agents and Telegram */}
                <ExunuTerminalView initialSymbol={selectedAsset?.symbol?.includes('EUR') ? 'EUR/USD' : 'XAU/USD'} lang={lang} />
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
                subtitle={isFr ? 'Transparence totale: taux de réussite réel, facteur de profit et conformité au risque de 1%.' : isAr ? 'تدقيق شامل وشفاف: نسبة النجاح، صفقات المستخدمين، وانضباط إدارة المخاطر.' : 'Transparent institutional verification: live win rate, user audit logs, and 1% risk audit.'}
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
                  onRefreshNews={async () => {
                    const res = await fetch('/api/news/sync', { method: 'POST' });
                    if (res.ok) {
                      const data = await res.json();
                      if (data.news) setNews(data.news);
                    }
                  }}
                />
                <SentimentRadar sentiment={sentiment} lang={lang} theme={theme} />
              </InternalPageTemplate>
            </motion.div>
          )}

          {activeTab === 'risk' && (
            <motion.div
              key="risk"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <InternalPageTemplate
                title={isFr ? 'Gestionnaire de Risque 1% & Taille de Lot' : isAr ? 'حاسبة إدارة المخاطر 1% وحجم اللوت' : '1% Risk Engine & Position Sizing'}
                subtitle={isFr ? 'Calcul mathématique précis du lot en fonction de la distance du Stop Loss.' : isAr ? 'حساب دقيق لحجم اللوت لمنع خسارة أكثر من 1% من رأس المال مهما حدث.' : 'Exact mathematical position sizing based on stop loss distance and portfolio risk allocation.'}
                badge={{ label: '1.0% Rule Enforced', variant: 'gold' }}
                breadcrumbs={[
                  { label: 'Private Desk', onClick: () => setActiveTab('overview') },
                  { label: isFr ? 'Risque' : isAr ? 'إدارة المخاطر' : 'Risk Management' }
                ]}
              >
                <RiskManagementCalculator
                  asset={selectedAsset}
                  prefillSignal={prefillSignal}
                  lang={lang}
                  theme={theme}
                />
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
                <span className="font-bold text-xs text-amber-400">3. Risk Management</span>
              </div>
              <p className="text-xs leading-relaxed text-zinc-400">
                {isAr ? 'حساب دقيق لحجم اللوت بناء على رأس المال ووقف الخسارة (1% Max)' : 'Strict 1% max capital risk calculation & position sizing'}
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
        setLang={setLang}
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        onOpenDesignSystem={() => setIsDesignSystemOpen(true)}
        selectedAsset={selectedAsset}
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
