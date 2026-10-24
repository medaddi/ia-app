import React, { useState } from 'react';
import {
  ShieldAlert,
  Sparkles,
  Languages,
  Send,
  Sun,
  Moon,
  Check,
  ChevronDown,
  Menu,
  User,
  LogOut,
  RefreshCw,
  Bot,
  Cloud,
  Activity,
  BarChart2,
  TrendingUp,
  Trophy,
  Newspaper,
  Calculator,
  Briefcase,
  History,
  Settings,
  Radio
} from 'lucide-react';
import { MarketAsset, Language } from '../types';
import { LiquidityDissectionLogo } from './LiquidityDissectionLogo';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  lang: Language;
  setLang: (lang: Language) => void;
  selectedAsset: MarketAsset;
  onOpenAssistant: () => void;
  onOpenTelegram: () => void;
  onOpenToolsDrawer: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  currentUser?: { id: string; username: string; role: string } | null;
  onLogout?: () => void;
  onForceRefresh?: () => void;
  isSyncingLive?: boolean;
  activeSignalsCount?: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  lang,
  setLang,
  onOpenAssistant,
  onOpenTelegram,
  onOpenToolsDrawer,
  theme,
  onToggleTheme,
  currentUser,
  onLogout,
  onForceRefresh,
  isSyncingLive = false,
  activeSignalsCount = 0,
}) => {
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  // 10 Required Navigation Tabs for Gold Trading Terminal
  const desktopNavTabs = [
    {
      id: 'overview',
      labelAr: 'الرئيسية',
      labelFr: 'Accueil',
      labelEn: '1. Overview',
      icon: Activity,
    },
    {
      id: 'chart',
      labelAr: 'شارت الذهب',
      labelFr: 'Graphique Or',
      labelEn: '2. Gold Chart',
      icon: BarChart2,
    },
    {
      id: 'analysis',
      labelAr: 'تحليل الذكاء الاصطناعي',
      labelFr: 'Analyse IA',
      labelEn: '3. AI Analysis',
      icon: Sparkles,
    },
    {
      id: 'signals',
      labelAr: 'إشارات التداول',
      labelFr: 'Signaux',
      labelEn: '4. Trade Signals',
      icon: TrendingUp,
      badge: activeSignalsCount > 0 ? activeSignalsCount : undefined,
    },
    {
      id: 'positions',
      labelAr: 'الصفقات المفتوحة',
      labelFr: 'Positions Ouvertes',
      labelEn: '5. Open Positions',
      icon: Briefcase,
    },
    {
      id: 'history',
      labelAr: 'سجل الصفقات',
      labelFr: 'Historique',
      labelEn: '6. Trade History',
      icon: History,
    },
    {
      id: 'performance',
      labelAr: 'تحليل الأداء',
      labelFr: 'Performance',
      labelEn: '7. Performance',
      icon: Trophy,
    },
    {
      id: 'risk',
      labelAr: 'إدارة المخاطر',
      labelFr: 'Gestion du Risque',
      labelEn: '8. Risk Management',
      icon: Calculator,
    },
    {
      id: 'telegram',
      labelAr: 'إعدادات تيليجرام',
      labelFr: 'Telegram',
      labelEn: '9. Telegram Settings',
      icon: Send,
    },
    {
      id: 'settings',
      labelAr: 'إعدادات النظام',
      labelFr: 'Paramètres',
      labelEn: '10. System Settings',
      icon: Settings,
    },
  ];

  return (
    <header className={`sticky top-0 z-40 backdrop-blur-xl border-b transition-colors duration-200 ${
      isLight ? 'bg-white/95 border-paper-line-2 shadow-xs' : 'bg-canvas/95 border-line shadow-2xl'
    }`}>
      {/* 1. Top Institutional Gold Pulse Bar */}
      <div className={`px-3 sm:px-4 py-1.5 border-b text-xs flex items-center justify-between gap-2 transition-colors ${
        isLight ? 'bg-paper border-paper-line-2 text-slate-700' : 'bg-canvas border-line text-slate-400'
      }`}>
        {/* Left Status Pulse */}
        <div className="flex items-center gap-2 min-w-0">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="animate-pulse absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
          </span>
          <span className={`font-extrabold uppercase tracking-wider text-xs sm:text-xs truncate ${
            isLight ? 'text-gold-700' : 'text-gold-400'
          }`}>
            {isFr ? 'XAU/USD · OTC SPOT · MOTEUR NY SILVER BULLET' : isAr ? 'XAU/USD · عقود الذهب الفورية · محرك NY SILVER BULLET' : 'XAU/USD · OTC SPOT · NY SILVER BULLET ENGINE'}
          </span>
          <span className="hidden lg:inline text-slate-400">•</span>
          <span className="hidden lg:inline font-mono font-medium text-xs text-zinc-400 truncate">
            {isFr ? 'Session New York (14:00 - 15:00 GMT) · M15 Liquidity & M5 Execution' : isAr ? 'جلسة نيويورك (14:00 - 15:00 GMT) · تحضير M15 وتنفيذ M5' : 'NY Killzone (14:00 - 15:00 GMT) · M15 Prep & M5 Execution'}
          </span>
        </div>

        {/* Right Status Actions */}
        <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
          {/* Telegram Settings Modal Trigger */}
          <button
            onClick={onOpenTelegram}
            className={`flex items-center gap-1 text-xs sm:text-xs px-2 py-0.5 rounded-md border font-semibold cursor-pointer transition ${
              isLight
                ? 'text-sky-700 bg-sky-50 border-sky-300 hover:bg-sky-100'
                : 'text-sky-400 bg-sky-950/40 border-sky-800/60 hover:bg-sky-900/40'
            }`}
            title="Telegram Bot Settings & Dispatch"
          >
            <Send className="w-3 h-3 text-sky-400" />
            <span className="hidden xs:inline sm:inline">Telegram Bot</span>
          </button>

          {/* Theme switcher */}
          <button
            onClick={onToggleTheme}
            className={`flex items-center gap-1 px-2 sm:px-2.5 py-1 rounded-lg text-xs font-semibold transition-all duration-150 border cursor-pointer ${
              isLight
                ? 'bg-white hover:bg-paper text-slate-700 border-paper-line-2'
                : 'bg-surface-2 hover:bg-surface-3 text-slate-300 border-line-2'
            }`}
          >
            {isLight ? (
              <>
                <Moon className="w-3.5 h-3.5 text-gold-700" />
                <span className="hidden xs:inline text-xs font-medium">Sombre</span>
              </>
            ) : (
              <>
                <Sun className="w-3.5 h-3.5 text-gold-400" />
                <span className="hidden xs:inline text-xs font-medium">Clair</span>
              </>
            )}
          </button>

          {/* Language Switcher Dropdown */}
          <div className="relative">
            <button
              onClick={() => setLangMenuOpen(!langMenuOpen)}
              className={`flex items-center gap-1 sm:gap-1.5 px-2 sm:px-2.5 py-1 rounded-lg text-xs font-semibold transition-all duration-150 border cursor-pointer ${
                isLight
                  ? 'bg-white hover:bg-paper text-slate-700 border-paper-line-2'
                  : 'bg-surface-2 hover:bg-surface-3 text-slate-300 border-line-2'
              }`}
            >
              <Languages className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-gold-500" />
              <span className="uppercase text-xs font-bold">{lang}</span>
              <ChevronDown className="w-3 h-3 text-slate-400" />
            </button>

            {langMenuOpen && (
              <div className={`absolute right-0 mt-2 w-36 rounded-xl shadow-xl border py-1 z-50 ${
                isLight ? 'bg-white border-paper-line-2 text-slate-800' : 'bg-surface-2 border-line-2 text-white'
              }`}>
                <button
                  onClick={() => {
                    setLang('fr');
                    setLangMenuOpen(false);
                  }}
                  className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between font-semibold hover:bg-gold-500/10 transition cursor-pointer ${
                    lang === 'fr' ? 'text-gold-700 font-bold bg-gold-500/10' : ''
                  }`}
                >
                  <span className="flex items-center gap-1.5">🇫🇷 Français</span>
                  {lang === 'fr' && <Check className="w-3.5 h-3.5 text-gold-500" />}
                </button>
                <button
                  onClick={() => {
                    setLang('ar');
                    setLangMenuOpen(false);
                  }}
                  className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between font-semibold hover:bg-gold-500/10 transition cursor-pointer ${
                    lang === 'ar' ? 'text-gold-700 font-bold bg-gold-500/10' : ''
                  }`}
                >
                  <span className="flex items-center gap-1.5">🇲🇦 العربية</span>
                  {lang === 'ar' && <Check className="w-3.5 h-3.5 text-gold-500" />}
                </button>
                <button
                  onClick={() => {
                    setLang('en');
                    setLangMenuOpen(false);
                  }}
                  className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between font-semibold hover:bg-gold-500/10 transition cursor-pointer ${
                    lang === 'en' ? 'text-gold-700 font-bold bg-gold-500/10' : ''
                  }`}
                >
                  <span className="flex items-center gap-1.5">🇬🇧 English</span>
                  {lang === 'en' && <Check className="w-3.5 h-3.5 text-gold-500" />}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 2. Main Navigation Row */}
      <div className="max-w-7xl mx-auto px-3 sm:px-4 py-2 sm:py-2.5 flex items-center justify-between gap-2 sm:gap-4">
        {/* Left: Drawer button + Brand Logo */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* 3-Bars Hamburger Button */}
          <button
            onClick={onOpenToolsDrawer}
            className={`flex items-center justify-center p-2 sm:p-2.5 rounded-xl text-xs font-bold transition-all duration-150 border cursor-pointer ${
              isLight
                ? 'bg-paper hover:bg-paper text-ink-strong border-paper-line-2 hover:border-gold-500'
                : 'bg-surface-2 hover:bg-surface-3 text-white border-line-2 hover:border-gold-500'
            }`}
            title={isFr ? 'Menu & Outils' : isAr ? 'القائمة والأدوات' : 'Menu & Tools'}
            aria-label="Toggle navigation menu"
          >
            <Menu className="w-4 h-4 sm:w-5 sm:h-5 text-gold-700 dark:text-gold-400" />
          </button>

          {/* Official Liquidity Dissection Logo */}
          <div onClick={() => setActiveTab('overview')} className="cursor-pointer">
            <LiquidityDissectionLogo size="sm" withText={true} theme={theme} />
          </div>
        </div>

        {/* Center: Desktop PC Navigation Bar (Visible on 2XL / XL screen, scrolling or compact) */}
        <nav className={`hidden xl:flex items-center gap-1 p-1 rounded-2xl border transition-all overflow-x-auto max-w-4xl ${
          isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
        }`}>
          {desktopNavTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const label = isAr ? tab.labelAr : isFr ? tab.labelFr : tab.labelEn;

            return (
              <button
                key={tab.id}
                onClick={() => {
                  if (tab.id === 'telegram') {
                    onOpenTelegram();
                  } else {
                    setActiveTab(tab.id);
                  }
                }}
                className={`relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-bold transition-all duration-150 cursor-pointer whitespace-nowrap ${
                  isActive
                    ? isLight
                      ? 'bg-white text-gold-700 shadow-xs border border-paper-line-2'
                      : 'bg-surface text-gold-400 shadow-xs border border-gold-700'
                    : isLight
                    ? 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-gold-500' : 'text-slate-400'}`} />
                <span>{label}</span>

                {tab.badge !== undefined && (
                  <span className="px-1.5 py-0.2 text-xs font-black rounded-full bg-emerald-500 text-white animate-pulse">
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Right: AI Assistant & Force Sync */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={onOpenAssistant}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-black bg-gradient-to-r from-gold-200 via-gold-500 to-gold-700 text-ink-strong hover:scale-105 transition shadow-md shadow-gold-500/20 cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5 text-ink-strong" />
            <span className="hidden sm:inline">AI Desk</span>
          </button>
        </div>
      </div>
    </header>
  );
};
