import React from 'react';

// ==========================================
// 1. BUTTON COMPONENT
// ==========================================
export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  children,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = 
    "inline-flex items-center justify-center font-medium transition-all duration-150 ease-out select-none cursor-pointer " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 " +
    "active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none";

  const sizeStyles: Record<ButtonSize, string> = {
    sm: "text-xs px-3 py-1.5 rounded-md gap-1.5 h-8",
    md: "text-sm px-4 py-2 rounded-lg gap-2 h-10",
    lg: "text-base px-6 py-2.5 rounded-xl gap-2.5 h-12",
  };

  const variantStyles: Record<ButtonVariant, string> = {
    primary: 
      "bg-slate-900 hover:bg-slate-800 text-white shadow-sm " +
      "dark:bg-slate-100 dark:hover:bg-white dark:text-slate-900",
    
    secondary:
      "bg-blue-600 hover:bg-blue-700 text-white shadow-sm " +
      "dark:bg-blue-600 dark:hover:bg-blue-500 dark:text-white",

    outline:
      "bg-white hover:bg-slate-50 text-slate-800 border border-slate-200/90 shadow-xs " +
      "dark:bg-slate-900/60 dark:hover:bg-slate-800/80 dark:text-slate-200 dark:border-white/10",

    danger:
      "bg-rose-600 hover:bg-rose-700 text-white shadow-sm " +
      "dark:bg-rose-600 dark:hover:bg-rose-500",

    ghost:
      "bg-transparent hover:bg-slate-100 text-slate-600 hover:text-slate-900 " +
      "dark:text-slate-400 dark:hover:bg-slate-800/80 dark:hover:text-slate-100",
  };

  return (
    <button
      disabled={disabled || isLoading}
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {isLoading ? (
        <svg className="animate-spin -ml-0.5 mr-2 h-4 w-4 text-current" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      ) : leftIcon ? (
        <span className="shrink-0">{leftIcon}</span>
      ) : null}
      <span>{children}</span>
      {!isLoading && rightIcon ? <span className="shrink-0">{rightIcon}</span> : null}
    </button>
  );
};

// ==========================================
// 2. INPUT FIELD COMPONENT
// ==========================================
export interface InputFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  leftAddon?: React.ReactNode;
  rightAddon?: React.ReactNode;
}

export const InputField: React.FC<InputFieldProps> = ({
  label,
  error,
  hint,
  leftAddon,
  rightAddon,
  id,
  className = '',
  disabled,
  ...props
}) => {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="w-full space-y-1.5 text-left">
      {label && (
        <label 
          htmlFor={inputId} 
          className="block text-xs font-semibold text-slate-700 dark:text-slate-300 tracking-tight"
        >
          {label}
        </label>
      )}

      <div className="relative flex items-center">
        {leftAddon && (
          <div className="absolute left-3 flex items-center pointer-events-none text-slate-400">
            {leftAddon}
          </div>
        )}

        <input
          id={inputId}
          disabled={disabled}
          className={`
            w-full h-10 text-sm rounded-lg transition-all duration-150 ease-out
            bg-white dark:bg-slate-900/90
            text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500
            border ${error ? 'border-rose-500 focus:border-rose-500 focus:ring-rose-500/20' : 'border-slate-200 dark:border-white/10 hover:border-slate-300 dark:hover:border-white/20 focus:border-blue-500 focus:ring-blue-500/15'}
            focus:outline-none focus:ring-4
            disabled:bg-slate-50 dark:disabled:bg-slate-950 disabled:text-slate-400 disabled:cursor-not-allowed
            ${leftAddon ? 'pl-9' : 'pl-3.5'}
            ${rightAddon ? 'pr-9' : 'pr-3.5'}
            ${className}
          `}
          {...props}
        />

        {rightAddon && (
          <div className="absolute right-3 flex items-center text-slate-400">
            {rightAddon}
          </div>
        )}
      </div>

      {error ? (
        <p className="text-xs text-rose-600 dark:text-rose-400 flex items-center gap-1 mt-1 font-medium">
          <span>•</span> {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          {hint}
        </p>
      ) : null}
    </div>
  );
};

// ==========================================
// 3. CARD COMPONENT
// ==========================================
export interface CardProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  interactive?: boolean;
  className?: string;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({
  children,
  title,
  subtitle,
  action,
  interactive = false,
  className = '',
  onClick,
}) => {
  return (
    <div
      onClick={interactive ? onClick : undefined}
      className={`
        p-5 sm:p-6 rounded-xl border transition-all duration-200
        bg-white dark:bg-slate-900/80 backdrop-blur-sm
        border-slate-200/80 dark:border-white/[0.08]
        shadow-sm dark:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.5)]
        ${interactive ? 'cursor-pointer hover:border-slate-300 dark:hover:border-white/20 hover:shadow-md active:scale-[0.995]' : ''}
        ${className}
      `}
    >
      {(title || action) && (
        <div className="flex items-start justify-between gap-4 pb-4 mb-4 border-b border-slate-100 dark:border-white/[0.06]">
          <div>
            {title && (
              <h3 className="text-base font-semibold text-slate-900 dark:text-white tracking-tight">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}

      {children}
    </div>
  );
};

// ==========================================
// 4. METRIC CARD COMPONENT
// ==========================================
export interface MetricCardProps {
  label: string;
  value: string | number;
  change?: {
    value: string;
    isPositive: boolean;
  };
  period?: string;
  icon?: React.ReactNode;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  change,
  period = 'vs last period',
  icon,
}) => {
  return (
    <div className="p-5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-slate-900/80 shadow-sm">
      <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-2">
        <span className="font-medium">{label}</span>
        {icon && <div className="text-slate-400 dark:text-slate-500">{icon}</div>}
      </div>

      <div className="flex items-baseline justify-between gap-2">
        <span className="text-2xl sm:text-3xl font-bold font-mono tracking-tight text-slate-900 dark:text-white">
          {value}
        </span>
      </div>

      {change && (
        <div className="flex items-center gap-1.5 mt-2 text-xs">
          <span className={`font-semibold font-mono ${change.isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
            {change.isPositive ? '+' : ''}{change.value}
          </span>
          <span className="text-slate-400 dark:text-slate-500 text-xs">{period}</span>
        </div>
      )}
    </div>
  );
};

// ==========================================
// 5. STATUS TAG (ZERO-PILL DISCIPLINE)
// ==========================================
export interface StatusTagProps {
  status: 'success' | 'danger' | 'warning' | 'neutral';
  label: string;
}

export const StatusTag: React.FC<StatusTagProps> = ({ status, label }) => {
  const styles: Record<StatusTagProps['status'], string> = {
    success: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    danger: 'text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/20',
    warning: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20',
    neutral: 'text-slate-600 dark:text-slate-400 bg-slate-500/10 border-slate-500/20',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${styles[status]}`}>
      {label}
    </span>
  );
};
