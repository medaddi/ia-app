import React, { useState, useEffect, useRef } from 'react';
import { 
  LayoutDashboard,
  TrendingUp, 
  BarChart2, 
  ShieldCheck,
  Bot, 
  Sparkles,
  Menu, 
  X, 
  Search, 
  Languages, 
  ChevronDown, 
  ChevronLeft, 
  ChevronRight, 
  User, 
  LogOut, 
  RefreshCw, 
  Send, 
  Check,
  Activity,
  Layers,
  Newspaper,
  ShieldAlert,
  Cpu,
  LineChart,
  Wallet,
  UserCog,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { MarketAsset, Language } from '../../types';
import { LiquidityDissectionLogo, LDEmblem } from '../LiquidityDissectionLogo';

export interface AppLayoutProps {
  children: React.ReactNode;
  activeTab: string;
  onSelectTab: (tabId: string) => void;
  lang: Language;
  setLang: (lang: Language) => void;
  theme?: 'light' | 'dark';
  onToggleTheme?: () => void;
  selectedAsset: MarketAsset;
  onSelectAsset?: (symbol: string) => void;
  activeSignalsCount: number;
  isSyncingLive?: boolean;
  onForceRefresh?: () => void;
  onOpenAssistant: () => void;
  onOpenTelegram?: () => void;
  onOpenDesignSystem?: () => void;
  isMobileDrawerOpen?: boolean;
  setIsMobileDrawerOpen?: (open: boolean) => void;
  currentUser?: { id: string; username: string; role: string } | null;
  onLogout?: () => void;
  tickerBarSlot?: React.ReactNode;
}

/** Current kill zone label (London 08:00–11:00 London time, NY 08:30–11:30 New York time), refreshed every minute. */
function useCurrentKillzone(): string | null {
  const calc = () => {
    const mins = (tz: string) => {
      const p = new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date());
      return Number(p.find(x => x.type === 'hour')?.value) * 60 + Number(p.find(x => x.type === 'minute')?.value);
    };
    const ldn = mins('Europe/London'), ny = mins('America/New_York');
    if (ldn >= 480 && ldn < 660) return 'LONDON KILL ZONE';
    if (ny >= 510 && ny < 690) return 'NEW YORK KILL ZONE';
    return null;
  };
  const [label, setLabel] = useState<string | null>(calc);
  useEffect(() => {
    const id = setInterval(() => setLabel(calc()), 60000);
    return () => clearInterval(id);
  }, []);
  return label;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  activeTab,
  onSelectTab,
  lang,
  setLang,
  selectedAsset,
  onSelectAsset,
  activeSignalsCount,
  isSyncingLive = false,
  onForceRefresh,
  onOpenAssistant,
  onOpenTelegram,
  onOpenDesignSystem,
  isMobileDrawerOpen: controlledDrawerOpen,
  setIsMobileDrawerOpen: setControlledDrawerOpen,
  currentUser,
  onLogout,
  tickerBarSlot,
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const currentWindow = useCurrentKillzone();

  // Desktop sidebar collapsed state (persisted)
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('ld_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  // Mobile drawer state
  const [internalDrawerOpen, setInternalDrawerOpen] = useState<boolean>(false);
  const isDrawerOpen = controlledDrawerOpen !== undefined ? controlledDrawerOpen : internalDrawerOpen;
  
  const setDrawerOpen = (open: boolean) => {
    if (setControlledDrawerOpen) {
      setControlledDrawerOpen(open);
    }
    setInternalDrawerOpen(open);
  };

  const [isLangDropdownOpen, setIsLangDropdownOpen] = useState<boolean>(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const searchInputRef = useRef<HTMLInputElement>(null);
  const langDropdownRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // 1. Accessibility: Lock body scroll when mobile drawer is open
  useEffect(() => {
    if (isDrawerOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [isDrawerOpen]);

  // 2. Hotkeys: Cmd+K / Ctrl+K for search, Escape to close overlays
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
      if (e.key === 'Escape') {
        setIsLangDropdownOpen(false);
        setIsUserMenuOpen(false);
        setDrawerOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // 3. Click-outside listeners for dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (langDropdownRef.current && !langDropdownRef.current.contains(e.target as Node)) {
        setIsLangDropdownOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleCollapse = () => {
    setIsCollapsed(prev => {
      const next = !prev;
      try {
        localStorage.setItem('ld_sidebar_collapsed', String(next));
      } catch {}
      return next;
    });
  };

  const handleNavClick = (id: string, isAssistant?: boolean) => {
    if (isAssistant) {
      onOpenAssistant();
    } else {
      onSelectTab(id);
    }
    setDrawerOpen(false);
  };

  // Main Navigation Items (Dashboard, Markets, Signals, Analysis, Strategies, Performance, News, Settings/Assistant)
  const navItems = [
    {
      id: 'overview',
      labelEn: 'Dashboard (XAU/USD)',
      labelFr: 'Dashboard Or Spot',
      labelAr: 'لوحة تحكم الذهب',
      icon: LayoutDashboard,
      badge: 'OTC',
    },
    {
      id: 'markets',
      labelEn: 'Markets & OTC',
      labelFr: 'Marchés & OTC',
      labelAr: 'الأسواق والأسعار',
      icon: LineChart,
      badge: 'Live',
    },
    {
      id: 'chart',
      labelEn: 'SMC Graphic Terminal',
      labelFr: 'Terminal Graphique Or',
      labelAr: 'شارت الذهب التفاعلي',
      icon: BarChart2,
      badge: 'Live OTC',
    },
    {
      id: 'analysis',
      labelEn: 'Strategies',
      labelFr: 'Stratégies',
      labelAr: 'استراتيجية نيويورك IA',
      icon: Layers,
      badge: 'v2.0',
    },
    {
      id: 'performance',
      labelEn: 'Performance',
      labelFr: 'Performance & Audit',
      labelAr: 'سجل الأداء',
      icon: ShieldCheck,
      badge: undefined,
    },
    {
      id: 'news',
      labelEn: 'News & Macro',
      labelFr: 'Actualités & Macro',
      labelAr: 'الأخبار والمخاطر',
      icon: Newspaper,
      badge: undefined,
    },
    {
      id: 'account',
      labelEn: 'My account & trades',
      labelFr: 'Compte & trades',
      labelAr: 'حسابي وصفقاتي',
      icon: Wallet,
      badge: undefined,
    },
    ...(currentUser?.role === 'admin' ? [{
      id: 'admin',
      labelEn: 'Admin · users',
      labelFr: 'Admin · utilisateurs',
      labelAr: 'الإدارة · المستخدمون',
      icon: UserCog,
      badge: undefined,
    }] : []),
    {
      id: 'assistant',
      labelEn: 'AI Terminal',
      labelFr: 'Assistant IA',
      labelAr: 'المساعد الذكي',
      icon: Bot,
      isAction: true,
      badge: 'PRO',
    },
  ];

  return (
    <div 
      className={`min-h-screen flex flex-col font-sans bg-canvas text-slate-100 w-full max-w-full overflow-x-hidden selection:bg-gold-500/30 selection:text-gold-500 ${
        isAr ? 'rtl' : 'ltr'
      }`}
      dir={isAr ? 'rtl' : 'ltr'}
    >
      {/* ============================================================ */}
      {/* 1. TOP INSTITUTIONAL STATUS PULSE BAR */}
      {/* ============================================================ */}
      <div className="h-8 px-4 border-b border-line bg-canvas text-xs flex items-center justify-between gap-3 shrink-0 select-none whitespace-nowrap overflow-hidden">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline font-mono text-xs text-zinc-500 uppercase tracking-wider">MARKET STATUS</span>
            {selectedAsset?.isMarketOpen === false ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm bg-slate-500/10 text-slate-300 font-mono text-xs font-semibold border border-slate-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                MARKET CLOSED
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm bg-emerald-500/10 text-emerald-400 font-mono text-xs font-semibold border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                MARKET OPEN
              </span>
            )}
          </div>
          <span className="text-zinc-700 hidden sm:inline" aria-hidden="true">|</span>
          <div className="hidden sm:flex items-center gap-1.5 text-zinc-400 font-mono text-xs">
            <span className="text-zinc-500 uppercase">ENGINE</span>
            <span className="text-gold-500 font-bold">XAUUSD SWEEP+MSS+FVG · EURUSD TREND PULLBACK</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-1.5 text-zinc-400 font-mono text-xs">
            <Activity className="w-3 h-3 text-gold-500" aria-hidden="true" />
            <span className="text-zinc-300">DISCIPLINE: RISK 1% MAX</span>
          </div>
          <div className="hidden md:flex items-center gap-1.5 text-zinc-400 font-mono text-xs">
            <span className="text-zinc-500">SESSION</span>
            <span className={`font-semibold font-mono ${currentWindow ? 'text-emerald-400' : 'text-zinc-400'}`}>{currentWindow ?? 'OUTSIDE KILL ZONES'}</span>
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* 2. MAIN LAYOUT SHELL (Sidebar + Workspace Container) */}
      {/* ============================================================ */}
      <div className="flex-1 flex overflow-hidden w-full max-w-full">
        
        {/* ─── A. DESKTOP COLLAPSIBLE SIDEBAR (Left Menu) ─── */}
        <aside
          className={`hidden lg:flex flex-col border-r border-line bg-surface transition-[width] duration-200 ease-out shrink-0 select-none z-30 ${
            isCollapsed ? 'w-20' : 'w-64'
          }`}
        >
          {/* Sidebar Header Brand with Metallic Gold Accent */}
          <div className={`h-16 px-4 flex items-center ${isCollapsed ? 'justify-center' : 'justify-between'} border-b border-line shrink-0`}>
            {isCollapsed ? (
              <button
                onClick={toggleCollapse}
                className="p-1 rounded-xl hover:bg-white/[0.06] transition active:scale-95 cursor-pointer"
                title="Expand Sidebar"
                aria-label="Expand Sidebar"
              >
                <LDEmblem className="w-10 h-10" />
              </button>
            ) : (
              <div className="flex items-center gap-2.5 min-w-0">
                <LiquidityDissectionLogo size="sm" withText={true} />
              </div>
            )}

            {!isCollapsed && (
              <button
                onClick={toggleCollapse}
                className="h-9 w-9 flex items-center justify-center rounded-lg text-zinc-400 hover:text-white hover:bg-white/[0.06] transition cursor-pointer active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                title="Collapse Sidebar"
                aria-label="Toggle Sidebar"
              >
                {isAr ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
              </button>
            )}
          </div>

          {/* Sidebar Nav Links */}
          <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1.5 no-scrollbar">
            {!isCollapsed && (
              <div className="px-3 pb-2 text-xs font-bold uppercase tracking-wider text-zinc-500">
                {isFr ? 'Navigation Privée' : isAr ? 'أدوات المنصة' : 'Trading Modules'}
              </div>
            )}

            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              const label = isFr ? item.labelFr : isAr ? item.labelAr : item.labelEn;

              return (
                <button
                  key={item.id}
                  onClick={() => handleNavClick(item.id, item.isAction)}
                  title={isCollapsed ? label : undefined}
                  className={`w-full min-h-[44px] flex items-center gap-3 px-3 py-2.5 rounded-xl font-medium text-xs transition-all duration-150 cursor-pointer active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 ${
                    isCollapsed ? 'justify-center' : 'justify-between'
                  } ${
                    isActive
                      ? 'relative bg-gold-500/10 text-gold-300 font-semibold before:absolute before:inset-y-2 before:start-0 before:w-[3px] before:rounded-full before:bg-gold-400'
                      : 'text-zinc-400 hover:text-slate-100 hover:bg-white/[0.04]'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Icon className={`w-4 h-4 shrink-0 transition-colors ${
                      isActive ? 'text-gold-500' : 'text-zinc-400 group-hover:text-zinc-200'
                    }`} />
                    {!isCollapsed && (
                      <span className="truncate">{label}</span>
                    )}
                  </div>

                  {!isCollapsed && item.badge && (
                    <span className={`text-xs font-mono font-bold px-1.5 py-0.5 rounded border shrink-0 ${
                      isActive 
                        ? 'bg-gold-500/15 text-gold-300 border-gold-500/30' 
                        : 'bg-surface-3 text-zinc-400 border-line'
                    }`}>
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Sidebar Footer Desk Capital Widget */}
          <div className="p-3 border-t border-line bg-surface shrink-0 space-y-2">
            {isCollapsed ? (
              <button
                onClick={toggleCollapse}
                className="w-full h-10 flex items-center justify-center rounded-xl border border-line text-zinc-400 hover:text-gold-500 hover:border-gold-500/40 transition cursor-pointer active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                aria-label="Expand Sidebar"
              >
                {isAr ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </button>
            ) : (
              <div className="space-y-2">
                <div className="p-2.5 rounded-xl border border-line bg-surface-2">
                  <div className="flex items-center justify-between text-xs text-zinc-400 mb-1">
                    <span>{isFr ? 'Actif Dédié' : isAr ? 'الأصل المؤسساتي' : 'Dedicated Asset'}</span>
                    <span className="font-mono text-emerald-400 font-bold">1.0% Risk</span>
                  </div>
                  <div className="font-mono font-bold text-sm tracking-tight text-slate-100 flex items-center justify-between">
                    <span>XAU/USD SPOT</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-gold-500/15 text-gold-500 border border-gold-500/30">2 STRATEGIES</span>
                  </div>
                </div>

                {onOpenTelegram && (
                  <button
                    onClick={onOpenTelegram}
                    className="w-full min-h-[40px] flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-gold-gradient bg-gold-gradient-hover text-ink-strong font-semibold text-xs transition cursor-pointer active:scale-[0.98]"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span>{isFr ? 'Alertes Telegram' : isAr ? 'إشعارات تليجرام' : 'Telegram Desk'}</span>
                  </button>
                )}
              </div>
            )}
          </div>
        </aside>

        {/* ─── B. RIGHT WORKSPACE COLUMN (Header + Content) ─── */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden w-full max-w-full">
          
          {/* Top Navigation Bar (Header) */}
          <header className="h-16 px-4 sm:px-6 border-b border-line bg-surface/85 backdrop-blur-xl flex items-center justify-between gap-4 shrink-0 z-20">
            {/* Left: Mobile Drawer Trigger & Section Info */}
            <div className="flex items-center gap-3 min-w-0">
              <button
                onClick={() => setDrawerOpen(true)}
                className="lg:hidden h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl border border-line-2 text-zinc-200 hover:bg-white/[0.06] hover:border-gold-500/40 active:scale-95 transition cursor-pointer touch-manipulation shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                aria-label="Open Navigation Menu"
              >
                <Menu className="w-5 h-5 text-gold-500" />
              </button>

              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <span className="hidden xs:inline">Liquidity Dissection</span>
                  <span className="hidden xs:inline" aria-hidden="true">·</span>
                  <span className="text-gold-500 font-medium capitalize truncate">
                    {activeTab}
                  </span>
                </div>
                <h1 className="text-xs sm:text-base font-bold text-white tracking-tight truncate max-w-[130px] xs:max-w-[200px] sm:max-w-xs md:max-w-none">
                  {selectedAsset?.symbol} <span className="font-normal text-zinc-400 hidden sm:inline">· {selectedAsset?.name}</span>
                </h1>
              </div>
            </div>

            {/* Center: Global Search Input with ⌘K hotkey */}
            <div className="hidden md:flex items-center flex-1 max-w-xs relative">
              <Search className="w-4 h-4 text-zinc-400 absolute left-3 pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder={isFr ? 'Rechercher XAU/USD ou EUR/USD' : isAr ? 'بحث: XAU/USD أو EUR/USD' : 'Search XAU/USD or EUR/USD'}
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  if (onSelectAsset && e.target.value.trim().length > 0) {
                    onSelectAsset(e.target.value.trim().toUpperCase());
                  }
                }}
                className="w-full h-10 pl-9 pr-12 text-xs rounded-xl bg-surface-2 border border-line text-slate-100 placeholder-zinc-500 focus:outline-none focus:border-gold-500 focus:ring-4 focus:ring-gold-500/15 transition-all"
                aria-label="Global search"
              />
              <kbd className="absolute right-2.5 text-xs font-mono px-1.5 py-0.5 rounded bg-white/[0.06] text-gold-500 border border-line-2 pointer-events-none">
                ⌘K
              </kbd>
            </div>

            {/* Right: Actions, Language Switcher (FR/EN) & User Profile */}
            <div className="flex items-center gap-2 sm:gap-3 shrink-0">
              
              {/* Force Live Sync Refresh Button */}
              {onForceRefresh && (
                <button
                  onClick={onForceRefresh}
                  disabled={isSyncingLive}
                  title="Sync Live Prices"
                  className="h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl border border-line-2 hover:bg-white/[0.06] hover:border-gold-500/40 text-zinc-300 active:scale-95 transition cursor-pointer touch-manipulation focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  aria-label="Refresh Data"
                >
                  <RefreshCw className={`w-4 h-4 ${isSyncingLive ? 'animate-spin text-gold-500' : ''}`} />
                </button>
              )}

              {/* Language Switcher (FR / EN / AR) */}
              <div className="relative" ref={langDropdownRef}>
                <button
                  onClick={() => setIsLangDropdownOpen(!isLangDropdownOpen)}
                  className="h-11 min-h-[44px] px-3 flex items-center gap-1.5 rounded-xl border border-line-2 hover:bg-white/[0.06] hover:border-gold-500/40 text-xs font-bold text-zinc-200 transition cursor-pointer active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  aria-label="Language Selector"
                  aria-haspopup="listbox"
                  aria-expanded={isLangDropdownOpen}
                >
                  <Languages className="w-3.5 h-3.5 text-gold-500 shrink-0" />
                  <span className="uppercase text-xs font-mono">{lang}</span>
                  <ChevronDown className="w-3 h-3 text-zinc-400" />
                </button>

                {isLangDropdownOpen && (
                  <div className="absolute right-0 mt-1.5 w-32 rounded-xl border border-line-2 bg-surface-2 shadow-[var(--shadow-float)] p-1 z-50 animate-in fade-in zoom-in-95 duration-100">
                    {[
                      { code: 'fr', label: 'Français' },
                      { code: 'en', label: 'English' },
                      { code: 'ar', label: 'العربية' },
                    ].map((l) => (
                      <button
                        key={l.code}
                        onClick={() => {
                          setLang(l.code as any);
                          setIsLangDropdownOpen(false);
                        }}
                        className={`w-full min-h-[38px] flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition cursor-pointer ${
                          lang === l.code 
                            ? 'bg-gold-500 text-ink-strong font-bold' 
                            : 'text-zinc-300 hover:bg-white/[0.06] hover:text-gold-500'
                        }`}
                      >
                        <span>{l.label}</span>
                        {lang === l.code && <Check className="w-3.5 h-3.5" />}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* User Profile Badge */}
              <div className="relative" ref={userMenuRef}>
                <button
                  onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                  className="h-11 min-h-[44px] px-2.5 sm:px-3 flex items-center gap-2 rounded-xl border border-line-2 bg-surface-2 hover:border-gold-500/50 active:scale-95 transition cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  aria-label="User Profile Menu"
                  aria-expanded={isUserMenuOpen}
                >
                  <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-gold-500 to-gold-200 text-ink-strong flex items-center justify-center font-bold text-xs shrink-0">
                    <User className="w-3.5 h-3.5" />
                  </div>
                  <div className="hidden sm:block text-left text-xs">
                    <div className="font-semibold text-zinc-100 leading-tight">
                      {currentUser?.username || 'Private Trader'}
                    </div>
                    <div className="text-xs text-gold-500 font-mono">
                      {currentUser?.role || 'VIP Desk'}
                    </div>
                  </div>
                  <ChevronDown className="w-3 h-3 text-zinc-400 hidden sm:inline" />
                </button>

                {isUserMenuOpen && (
                  <div className="absolute right-0 mt-1.5 w-48 rounded-xl border border-line-2 bg-surface-2 shadow-[var(--shadow-float)] p-2 z-50 animate-in fade-in zoom-in-95 duration-100 space-y-1">
                    <div className="px-3 py-2 border-b border-line mb-1">
                      <div className="text-xs font-bold text-white truncate">
                        {currentUser?.username || 'Private Trader'}
                      </div>
                      <div className="text-xs text-gold-500 font-mono">
                        Institutional Tier
                      </div>
                    </div>

                    {onLogout && (
                      <button
                        onClick={() => {
                          setIsUserMenuOpen(false);
                          onLogout();
                        }}
                        className="w-full min-h-[38px] flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold text-rose-400 hover:bg-rose-950/30 transition cursor-pointer"
                      >
                        <LogOut className="w-4 h-4" />
                        <span>{isFr ? 'Déconnexion' : isAr ? 'تسجيل الخروج' : 'Logout'}</span>
                      </button>
                    )}
                  </div>
                )}
              </div>

            </div>
          </header>

          {/* Integrated Ticker Bar Slot */}
          {tickerBarSlot && (
            <div className="shrink-0 border-b border-line w-full max-w-full overflow-hidden">
              {tickerBarSlot}
            </div>
          )}

          {/* Main Content Area Container with Fluid CSS Grid / Flexbox */}
          <main className="flex-1 overflow-y-auto overflow-x-hidden px-4 sm:px-6 lg:px-8 py-5 sm:py-6 pb-28 lg:pb-8 w-full max-w-full">
            <div className="max-w-7xl mx-auto space-y-6 w-full">
              {children}
            </div>
          </main>

        </div>
      </div>

      {/* ============================================================ */}
      {/* 3. MOBILE HAMBURGER SLIDING OFF-CANVAS MENU */}
      {/* ============================================================ */}
      <AnimatePresence>
        {isDrawerOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDrawerOpen(false)}
              className="fixed inset-0 bg-black/70 backdrop-blur-xs z-50 lg:hidden"
            />

            <motion.div
              id="mobile-nav-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Mobile Navigation"
              initial={{ x: isAr ? '100%' : '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: isAr ? '100%' : '-100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 280 }}
              className={`fixed top-0 bottom-0 ${isAr ? 'right-0' : 'left-0'} w-80 max-w-[88vw] z-50 shadow-[var(--shadow-float)] flex flex-col border-r border-line bg-surface lg:hidden`}
            >
              {/* Drawer Header */}
              <div className="p-4 border-b border-line flex items-center justify-between shrink-0">
                <LiquidityDissectionLogo size="sm" withText={true} />
                <button
                  onClick={() => setDrawerOpen(false)}
                  className="h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl border border-line-2 text-zinc-400 hover:text-white hover:border-gold-500/40 active:scale-95 transition cursor-pointer"
                  aria-label="Close Navigation Menu"
                >
                  <X className="w-5 h-5 text-gold-500" />
                </button>
              </div>

              {/* Drawer Links */}
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                <div className="px-2 pb-2 text-xs font-bold uppercase tracking-wider text-zinc-500">
                  {isFr ? 'Modules Principaux' : isAr ? 'القائمة الرئيسية' : 'Private Desk Navigation'}
                </div>

                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = activeTab === item.id;
                  const label = isFr ? item.labelFr : isAr ? item.labelAr : item.labelEn;

                  return (
                    <button
                      key={item.id}
                      onClick={() => handleNavClick(item.id, item.isAction)}
                      className={`w-full min-h-[48px] flex items-center justify-between px-3.5 py-3 rounded-xl font-medium text-sm transition cursor-pointer active:scale-[0.98] ${
                        isActive
                          ? 'bg-gold-500/10 text-gold-300 font-semibold'
                          : 'text-zinc-300 hover:bg-white/[0.06] hover:text-gold-500'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <Icon className="w-5 h-5 text-gold-500 shrink-0" />
                        <span className="truncate">{label}</span>
                      </div>
                      {item.badge && (
                        <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-surface-3 text-zinc-400 border border-line">
                          {item.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Drawer Bottom Widget */}
              <div className="p-4 border-t border-line bg-surface space-y-2.5 pb-safe shrink-0">
                <div className="p-3 rounded-xl border border-line bg-surface-2">
                  <div className="text-xs text-zinc-400">Desk Capital</div>
                  <div className="font-mono font-bold text-sm text-white flex items-center justify-between mt-0.5">
                    <span>$5,000.00 USD</span>
                    <span className="text-gold-500 text-xs">1.0% Risk</span>
                  </div>
                </div>

                {onOpenTelegram && (
                  <button
                    onClick={() => {
                      setDrawerOpen(false);
                      onOpenTelegram();
                    }}
                    className="w-full min-h-[44px] flex items-center justify-center gap-2 p-2.5 rounded-xl bg-gold-gradient text-ink-strong font-semibold text-xs active:scale-[0.98] transition"
                  >
                    <Send className="w-4 h-4" />
                    <span>Telegram Desk</span>
                  </button>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

    </div>
  );
};
