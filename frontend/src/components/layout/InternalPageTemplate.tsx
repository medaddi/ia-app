import React from 'react';
import { ChevronRight, Home, ArrowLeft, Layers, PlusCircle, Sparkles, Database, Sliders } from 'lucide-react';
import { motion } from 'motion/react';

export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
  icon?: React.ComponentType<{ className?: string }>;
}

export interface InternalPageTemplateProps {
  /** Page Title displayed in large heading */
  title: string;
  /** Supporting subtitle or analytical description */
  subtitle?: string;
  /** Breadcrumb items array (defaults to Home > Current Page if omitted) */
  breadcrumbs?: BreadcrumbItem[];
  /** Optional back navigation handler */
  onBack?: () => void;
  /** Optional status pill or badge (e.g. 'Live Audit', 'Verified 99.8%') */
  badge?: {
    label: string;
    variant?: 'gold' | 'emerald' | 'rose' | 'neutral';
  };
  /** Optional actions placed on the right side of the header (buttons, filters) */
  headerActions?: React.ReactNode;
  /** Top metrics / quick statistics grid slot */
  statsSlot?: React.ReactNode;
  /** Primary content slot (if omitted, default responsive grid of empty cards is rendered) */
  children?: React.ReactNode;
  /** Optional side column or secondary widgets */
  asideSlot?: React.ReactNode;
}

/**
 * Standard Institutional Card Component with Obsidian & Metallic Gold Accents
 */
export const InternalCard: React.FC<{
  title?: string;
  subtitle?: string;
  badge?: string;
  headerAction?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  goldHover?: boolean;
}> = ({ title, subtitle, badge, headerAction, children, className = '', goldHover = true }) => {
  return (
    <div
      className={`rounded-2xl border border-white/[0.08] bg-surface-3 p-5 sm:p-6 transition-all duration-200 shadow-xl ${
        goldHover ? 'hover:border-gold-500/40 hover:shadow-[0_4px_24px_rgba(0,0,0,0.6)]' : ''
      } ${className}`}
    >
      {(title || headerAction || badge) && (
        <div className="flex items-center justify-between gap-3 pb-3.5 border-b border-white/[0.08] mb-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {title && (
                <h3 className="font-extrabold text-sm sm:text-base text-white tracking-tight truncate">
                  {title}
                </h3>
              )}
              {badge && (
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-gold-500/15 text-gold-500 border border-gold-500/30">
                  {badge}
                </span>
              )}
            </div>
            {subtitle && (
              <p className="text-xs text-zinc-400 mt-0.5 truncate">{subtitle}</p>
            )}
          </div>
          {headerAction && <div className="shrink-0">{headerAction}</div>}
        </div>
      )}
      {children}
    </div>
  );
};

/**
 * Standard Metric / Quick Stat Card
 */
export const InternalMetricCard: React.FC<{
  label: string;
  value: string | number;
  change?: string;
  isPositive?: boolean;
  icon?: React.ComponentType<{ className?: string }>;
  subtext?: string;
}> = ({ label, value, change, isPositive, icon: Icon, subtext }) => {
  return (
    <div className="rounded-2xl border border-white/[0.08] bg-surface-3 p-4 sm:p-5 hover:border-gold-500/40 hover:shadow-[0_4px_20px_rgba(0,0,0,0.6)] transition-all">
      <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
        <span className="font-medium truncate">{label}</span>
        {Icon && (
          <div className="w-7 h-7 rounded-lg bg-gold-500/10 text-gold-500 flex items-center justify-center border border-gold-500/20 shrink-0">
            <Icon className="w-3.5 h-3.5" />
          </div>
        )}
      </div>

      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono font-black text-xl sm:text-2xl text-white tracking-tight">
          {value}
        </span>
        {change && (
          <span
            className={`font-mono text-xs font-bold px-1.5 py-0.5 rounded ${
              isPositive !== undefined
                ? isPositive
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                : 'bg-zinc-800 text-zinc-300'
            }`}
          >
            {change}
          </span>
        )}
      </div>

      {subtext && (
        <p className="text-xs text-zinc-500 mt-2 font-mono truncate">{subtext}</p>
      )}
    </div>
  );
};

/**
 * Empty / Placeholder Content Card with Gold Accents
 */
export const InternalEmptyCard: React.FC<{
  title?: string;
  description?: string;
  icon?: React.ComponentType<{ className?: string }>;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}> = ({
  title = 'Module Ready for Configuration',
  description = 'Institutional data and live algorithmic parameters will populate this container.',
  icon: Icon,
  action,
  className = '',
}) => {
  return (
    <div
      className={`rounded-2xl border border-dashed border-white/[0.12] bg-surface-2/70 p-8 sm:p-10 flex flex-col items-center justify-center text-center transition-all hover:border-gold-500/50 hover:bg-surface-2 ${className}`}
    >
      <div className="w-12 h-12 rounded-2xl bg-gold-500/10 text-gold-500 border border-gold-500/25 flex items-center justify-center mb-3 shadow-[0_0_20px_rgba(197,160,89,0.15)]">
        {Icon ? <Icon className="w-6 h-6" /> : <Layers className="w-6 h-6 text-gold-500" />}
      </div>
      <h4 className="font-bold text-sm sm:text-base text-white tracking-tight mb-1">
        {title}
      </h4>
      <p className="text-xs text-zinc-400 max-w-sm leading-relaxed mb-4">
        {description}
      </p>
      {action && (
        <button
          onClick={action.onClick}
          className="min-h-[40px] px-4 py-2 rounded-xl bg-gold-500 hover:bg-gold-500 text-ink-strong font-black text-xs transition active:scale-95 shadow-md shadow-gold-500/20 cursor-pointer"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};

/**
 * Universal Internal Page Template
 */
export const InternalPageTemplate: React.FC<InternalPageTemplateProps> = ({
  title,
  subtitle,
  breadcrumbs,
  onBack,
  badge,
  headerActions,
  statsSlot,
  children,
  asideSlot,
}) => {
  const defaultCrumbs: BreadcrumbItem[] = [
    { label: 'Private Desk', icon: Home },
    { label: title },
  ];

  const activeBreadcrumbs = breadcrumbs || defaultCrumbs;

  const getBadgeClass = (variant = 'gold') => {
    switch (variant) {
      case 'emerald':
        return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
      case 'rose':
        return 'bg-rose-500/15 text-rose-400 border-rose-500/30';
      case 'neutral':
        return 'bg-zinc-800 text-zinc-300 border-white/[0.08]';
      case 'gold':
      default:
        return 'bg-gold-500/15 text-gold-500 border-gold-500/30';
    }
  };

  // Default empty content cards grid when no children are provided
  const defaultEmptyContent = (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <InternalEmptyCard
          title="Data Stream Matrix"
          description="Awaiting primary data synchronization and WebSocket feed."
          icon={Database}
        />
        <InternalEmptyCard
          title="Risk & Execution Rules"
          description="Institutional 1.0% stop-loss threshold parameters."
          icon={Sliders}
        />
        <InternalEmptyCard
          title="Algorithmic Intelligence"
          description="SMC order block scanner and liquidity sweep detector."
          icon={Sparkles}
        />
      </div>

      <InternalCard
        title="Primary Analytical Workspace"
        subtitle="Institutional grade visualization panel"
        badge="Ready"
        goldHover={true}
      >
        <InternalEmptyCard
          title="Empty Analytical Canvas"
          description="Add custom charts, order book dissection, or audit logs to this section."
          icon={PlusCircle}
          action={{
            label: 'Initialize Module',
            onClick: () => {},
          }}
          className="py-12"
        />
      </InternalCard>
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6 w-full max-w-full"
    >
      {/* 1. Breadcrumbs Navigation */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-zinc-500">
        {onBack && (
          <button
            onClick={onBack}
            className="p-1 rounded-lg hover:bg-white/[0.06] text-zinc-400 hover:text-gold-500 transition cursor-pointer active:scale-95 mr-1"
            title="Go Back"
            aria-label="Go Back"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
        )}

        {activeBreadcrumbs.map((crumb, idx) => {
          const isLast = idx === activeBreadcrumbs.length - 1;
          const CrumbIcon = crumb.icon;

          return (
            <React.Fragment key={idx}>
              {idx > 0 && <ChevronRight className="w-3.5 h-3.5 text-zinc-600 shrink-0" />}
              
              {isLast ? (
                <span className="font-bold text-gold-500 flex items-center gap-1.5 truncate">
                  {CrumbIcon && <CrumbIcon className="w-3.5 h-3.5" />}
                  <span>{crumb.label}</span>
                </span>
              ) : (
                <button
                  onClick={crumb.onClick}
                  className="hover:text-zinc-200 transition flex items-center gap-1.5 cursor-pointer truncate"
                >
                  {CrumbIcon && <CrumbIcon className="w-3.5 h-3.5" />}
                  <span>{crumb.label}</span>
                </button>
              )}
            </React.Fragment>
          );
        })}
      </nav>

      {/* 2. Dynamic Page Title Header & Action Controls */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.08]">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              {title}
            </h1>
            {badge && (
              <span
                className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full border ${getBadgeClass(
                  badge.variant
                )}`}
              >
                {badge.label}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed max-w-2xl">
              {subtitle}
            </p>
          )}
        </div>

        {headerActions && (
          <div className="flex items-center gap-2.5 sm:gap-3 shrink-0">
            {headerActions}
          </div>
        )}
      </header>

      {/* 3. Optional Quick Stats / Metrics Row */}
      {statsSlot && (
        <section aria-label="Page Key Metrics" className="w-full">
          {statsSlot}
        </section>
      )}

      {/* 4. Main Content Responsive Grid Layout */}
      {asideSlot ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 w-full">
          <div className="lg:col-span-8 space-y-6">
            {children || defaultEmptyContent}
          </div>
          <div className="lg:col-span-4 space-y-6">{asideSlot}</div>
        </div>
      ) : (
        <div className="space-y-6 w-full">{children || defaultEmptyContent}</div>
      )}
    </motion.div>
  );
};
