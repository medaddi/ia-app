import React from 'react';

// ==========================================
// 1. TYPOGRAPHY SYSTEM
// ==========================================

export const SectionHeader: React.FC<{
  title: string;
  subtitle?: string;
  badge?: string;
  action?: React.ReactNode;
  className?: string;
}> = ({ title, subtitle, badge, action, className = '' }) => (
  <div className={`flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-white/[0.08] ${className}`}>
    <div>
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold tracking-tight text-zinc-100 uppercase font-mono">
          {title}
        </h2>
        {badge && (
          <span className="text-xs font-mono font-medium px-1.5 py-0.5 rounded border border-gold-500/30 bg-gold-500/10 text-gold-500">
            {badge}
          </span>
        )}
      </div>
      {subtitle && (
        <p className="text-xs text-zinc-400 mt-0.5">{subtitle}</p>
      )}
    </div>
    {action && <div className="shrink-0">{action}</div>}
  </div>
);

// ==========================================
// 2. BADGE SYSTEM
// ==========================================

export type BadgeVariant = 'buy' | 'sell' | 'warning' | 'neutral' | 'accent' | 'wait';

export const TradingBadge: React.FC<{
  variant?: BadgeVariant;
  children: React.ReactNode;
  size?: 'sm' | 'md';
  className?: string;
}> = ({ variant = 'neutral', children, size = 'sm', className = '' }) => {
  const variantStyles: Record<BadgeVariant, string> = {
    buy: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    sell: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    neutral: 'bg-zinc-800/80 text-zinc-300 border-zinc-700/50',
    accent: 'bg-gold-500/10 text-gold-500 border-gold-500/30',
    wait: 'bg-zinc-800/90 text-zinc-400 border-zinc-700/60',
  };

  const sizeStyles = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      className={`inline-flex items-center gap-1 font-mono font-medium rounded-md border tracking-wide uppercase ${variantStyles[variant]} ${sizeStyles} ${className}`}
    >
      {children}
    </span>
  );
};

// ==========================================
// 3. BUTTON SYSTEM
// ==========================================

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent';

export const TradingButton: React.FC<{
  variant?: ButtonVariant;
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  type?: 'button' | 'submit' | 'reset';
  fullWidth?: boolean;
}> = ({
  variant = 'secondary',
  size = 'md',
  icon,
  children,
  onClick,
  disabled = false,
  className = '',
  type = 'button',
  fullWidth = false,
}) => {
  const base = 'inline-flex items-center justify-center font-medium rounded-lg transition-colors cursor-pointer select-none active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/50';

  const sizeStyles = {
    sm: 'text-xs px-2.5 py-1.5 gap-1.5 h-8',
    md: 'text-xs px-3.5 py-2 gap-2 h-9',
    lg: 'text-sm px-4.5 py-2.5 gap-2.5 h-10',
  }[size];

  const variantStyles: Record<ButtonVariant, string> = {
    primary: 'bg-gold-500 hover:bg-gold-500 text-black font-semibold shadow-xs',
    accent: 'bg-gold-500/15 hover:bg-gold-500/25 text-gold-500 border border-gold-500/30',
    secondary: 'bg-surface-3 hover:bg-surface-3 text-zinc-200 border border-white/[0.08] hover:border-zinc-700',
    ghost: 'bg-transparent hover:bg-white/[0.05] text-zinc-400 hover:text-zinc-200',
    danger: 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/25',
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${sizeStyles} ${variantStyles[variant]} ${fullWidth ? 'w-full' : ''} ${className}`}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      <span>{children}</span>
    </button>
  );
};

// ==========================================
// 4. STAT / KPI DISPLAY CARD
// ==========================================

export const StatCard: React.FC<{
  title: string;
  value: string | number;
  change?: string;
  isPositive?: boolean;
  subtext?: string;
  badge?: string;
  className?: string;
}> = ({ title, value, change, isPositive, subtext, badge, className = '' }) => (
  <div className={`p-4 rounded-xl bg-surface-2 border border-white/[0.08] flex flex-col justify-between ${className}`}>
    <div className="flex items-center justify-between gap-2 text-xs text-zinc-400 mb-2">
      <span className="font-mono uppercase tracking-wider">{title}</span>
      {badge && (
        <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.06]">
          {badge}
        </span>
      )}
    </div>
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xl sm:text-2xl font-mono font-bold text-zinc-100 tracking-tight">
        {value}
      </span>
      {change && (
        <span
          className={`text-xs font-mono font-semibold ${
            isPositive !== undefined
              ? isPositive
                ? 'text-emerald-400'
                : 'text-rose-400'
              : 'text-zinc-400'
          }`}
        >
          {change}
        </span>
      )}
    </div>
    {subtext && (
      <p className="text-xs text-zinc-500 font-mono mt-2 truncate">{subtext}</p>
    )}
  </div>
);

// ==========================================
// 5. REGIME INDICATOR BADGE
// ==========================================

export const MarketRegimeTag: React.FC<{ regime: string }> = ({ regime }) => {
  const norm = (regime || '').toUpperCase();

  if (norm.includes('TRENDING UP') || norm.includes('BULLISH')) {
    return <TradingBadge variant="buy">TRENDING UP</TradingBadge>;
  }
  if (norm.includes('TRENDING DOWN') || norm.includes('BEARISH')) {
    return <TradingBadge variant="sell">TRENDING DOWN</TradingBadge>;
  }
  if (norm.includes('RANG') || norm.includes('CONSOLIDATION')) {
    return <TradingBadge variant="neutral">RANGING</TradingBadge>;
  }
  if (norm.includes('BREAKOUT')) {
    return <TradingBadge variant="accent">BREAKOUT</TradingBadge>;
  }
  if (norm.includes('HIGH VOLATIL')) {
    return <TradingBadge variant="warning">HIGH VOLATILITY</TradingBadge>;
  }
  if (norm.includes('WAIT') || norm.includes('UNCERTAIN')) {
    return <TradingBadge variant="wait">WAIT / UNCERTAIN</TradingBadge>;
  }

  return <TradingBadge variant="neutral">{regime || 'UNCERTAIN'}</TradingBadge>;
};
