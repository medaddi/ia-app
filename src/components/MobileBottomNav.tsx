import React from 'react';
import { 
  Activity, 
  TrendingUp, 
  BarChart2, 
  Briefcase, 
  Menu
} from 'lucide-react';
import { Language } from '../types';

interface MobileBottomNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  lang: Language;
  theme: 'light' | 'dark';
  onOpenAssistant: () => void;
  onOpenTelegram: () => void;
  onOpenMenu?: () => void;
  activeSignalsCount: number;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  activeTab,
  setActiveTab,
  lang,
  theme,
  onOpenMenu,
  activeSignalsCount
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const navItems = [
    {
      id: 'overview',
      labelAr: 'الرئيسية',
      labelFr: 'Accueil',
      labelEn: 'Home',
      icon: Activity
    },
    {
      id: 'signals',
      labelAr: 'الصفقات',
      labelFr: 'Signaux',
      labelEn: 'Signals',
      icon: TrendingUp,
      badge: activeSignalsCount > 0 ? activeSignalsCount : undefined
    },
    {
      id: 'chart',
      labelAr: 'الشارت',
      labelFr: 'Graphique',
      labelEn: 'Chart',
      icon: BarChart2
    },
    {
      id: 'positions',
      labelAr: 'المحفظة',
      labelFr: 'Positions',
      labelEn: 'Positions',
      icon: Briefcase
    },
    {
      id: 'menu',
      labelAr: 'المزيد',
      labelFr: 'Menu',
      labelEn: 'Menu',
      icon: Menu,
      isMenuTrigger: true
    }
  ];

  return (
    <nav 
      aria-label="Mobile Bottom Navigation"
      className={`fixed bottom-0 inset-x-0 z-40 lg:hidden border-t backdrop-blur-2xl transition-all duration-200 pb-safe ${
        isLight 
          ? 'bg-white/90 border-paper-line-2 shadow-[0_-4px_20px_rgba(0,0,0,0.05)]' 
          : 'bg-surface/90 border-line shadow-[0_-8px_24px_rgba(0,0,0,0.5)]'
      }`}
    >
      <div className="grid grid-cols-5 h-16 max-w-lg mx-auto px-1 items-center">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          const label = isAr ? item.labelAr : isFr ? item.labelFr : item.labelEn;

          return (
            <button
              key={item.id}
              onClick={() => {
                if (item.isMenuTrigger) {
                  if (onOpenMenu) onOpenMenu();
                } else {
                  setActiveTab(item.id);
                }
              }}
              aria-current={isActive ? 'page' : undefined}
              className={`relative min-h-[48px] h-full flex flex-col items-center justify-center py-1 transition-colors duration-150 active:scale-95 cursor-pointer touch-manipulation select-none ${
                isActive
                  ? isLight
                    ? 'text-gold-700'
                    : 'text-gold-300'
                  : isLight
                  ? 'text-slate-500 hover:text-slate-800'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {/* Active Indicator Top Pill */}
              {isActive && (
                <span aria-hidden="true" className="absolute top-0 w-8 h-0.5 rounded-full bg-gold-400" />
              )}

              {/* Icon Container with Badge */}
              <div className={`relative px-3 py-1 rounded-full transition-colors ${
                isActive
                  ? isLight
                    ? 'bg-gold-100'
                    : 'bg-gold-500/10'
                  : ''
              }`}>
                <Icon className="w-5 h-5" aria-hidden="true" />
                
                {/* Real-time active badge */}
                {item.badge !== undefined && (
                  <span className="absolute -top-1 -right-2 px-1 min-w-[18px] h-[18px] flex items-center justify-center text-[11px] font-bold rounded-full bg-emerald-500 text-canvas ring-2 ring-surface tabular-nums">
                    {item.badge}
                  </span>
                )}


              </div>

              {/* Label */}
              <span className={`text-xs tracking-tight mt-0.5 font-medium transition-colors ${
                isActive ? 'font-semibold' : ''
              }`}>
                {label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
