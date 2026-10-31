import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart2, Bell, BellOff, Bot, Check, ChevronDown, ChevronLeft, ChevronRight, Flame, Languages, Layers, LayoutDashboard, LineChart, LogOut, Menu,
  Newspaper, RefreshCw, Search, Send, ShieldCheck, UserCog, Wallet, X,
} from 'lucide-react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { MarketAsset, Language } from '../../types';
import { disableNotifications, enableNotifications, notifyEnabled, notifyPermission, registerServiceWorker } from '../../notifications';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS } from '../../instruments';
import { LDEmblem } from '../LiquidityDissectionLogo';

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
  engineText: ['Gold · breakout + reversion H1  ·  EUR, GBP · RSI(2) H4  ·  Forex · FXAlexG GPA', 'Or · breakout + réversion H1  ·  EUR, GBP · RSI(2) H4  ·  Forex · FXAlexG GPA', 'الذهب · اختراق + ارتداد H1  ·  EUR، GBP · RSI(2) H4  ·  الفوركس · FXAlexG GPA'],
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
  privateDesk: ['Private desk', 'Desk privé', 'المكتب الخاص'],
  pairs: ['Pairs', 'Paires', 'الأزواج'],
  ctaTitle: ['Signals on Telegram', 'Signaux sur Telegram', 'الإشارات ف تيليغرام'],
  ctaText: ['Every trade with the lot for your risk, the moment it is taken', 'Chaque trade avec le lot pour votre risque, dès qu’il est pris', 'كل صفقة باللوت ديال المخاطرة ديالك، فاللحظة لي كتاخد'],
  ctaButton: ['Link Telegram', 'Lier Telegram', 'ربط تيليغرام'],
  ctaLinked: ['Telegram linked', 'Telegram lié', 'تيليغرام مربوط'],
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

  const activePair = ['chart', 'technical'].includes(activeTab) ? selectedAsset?.symbol : undefined;
  const [pairsOpen, setPairsOpen] = useState(true);
  const [flyout, setFlyout] = useState<{ top: number; x: number } | null>(null);  // collapsed: pairs card next to the chart icon
  const openPair = (sym: string) => { onSelectAsset?.(sym); onSelectTab('chart'); setFlyout(null); setDrawerOpen(false); };
  const showFlyout = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    setFlyout({ top: Math.min(r.top, window.innerHeight - 380), x: isAr ? window.innerWidth - r.left + 12 : r.right + 12 });
  };

  const NavButton = ({ item, mobile = false }: { item: NavItem; mobile?: boolean }) => {
    const Icon = item.icon;
    const active = section === item.id;
    const compact = isCollapsed && !mobile;
    const tree = item.id === 'chart';  // the live chart opens into the pairs, like a sub-menu
    const btn = (
      <button onClick={() => { if (tree && !compact && active) setPairsOpen(o => !o); go(item); }} title={compact ? t(item.label) : undefined}
        aria-current={active ? 'page' : undefined} aria-expanded={tree && !compact ? pairsOpen && active : undefined}
        className={`group relative w-full flex items-center gap-3 rounded-2xl text-[13px] font-medium cursor-pointer transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/70 ${
          mobile ? 'min-h-[48px] px-3.5' : 'min-h-[44px] px-3'} ${compact ? 'justify-center w-11 mx-auto px-0' : ''} ${
          active ? 'text-white' : 'text-zinc-400 hover:text-slate-100 hover:bg-white/[0.035]'}`}>
        {active && (
          <motion.span layoutId={mobile ? 'nav-active-m' : 'nav-active'} transition={{ duration: reduce ? 0 : 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-0 rounded-2xl bg-white/[0.06] ring-1 ring-inset ring-white/[0.06] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]" />
        )}
        <Icon className={`relative w-[18px] h-[18px] shrink-0 transition-colors ${active ? 'text-gold-400' : 'text-zinc-500 group-hover:text-zinc-300'}`} />
        {!compact && <span className="relative truncate flex-1 text-start">{t(item.label)}</span>}
        {!!item.count && item.count > 0 && (
          <span className={`relative shrink-0 inline-flex items-center rounded-full bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30 font-mono text-[10px] font-semibold ${
            compact ? 'absolute -top-1 -end-1 px-1.5' : 'px-1.5 py-0.5'}`} aria-label={`${item.count} ${t('signalsRunning')}`}>
            {item.count}
          </span>
        )}
        {tree && !compact && (
          <ChevronDown className={`relative w-3.5 h-3.5 shrink-0 text-zinc-500 transition-transform duration-200 ${active && pairsOpen ? 'rotate-180 text-gold-400' : ''}`} aria-hidden="true" />
        )}
      </button>
    );
    if (!tree) return btn;
    const list = (inFlyout: boolean) => (
      <ul className={inFlyout ? 'space-y-0.5' : 'relative ms-[22px] mt-1 mb-1 space-y-0.5 ps-3'}>
        {!inFlyout && <span className="absolute start-0 top-0 bottom-3 w-px bg-line-2" aria-hidden="true" />}
        {INSTRUMENT_SYMBOLS.map(sym => {
          const on = activePair === sym;
          return (
            <li key={sym} className="relative">
              {!inFlyout && <span className="absolute -start-3 top-1/2 w-2.5 h-px bg-line-2" aria-hidden="true" />}
              <button onClick={() => openPair(sym)} aria-current={on ? 'true' : undefined}
                className={`w-full flex items-center justify-between gap-2 rounded-xl px-2.5 h-8 text-xs cursor-pointer transition-colors ${
                  on ? 'bg-white/[0.06] text-white font-semibold' : 'text-zinc-400 hover:text-slate-100 hover:bg-white/[0.035]'}`}>
                <span className="font-mono">{sym}</span>
                <span className={`text-[10px] truncate ${on ? 'text-gold-300' : 'text-zinc-600'}`}>{INSTRUMENT_LABELS[sym]}</span>
              </button>
            </li>
          );
        })}
      </ul>
    );
    if (compact) {
      // Collapsed: the pairs open in a floating card next to the icon
      return (
        <div className="relative" onMouseEnter={e => showFlyout(e.currentTarget)} onMouseLeave={() => setFlyout(null)} onFocus={e => showFlyout(e.currentTarget)}
          onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setFlyout(null); }}>
          {btn}
          <AnimatePresence>
            {flyout && (
              <motion.div initial={{ opacity: 0, x: isAr ? 6 : -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: isAr ? 6 : -6 }} transition={{ duration: 0.14 }}
                style={{ top: flyout.top, [isAr ? 'right' : 'left']: flyout.x - 12 }} className="fixed ps-3 pe-3 z-50">
                <div className="w-52 rounded-2xl border border-line-2 bg-surface-2 shadow-[0_20px_50px_-12px_rgba(0,0,0,0.85)] p-1.5">
                  <div className="px-2.5 pt-1 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{t('pairs')}</div>
                  {list(true)}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      );
    }
    return (
      <div>
        {btn}
        <AnimatePresence initial={false}>
          {active && pairsOpen && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              transition={{ duration: reduce ? 0 : 0.2, ease: [0.22, 1, 0.36, 1] }} className="overflow-hidden">
              {list(false)}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  };

  const open = selectedAsset?.isMarketOpen !== false;
  const Chevron = (isCollapsed ? !isAr : isAr) ? ChevronRight : ChevronLeft;

  // One panel for the desktop sidebar and the mobile drawer
  const SidebarBody = ({ mobile = false }: { mobile?: boolean }) => {
    const compact = isCollapsed && !mobile;
    return (
      <>
        {/* Brand card: the emblem and the desk name, the collapse button on the panel edge */}
        <div className={`relative shrink-0 ${compact ? 'px-2 pt-5 pb-3' : 'px-4 pt-5 pb-3'}`}>
          <button onClick={() => { onSelectTab('overview'); setDrawerOpen(false); }} aria-label={t('dashboard')}
            className={`group w-full flex items-center gap-3 rounded-2xl cursor-pointer ${compact ? 'justify-center' : ''}`}>
            <span className="relative shrink-0">
              <span className="absolute -inset-2 rounded-full bg-gold-500/20 blur-lg opacity-60 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
              <LDEmblem className={`relative !rounded-full ring-2 ring-gold-500/30 ${compact ? 'w-11 h-11' : 'w-12 h-12'}`} />
            </span>
            {!compact && (
              <span className="min-w-0 text-start leading-tight">
                <span className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-500">{t('privateDesk')}</span>
                <span className="block mt-0.5 text-sm font-bold text-white truncate">
                  Liquidity <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-400 to-gold-600 bg-clip-text text-transparent">Dissection</span>
                </span>
              </span>
            )}
          </button>
          {!mobile && (
            <button onClick={toggleCollapse} aria-label={isCollapsed ? t('expand') : t('collapse')} title={isCollapsed ? t('expand') : t('collapse')}
              className="absolute top-8 -end-3 w-6 h-6 rounded-full border border-line-2 bg-surface-3 text-zinc-400 hover:text-gold-300 hover:border-gold-500/50 flex items-center justify-center cursor-pointer shadow-md transition-colors z-10">
              <Chevron className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <nav className={`flex-1 overflow-y-auto no-scrollbar ${compact ? 'px-2 py-2 space-y-4' : 'px-3 py-2 space-y-5'}`}>
          {groups.map(g => (
            <div key={g.title} className="space-y-1">
              {!compact ? <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-500/80">{t(g.title)}</div>
                : <div className="text-center pb-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-zinc-600 truncate">{t(g.title)}</div>}
              {g.items.map(item => <React.Fragment key={item.id}>{NavButton({ item, mobile })}</React.Fragment>)}
            </div>
          ))}
        </nav>

        {/* Call to action: link Telegram (lot for my risk on every trade) */}
        <div className={`shrink-0 ${compact ? 'p-3 flex justify-center' : 'p-3'} ${mobile ? 'pb-safe' : ''}`}>
          {compact ? (
            <button onClick={() => onSelectTab('account')} title={t('ctaButton')} aria-label={t('ctaButton')}
              className="w-11 h-11 rounded-2xl bg-gradient-to-b from-gold-300 to-gold-600 text-ink-strong flex items-center justify-center shadow-[0_8px_24px_-8px_rgba(214,174,87,0.7)] hover:brightness-110 cursor-pointer transition">
              <Send className="w-4 h-4" />
            </button>
          ) : (
            <div className="rounded-3xl border border-white/[0.06] bg-gradient-to-b from-white/[0.05] to-white/[0.015] p-4 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
              <div className="text-sm font-semibold text-white">{t('ctaTitle')}</div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-400">{t('ctaText')}</p>
              <button onClick={() => { onSelectTab('account'); setDrawerOpen(false); }}
                className="mt-3 w-full h-10 rounded-2xl bg-gradient-to-b from-gold-300 to-gold-600 text-ink-strong text-xs font-bold inline-flex items-center justify-center gap-2 shadow-[0_10px_28px_-10px_rgba(214,174,87,0.8)] hover:brightness-110 cursor-pointer transition">
                <Send className="w-4 h-4" />{t('ctaButton')}
              </button>
            </div>
          )}
        </div>
      </>
    );
  };

  return (
    <div className="h-dvh flex flex-col font-sans bg-canvas text-slate-100 w-full max-w-full overflow-x-hidden selection:bg-gold-500/30" dir={isAr ? 'rtl' : 'ltr'}>
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
        {/* Desktop sidebar: a floating rounded panel */}
        <aside className={`hidden lg:flex shrink-0 select-none z-30 p-3 pe-0 transition-[width] duration-200 ease-out ${isCollapsed ? 'w-[100px]' : 'w-[276px]'}`} aria-label={t('openMenu')}>
          <div className="relative flex-1 flex flex-col min-h-0 rounded-[28px] border border-white/[0.06] bg-gradient-to-b from-surface-2 to-surface shadow-[0_24px_60px_-24px_rgba(0,0,0,0.8),inset_0_1px_0_rgba(255,255,255,0.04)]">
            {SidebarBody({})}
          </div>
        </aside>

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden w-full max-w-full">
          {/* Navbar */}
          <div className="shrink-0 z-20 px-3 sm:px-4 lg:px-5 pt-3">
          <header className="h-16 px-3 sm:px-4 rounded-[22px] border border-white/[0.06] bg-surface-2/80 backdrop-blur-xl shadow-[0_18px_40px_-22px_rgba(0,0,0,0.8),inset_0_1px_0_rgba(255,255,255,0.04)] flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <button onClick={() => setDrawerOpen(true)} aria-label={t('openMenu')}
                className="lg:hidden h-11 w-11 flex items-center justify-center rounded-2xl border border-line-2 text-gold-400 hover:bg-white/[0.06] cursor-pointer transition-colors shrink-0">
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
                className="w-full h-10 ps-9 pe-12 text-sm rounded-2xl bg-canvas/60 border border-line text-slate-100 placeholder:text-zinc-500 focus:outline-none focus:border-gold-500 focus:ring-4 focus:ring-gold-500/15 transition-[border-color,box-shadow]" />
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
                  className="hidden sm:inline-flex h-10 items-center gap-1.5 px-3 rounded-2xl bg-emerald-500/10 text-emerald-300 ring-1 ring-inset ring-emerald-500/30 text-xs font-semibold cursor-pointer hover:bg-emerald-500/15 transition-colors">
                  <Flame className="w-4 h-4" aria-hidden="true" />{activeSignalsCount}<span className="hidden xl:inline font-normal">{t('signalsRunning')}</span>
                </button>
              )}
              <NotifyButton t={t} />
              {onForceRefresh && (
                <button onClick={onForceRefresh} disabled={isSyncingLive} title={t('refresh')} aria-label={t('refresh')}
                  className="h-10 w-10 flex items-center justify-center rounded-2xl border border-line-2 text-zinc-300 hover:bg-white/[0.06] hover:border-gold-500/40 cursor-pointer transition-colors">
                  <RefreshCw className={`w-4 h-4 ${isSyncingLive ? 'animate-spin text-gold-400' : ''}`} />
                </button>
              )}

              <div className="relative" ref={langRef}>
                <button onClick={() => setLangOpen(v => !v)} aria-label={t('language')} aria-haspopup="listbox" aria-expanded={langOpen}
                  className="h-10 px-2.5 flex items-center gap-1.5 rounded-2xl border border-line-2 hover:bg-white/[0.06] hover:border-gold-500/40 text-xs font-semibold text-zinc-200 cursor-pointer transition-colors">
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
                  className="h-10 ps-1 pe-2 flex items-center gap-2 rounded-2xl border border-line-2 bg-canvas/40 hover:border-gold-500/50 cursor-pointer transition-colors">
                  <span className="w-8 h-8 rounded-full bg-gradient-to-br from-gold-200 to-gold-600 text-ink-strong flex items-center justify-center font-bold text-xs" aria-hidden="true">{initials(currentUser?.username)}</span>
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
          </div>

          {tickerBarSlot && <div className="shrink-0 border-b border-line w-full max-w-full overflow-hidden">{tickerBarSlot}</div>}

          <main className="flex-1 overflow-y-auto overflow-x-hidden px-4 sm:px-6 lg:px-8 py-4 sm:py-5 pb-28 lg:pb-8 w-full max-w-full">
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
              initial={{ x: isAr ? '110%' : '-110%' }} animate={{ x: 0 }} exit={{ x: isAr ? '110%' : '-110%' }}
              transition={reduce ? { duration: 0 } : { type: 'spring', damping: 28, stiffness: 300 }}
              className={`fixed top-3 bottom-3 ${isAr ? 'right-3' : 'left-3'} w-80 max-w-[86vw] z-50 flex flex-col rounded-[28px] border border-white/[0.07] bg-gradient-to-b from-surface-2 to-surface shadow-[var(--shadow-float)] lg:hidden`}>
              <button onClick={() => setDrawerOpen(false)} aria-label={t('closeMenu')}
                className="absolute top-5 end-4 h-10 w-10 flex items-center justify-center rounded-2xl border border-line-2 text-gold-400 hover:bg-white/[0.06] cursor-pointer transition-colors z-10">
                <X className="w-5 h-5" />
              </button>
              {SidebarBody({ mobile: true })}
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
