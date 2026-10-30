import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart2, Bell, BellOff, Bot, Check, ChevronDown, ChevronLeft, ChevronRight, Flame, Languages, Layers, LayoutDashboard, LineChart, LogOut, Menu,
  Newspaper, RefreshCw, Search, Send, ShieldCheck, UserCog, Wallet, X,
} from 'lucide-react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { MarketAsset, Language } from '../../types';
import { disableNotifications, enableNotifications, notifyEnabled, notifyPermission, registerServiceWorker } from '../../notifications';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS } from '../../instruments';
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

// Every visible text of the shell, in the three languages of the app: [English, Français, العربية]
const T = {
  dashboard: ['Dashboard', 'Tableau de bord', 'لوحة التحكم'],
  chart: ['Live chart', 'Graphique en direct', 'الشارت المباشر'],
  markets: ['Markets', 'Marchés', 'الأسواق'],
  strategies: ['Strategies', 'Stratégies', 'الاستراتيجيات'],
  performance: ['Signal results', 'Résultats des signaux', 'نتائج الإشارات'],
  news: ['News & calendar', 'Actualités & calendrier', 'الأخبار والأجندة'],
  account: ['My account & trades', 'Mon compte & trades', 'حسابي وصفقاتي'],
  admin: ['Users', 'Utilisateurs', 'المستخدمون'],
  assistant: ['AI assistant', 'Assistant IA', 'المساعد الذكي'],
  telegram: ['Telegram bot', 'Bot Telegram', 'بوت تيليغرام'],
  gTrading: ['Trading', 'Trading', 'التداول'],
  gResults: ['Results', 'Résultats', 'النتائج'],
  gAccount: ['Account', 'Compte', 'الحساب'],
  gTools: ['Tools', 'Outils', 'الأدوات'],
  marketOpen: ['Market open', 'Marché ouvert', 'السوق مفتوح'],
  marketClosed: ['Market closed', 'Marché fermé', 'السوق مغلق'],
  session: ['Session', 'Session', 'الجلسة'],
  engines: ['Strategies', 'Stratégies', 'الاستراتيجيات'],
  engineText: ['Gold · H1 breakout  ·  Forex · FXAlexG GPA', 'Or · breakout H1  ·  Forex · FXAlexG GPA', 'الذهب · اختراق H1  ·  الفوركس · FXAlexG GPA'],
  search: ['Search a pair… (XAU/USD, EUR/CHF)', 'Chercher une paire… (XAU/USD, EUR/CHF)', 'قلب على زوج… (XAU/USD، EUR/CHF)'],
  noMatch: ['No pair found', 'Aucune paire trouvée', 'ما كاين حتى زوج'],
  refresh: ['Refresh the data', 'Actualiser les données', 'تحديث المعطيات'],
  language: ['Language', 'Langue', 'اللغة'],
  signalsRunning: ['running signal(s)', 'signal(s) en cours', 'إشارة جارية'],
  notifyOn: ['Trade notifications on (click to turn off)', 'Notifications de trades activées (cliquer pour couper)', 'إشعارات الصفقات مفعلة (كليكي باش توقفها)'],
  notifyOff: ['Turn on trade notifications', 'Activer les notifications de trades', 'فعّل إشعارات الصفقات'],
  notifyBlocked: ['Notifications are blocked: allow them in the browser site settings', 'Notifications bloquées : autorisez-les dans les réglages du site', 'الإشعارات محبوسة: سمح ليها ف إعدادات الموقع ف المتصفح'],
  notifyTest: ['Notifications on: you will get one for every new trade', 'Notifications activées : une pour chaque nouveau trade', 'الإشعارات مفعلة: غادي توصلك وحدة على كل صفقة جديدة'],
  roleAdmin: ['Administrator', 'Administrateur', 'مدير'],
  roleUser: ['Trader', 'Trader', 'متداول'],
  logout: ['Log out', 'Se déconnecter', 'تسجيل الخروج'],
  openMenu: ['Open the menu', 'Ouvrir le menu', 'حل القائمة'],
  closeMenu: ['Close the menu', 'Fermer le menu', 'سد القائمة'],
  collapse: ['Collapse the sidebar', 'Réduire le menu', 'صغر القائمة'],
  expand: ['Expand the sidebar', 'Agrandir le menu', 'كبر القائمة'],
  userMenu: ['Account menu', 'Menu du compte', 'قائمة الحساب'],
  sessionAsia: ['Asia', 'Asie', 'آسيا'],
  sessionLondon: ['London', 'Londres', 'لندن'],
  sessionOverlap: ['London · New York', 'Londres · New York', 'لندن · نيويورك'],
  sessionNy: ['New York', 'New York', 'نيويورك'],
  sessionRollover: ['Rollover', 'Rollover', 'تبديل اليوم'],
} as const;
type Key = keyof typeof T;

interface NavItem { id: string; label: Key; icon: React.ComponentType<{ className?: string }>; action?: 'assistant' | 'telegram'; count?: number }

/** Forex session from the London clock, refreshed every minute. */
function useSession(): Key {
  const calc = (): Key => {
    const h = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', hour: '2-digit', hourCycle: 'h23' }).format(new Date()));
    return h < 7 ? 'sessionAsia' : h < 13 ? 'sessionLondon' : h < 17 ? 'sessionOverlap' : h < 22 ? 'sessionNy' : 'sessionRollover';
  };
  const [s, setS] = useState<Key>(calc);
  useEffect(() => { const id = setInterval(() => setS(calc()), 60000); return () => clearInterval(id); }, []);
  return s;
}

const initials = (name?: string) => (name || '?').slice(0, 2).toUpperCase();

export const AppLayout: React.FC<AppLayoutProps> = ({
  children, activeTab, onSelectTab, lang, setLang, selectedAsset, onSelectAsset, activeSignalsCount, isSyncingLive = false, onForceRefresh,
  onOpenAssistant, onOpenTelegram, isMobileDrawerOpen: controlledDrawerOpen, setIsMobileDrawerOpen: setControlledDrawerOpen, currentUser, onLogout,
  tickerBarSlot,
}) => {
  const isAr = lang === 'ar';
  const t = (k: Key) => T[k][lang === 'fr' ? 1 : isAr ? 2 : 0];
  const reduce = useReducedMotion();
  const session = useSession();
  const isAdmin = currentUser?.role === 'admin';

  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => { try { return localStorage.getItem('ld_sidebar_collapsed') === 'true'; } catch { return false; } });
  const [internalDrawerOpen, setInternalDrawerOpen] = useState(false);
  const isDrawerOpen = controlledDrawerOpen !== undefined ? controlledDrawerOpen : internalDrawerOpen;
  const setDrawerOpen = (open: boolean) => { setControlledDrawerOpen?.(open); setInternalDrawerOpen(open); };
  const [langOpen, setLangOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [hit, setHit] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const langRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);
  const searchBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isDrawerOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [isDrawerOpen]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); searchRef.current?.focus(); setSearchOpen(true); }
      if (e.key === 'Escape') { setLangOpen(false); setUserOpen(false); setSearchOpen(false); setDrawerOpen(false); }
    };
    const onDown = (e: MouseEvent) => {
      const out = (r: React.RefObject<HTMLDivElement | null>) => r.current && !r.current.contains(e.target as Node);
      if (out(langRef)) setLangOpen(false);
      if (out(userRef)) setUserOpen(false);
      if (out(searchBoxRef)) setSearchOpen(false);
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => { window.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onDown); };
  }, []);

  const toggleCollapse = () => setIsCollapsed(prev => { try { localStorage.setItem('ld_sidebar_collapsed', String(!prev)); } catch { /* storage blocked */ } return !prev; });

  const groups: { title: Key; items: NavItem[] }[] = [
    { title: 'gTrading', items: [
      { id: 'overview', label: 'dashboard', icon: LayoutDashboard },
      { id: 'chart', label: 'chart', icon: BarChart2, count: activeSignalsCount },
      { id: 'markets', label: 'markets', icon: LineChart },
      { id: 'analysis', label: 'strategies', icon: Layers },
    ] },
    { title: 'gResults', items: [
      { id: 'performance', label: 'performance', icon: ShieldCheck },
      { id: 'news', label: 'news', icon: Newspaper },
    ] },
    { title: 'gAccount', items: [
      { id: 'account', label: 'account', icon: Wallet },
      ...(isAdmin ? [{ id: 'admin', label: 'admin' as Key, icon: UserCog }] : []),
    ] },
    { title: 'gTools', items: [
      { id: 'assistant', label: 'assistant', icon: Bot, action: 'assistant' as const },
      ...(isAdmin && onOpenTelegram ? [{ id: 'telegram', label: 'telegram' as Key, icon: Send, action: 'telegram' as const }] : []),
    ] },
  ];
  const allItems = groups.flatMap(g => g.items);
  // Sub-pages light up their section: the account tabs → "My account", the technical view → "Live chart"
  const section = ['positions', 'history', 'settings'].includes(activeTab) ? 'account' : activeTab === 'technical' ? 'chart' : activeTab;
  const current = allItems.find(i => i.id === section);

  const go = (item: NavItem) => {
    if (item.action === 'assistant') onOpenAssistant();
    else if (item.action === 'telegram') onOpenTelegram?.();
    else onSelectTab(item.id);
    setDrawerOpen(false);
  };

  // Pair search: suggestions from the instruments the app analyses; Enter opens the chart of the highlighted one
  const matches = useMemo(() => {
    const q = query.trim().toUpperCase().replace(/[\s/]/g, '');
    return INSTRUMENT_SYMBOLS.filter(s => !q || s.replace('/', '').includes(q) || INSTRUMENT_LABELS[s].toUpperCase().includes(q)).slice(0, 9);
  }, [query]);
  const pick = (sym: string) => { onSelectAsset?.(sym); onSelectTab('chart'); setQuery(''); setSearchOpen(false); searchRef.current?.blur(); };

  const NavButton = ({ item, mobile = false }: { item: NavItem; mobile?: boolean }) => {
    const Icon = item.icon;
    const active = section === item.id;
    const compact = isCollapsed && !mobile;
    return (
      <button onClick={() => go(item)} title={compact ? t(item.label) : undefined} aria-current={active ? 'page' : undefined}
        className={`group relative w-full flex items-center gap-3 rounded-xl text-sm font-medium cursor-pointer transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 ${
          mobile ? 'min-h-[48px] px-3.5' : 'min-h-[42px] px-3'} ${compact ? 'justify-center' : ''} ${
          active ? 'text-gold-200' : 'text-zinc-400 hover:text-slate-100 hover:bg-white/[0.04]'}`}>
        {active && (
          <motion.span layoutId={mobile ? 'nav-active-m' : 'nav-active'} transition={{ duration: reduce ? 0 : 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-0 rounded-xl bg-gold-500/10 ring-1 ring-inset ring-gold-500/25">
            <span className="absolute inset-y-2 start-0 w-[3px] rounded-full bg-gold-400" />
          </motion.span>
        )}
        <Icon className={`relative w-[18px] h-[18px] shrink-0 transition-colors ${active ? 'text-gold-400' : 'text-zinc-500 group-hover:text-zinc-300'}`} />
        {!compact && <span className="relative truncate flex-1 text-start">{t(item.label)}</span>}
        {!!item.count && item.count > 0 && (
          <span className={`relative shrink-0 inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30 font-mono text-[11px] font-semibold ${
            compact ? 'absolute -top-0.5 end-1 px-1.5' : 'px-2 py-0.5'}`} aria-label={`${item.count} ${t('signalsRunning')}`}>
            {item.count}
          </span>
        )}
      </button>
    );
  };

  const UserCard = ({ mobile = false }: { mobile?: boolean }) => (
    <div className={`flex items-center gap-2.5 rounded-xl border border-line bg-surface-2/70 ${isCollapsed && !mobile ? 'flex-col p-2' : 'p-2.5'}`}>
      <span className="shrink-0 w-9 h-9 rounded-lg bg-gradient-to-br from-gold-200 to-gold-600 text-ink-strong flex items-center justify-center font-bold text-xs" aria-hidden="true">
        {initials(currentUser?.username)}
      </span>
      {!(isCollapsed && !mobile) && (
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-slate-100 truncate">{currentUser?.username}</div>
          <div className="text-[11px] text-gold-500">{isAdmin ? t('roleAdmin') : t('roleUser')}</div>
        </div>
      )}
      <div className={`flex ${isCollapsed && !mobile ? 'flex-col' : ''} gap-1`}>
        <button onClick={() => { onSelectTab('account'); setDrawerOpen(false); }} title={t('account')} aria-label={t('account')}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:text-gold-300 hover:bg-white/[0.05] cursor-pointer transition-colors">
          <Wallet className="w-4 h-4" />
        </button>
        {onLogout && (
          <button onClick={() => { setDrawerOpen(false); onLogout(); }} title={t('logout')} aria-label={t('logout')}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:text-rose-300 hover:bg-rose-500/10 cursor-pointer transition-colors">
            <LogOut className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );

  const open = selectedAsset?.isMarketOpen !== false;
  const Chevron = (isCollapsed ? !isAr : isAr) ? ChevronRight : ChevronLeft;

  return (
    <div className="min-h-screen flex flex-col font-sans bg-canvas text-slate-100 w-full max-w-full overflow-x-hidden selection:bg-gold-500/30" dir={isAr ? 'rtl' : 'ltr'}>
      {/* Status strip: market, session, strategies */}
      <div className="h-8 px-4 border-b border-line bg-canvas text-[11px] flex items-center justify-between gap-3 shrink-0 select-none whitespace-nowrap overflow-hidden">
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-semibold ring-1 ring-inset ${open ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25' : 'bg-slate-500/10 text-slate-300 ring-slate-500/25'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${open ? 'bg-emerald-400' : 'bg-slate-400'}`} aria-hidden="true" />
            {open ? t('marketOpen') : t('marketClosed')}
          </span>
          <span className="text-zinc-500">{t('session')} <span className="text-gold-300 font-medium">{t(session)}</span></span>
        </div>
        <span className="hidden md:inline text-zinc-500">{t('engines')} <span className="text-zinc-300">{t('engineText')}</span></span>
      </div>

      <div className="flex-1 flex overflow-hidden w-full max-w-full">
        {/* Desktop sidebar */}
        <aside className={`hidden lg:flex flex-col border-e border-line bg-surface transition-[width] duration-200 ease-out shrink-0 select-none z-30 ${isCollapsed ? 'w-[76px]' : 'w-64'}`}
          aria-label={t('openMenu')}>
          {/* Brand: the emblem centred and large, the name under it */}
          <button onClick={() => onSelectTab('overview')} aria-label={t('dashboard')}
            className={`group relative flex flex-col items-center justify-center gap-2 border-b border-line shrink-0 cursor-pointer ${isCollapsed ? 'py-4' : 'pt-5 pb-4'}`}>
            <span className="relative">
              <span className="absolute -inset-3 rounded-[30%] bg-gold-500/15 blur-xl opacity-70 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
              <LDEmblem className={`relative ${isCollapsed ? 'w-11 h-11' : 'w-16 h-16'}`} large={!isCollapsed} />
            </span>
            {!isCollapsed && (
              <span className="text-center leading-tight">
                <span className="block text-[13px] font-black uppercase tracking-[0.2em] text-white">
                  Liquidity <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-400 to-gold-600 bg-clip-text text-transparent">Dissection</span>
                </span>
                <span className="block mt-0.5 text-[10px] font-mono font-semibold uppercase tracking-[0.3em] text-gold-500">- Private Desk -</span>
              </span>
            )}
          </button>

          <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5 no-scrollbar">
            {groups.map(g => (
              <div key={g.title} className="space-y-1">
                {!isCollapsed ? <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{t(g.title)}</div>
                  : <div className="mx-auto w-6 h-px bg-line mb-2" aria-hidden="true" />}
                {g.items.map(item => <NavButton key={item.id} item={item} />)}
              </div>
            ))}
          </nav>

          <div className="p-3 border-t border-line shrink-0 space-y-2">
            {currentUser && <UserCard />}
            <button onClick={toggleCollapse} aria-label={isCollapsed ? t('expand') : t('collapse')} title={isCollapsed ? t('expand') : t('collapse')}
              className="w-full h-8 flex items-center justify-center gap-1.5 rounded-lg text-[11px] text-zinc-500 hover:text-gold-300 hover:bg-white/[0.05] cursor-pointer transition-colors">
              <Chevron className="w-4 h-4" />{!isCollapsed && t('collapse')}
            </button>
          </div>
        </aside>

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden w-full max-w-full">
          {/* Navbar */}
          <header className="h-16 px-3 sm:px-6 border-b border-line bg-surface/85 backdrop-blur-xl flex items-center justify-between gap-3 shrink-0 z-20">
            <div className="flex items-center gap-3 min-w-0">
              <button onClick={() => setDrawerOpen(true)} aria-label={t('openMenu')}
                className="lg:hidden h-11 w-11 flex items-center justify-center rounded-xl border border-line-2 text-gold-400 hover:bg-white/[0.06] cursor-pointer transition-colors shrink-0">
                <Menu className="w-5 h-5" />
              </button>
              <LDEmblem className="lg:hidden w-9 h-9" />
              <div className="min-w-0">
                <div className="text-[11px] text-zinc-500 truncate">LiquidityDissection</div>
                <h1 className="text-sm sm:text-base font-semibold text-white tracking-tight truncate">
                  {current ? t(current.label) : ''}
                  {['chart', 'technical'].includes(activeTab) && selectedAsset && <span className="text-zinc-400 font-normal"> · {selectedAsset.symbol}</span>}
                </h1>
              </div>
            </div>

            <div ref={searchBoxRef} className="hidden md:block relative flex-1 max-w-sm">
              <Search className="w-4 h-4 text-zinc-500 absolute start-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
              <input ref={searchRef} type="search" value={query} placeholder={t('search')} aria-label={t('search')} aria-expanded={searchOpen} aria-controls="pair-search"
                role="combobox" aria-autocomplete="list"
                onFocus={() => setSearchOpen(true)} onChange={e => { setQuery(e.target.value); setHit(0); setSearchOpen(true); }}
                onKeyDown={e => {
                  if (e.key === 'ArrowDown') { e.preventDefault(); setHit(h => Math.min(h + 1, matches.length - 1)); }
                  if (e.key === 'ArrowUp') { e.preventDefault(); setHit(h => Math.max(h - 1, 0)); }
                  if (e.key === 'Enter' && matches[hit]) pick(matches[hit]);
                }}
                className="w-full h-10 ps-9 pe-12 text-sm rounded-xl bg-surface-2 border border-line text-slate-100 placeholder:text-zinc-500 focus:outline-none focus:border-gold-500 focus:ring-4 focus:ring-gold-500/15 transition-[border-color,box-shadow]" />
              <kbd className="absolute end-2.5 top-1/2 -translate-y-1/2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.06] text-gold-500 border border-line-2 pointer-events-none">Ctrl K</kbd>
              <AnimatePresence>
                {searchOpen && (
                  <motion.ul id="pair-search" role="listbox" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}
                    className="absolute mt-1.5 w-full rounded-xl border border-line-2 bg-surface-2 shadow-[var(--shadow-float)] p-1 z-50">
                    {matches.length === 0 ? <li className="px-3 py-2 text-xs text-zinc-500">{t('noMatch')}</li> : matches.map((s, i) => (
                      <li key={s} role="option" aria-selected={i === hit}>
                        <button onMouseDown={e => { e.preventDefault(); pick(s); }} onMouseEnter={() => setHit(i)}
                          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm cursor-pointer ${i === hit ? 'bg-gold-500/10 text-gold-200' : 'text-zinc-300'}`}>
                          <span className="font-mono font-semibold">{s}</span><span className="text-xs text-zinc-500">{INSTRUMENT_LABELS[s]}</span>
                        </button>
                      </li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </div>

            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
              {activeSignalsCount > 0 && (
                <button onClick={() => onSelectTab('overview')} title={`${activeSignalsCount} ${t('signalsRunning')}`}
                  className="hidden sm:inline-flex h-10 items-center gap-1.5 px-3 rounded-xl bg-emerald-500/10 text-emerald-300 ring-1 ring-inset ring-emerald-500/30 text-xs font-semibold cursor-pointer hover:bg-emerald-500/15 transition-colors">
                  <Flame className="w-4 h-4" aria-hidden="true" />{activeSignalsCount}<span className="hidden xl:inline font-normal">{t('signalsRunning')}</span>
                </button>
              )}
              <NotifyButton t={t} />
              {onForceRefresh && (
                <button onClick={onForceRefresh} disabled={isSyncingLive} title={t('refresh')} aria-label={t('refresh')}
                  className="h-10 w-10 flex items-center justify-center rounded-xl border border-line-2 text-zinc-300 hover:bg-white/[0.06] hover:border-gold-500/40 cursor-pointer transition-colors">
                  <RefreshCw className={`w-4 h-4 ${isSyncingLive ? 'animate-spin text-gold-400' : ''}`} />
                </button>
              )}

              <div className="relative" ref={langRef}>
                <button onClick={() => setLangOpen(v => !v)} aria-label={t('language')} aria-haspopup="listbox" aria-expanded={langOpen}
                  className="h-10 px-2.5 flex items-center gap-1.5 rounded-xl border border-line-2 hover:bg-white/[0.06] hover:border-gold-500/40 text-xs font-semibold text-zinc-200 cursor-pointer transition-colors">
                  <Languages className="w-4 h-4 text-gold-500" aria-hidden="true" /><span className="uppercase font-mono">{lang}</span>
                </button>
                <AnimatePresence>
                  {langOpen && (
                    <motion.div role="listbox" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} transition={{ duration: 0.12 }}
                      className="absolute end-0 mt-1.5 w-36 rounded-xl border border-line-2 bg-surface-2 shadow-[var(--shadow-float)] p-1 z-50 origin-top">
                      {([['fr', 'Français'], ['en', 'English'], ['ar', 'العربية']] as const).map(([code, label]) => (
                        <button key={code} role="option" aria-selected={lang === code} onClick={() => { setLang(code as Language); setLangOpen(false); }}
                          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors ${lang === code ? 'bg-gold-500/15 text-gold-200 font-semibold' : 'text-zinc-300 hover:bg-white/[0.05]'}`}>
                          {label}{lang === code && <Check className="w-4 h-4" aria-hidden="true" />}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div className="relative" ref={userRef}>
                <button onClick={() => setUserOpen(v => !v)} aria-label={t('userMenu')} aria-haspopup="menu" aria-expanded={userOpen}
                  className="h-10 ps-1 pe-2 flex items-center gap-2 rounded-xl border border-line-2 bg-surface-2 hover:border-gold-500/50 cursor-pointer transition-colors">
                  <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-gold-200 to-gold-600 text-ink-strong flex items-center justify-center font-bold text-xs" aria-hidden="true">{initials(currentUser?.username)}</span>
                  <span className="hidden sm:block text-start leading-tight">
                    <span className="block text-xs font-semibold text-zinc-100 max-w-[110px] truncate">{currentUser?.username}</span>
                    <span className="block text-[10px] text-gold-500">{isAdmin ? t('roleAdmin') : t('roleUser')}</span>
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-zinc-500 hidden sm:block" aria-hidden="true" />
                </button>
                <AnimatePresence>
                  {userOpen && (
                    <motion.div role="menu" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} transition={{ duration: 0.12 }}
                      className="absolute end-0 mt-1.5 w-56 rounded-xl border border-line-2 bg-surface-2 shadow-[var(--shadow-float)] p-1.5 z-50 origin-top">
                      <div className="px-3 py-2 mb-1 border-b border-line">
                        <div className="text-sm font-semibold text-white truncate">{currentUser?.username}</div>
                        <div className="text-[11px] text-gold-500">{isAdmin ? t('roleAdmin') : t('roleUser')}</div>
                      </div>
                      {[
                        { k: 'account' as Key, icon: Wallet, on: () => onSelectTab('account') },
                        ...(isAdmin ? [{ k: 'admin' as Key, icon: UserCog, on: () => onSelectTab('admin') }] : []),
                        ...(isAdmin && onOpenTelegram ? [{ k: 'telegram' as Key, icon: Send, on: () => onOpenTelegram() }] : []),
                      ].map(({ k, icon: Icon, on }) => (
                        <button key={k} role="menuitem" onClick={() => { setUserOpen(false); on(); }}
                          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-zinc-300 hover:bg-white/[0.05] hover:text-gold-200 cursor-pointer transition-colors">
                          <Icon className="w-4 h-4 text-zinc-500" />{t(k)}
                        </button>
                      ))}
                      {onLogout && (
                        <button role="menuitem" onClick={() => { setUserOpen(false); onLogout(); }}
                          className="w-full flex items-center gap-2.5 px-3 py-2 mt-1 rounded-lg text-sm text-rose-300 hover:bg-rose-500/10 cursor-pointer transition-colors border-t border-line">
                          <LogOut className="w-4 h-4" />{t('logout')}
                        </button>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </header>

          {tickerBarSlot && <div className="shrink-0 border-b border-line w-full max-w-full overflow-hidden">{tickerBarSlot}</div>}

          <main className="flex-1 overflow-y-auto overflow-x-hidden px-4 sm:px-6 lg:px-8 py-5 sm:py-6 pb-28 lg:pb-8 w-full max-w-full">
            <div className="max-w-7xl mx-auto space-y-6 w-full">{children}</div>
          </main>
        </div>
      </div>

      {/* Mobile drawer */}
      <AnimatePresence>
        {isDrawerOpen && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setDrawerOpen(false)}
              className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 lg:hidden" aria-hidden="true" />
            <motion.div role="dialog" aria-modal="true" aria-label={t('openMenu')}
              initial={{ x: isAr ? '100%' : '-100%' }} animate={{ x: 0 }} exit={{ x: isAr ? '100%' : '-100%' }}
              transition={reduce ? { duration: 0 } : { type: 'spring', damping: 28, stiffness: 300 }}
              className={`fixed top-0 bottom-0 ${isAr ? 'right-0 border-s' : 'left-0 border-e'} w-80 max-w-[88vw] z-50 flex flex-col border-line bg-surface shadow-[var(--shadow-float)] lg:hidden`}>
              <div className="relative p-4 pt-6 border-b border-line flex flex-col items-center shrink-0">
                <LiquidityDissectionLogo size="lg" layout="vertical" withText />
                <button onClick={() => setDrawerOpen(false)} aria-label={t('closeMenu')}
                  className="absolute top-3 end-3 h-10 w-10 flex items-center justify-center rounded-xl border border-line-2 text-gold-400 hover:bg-white/[0.06] cursor-pointer transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <nav className="flex-1 overflow-y-auto p-4 space-y-5">
                {groups.map(g => (
                  <div key={g.title} className="space-y-1">
                    <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{t(g.title)}</div>
                    {g.items.map(item => <NavButton key={item.id} item={item} mobile />)}
                  </div>
                ))}
              </nav>
              {currentUser && <div className="p-4 border-t border-line pb-safe shrink-0"><UserCard mobile /></div>}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};


/** Bell in the top bar: turns the browser notifications for new trades on / off (the browser asks once). */
function NotifyButton({ t }: { t: (k: Key) => string }) {
  const [on, setOn] = useState(notifyEnabled);
  const [perm, setPerm] = useState(notifyPermission);
  useEffect(() => {
    const sync = () => { setOn(notifyEnabled()); setPerm(notifyPermission()); };
    window.addEventListener('ld-notify-change', sync);
    window.addEventListener('focus', sync);
    return () => { window.removeEventListener('ld-notify-change', sync); window.removeEventListener('focus', sync); };
  }, []);
  if (perm === 'unsupported') return null;
  const blocked = perm === 'denied';
  const label = blocked ? t('notifyBlocked') : on ? t('notifyOn') : t('notifyOff');
  const click = async () => {
    if (on) { disableNotifications(); return; }
    if (await enableNotifications()) {
      const reg = await registerServiceWorker();
      const opts = { body: t('notifyTest'), icon: '/brand/emblem-192.webp', tag: 'ld-test' };
      if (reg) reg.showNotification('LiquidityDissection', opts); else new Notification('LiquidityDissection', opts);
    }
    setPerm(notifyPermission());
  };
  return (
    <button onClick={click} title={label} aria-label={label} aria-pressed={on}
      className={`relative h-10 w-10 flex items-center justify-center rounded-xl border cursor-pointer transition-colors ${on ? 'border-gold-500/50 bg-gold-500/10 text-gold-300' : 'border-line-2 text-zinc-300 hover:bg-white/[0.06] hover:border-gold-500/40'} ${blocked ? 'opacity-60' : ''}`}>
      {on ? <Bell className="w-4 h-4" /> : <BellOff className="w-4 h-4" />}
      {on && <span className="absolute top-2 end-2 w-1.5 h-1.5 rounded-full bg-emerald-400" aria-hidden="true" />}
    </button>
  );
}
