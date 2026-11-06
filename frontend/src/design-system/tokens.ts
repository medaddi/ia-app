/**
 * Vanguard Neo-Precision Design System Tokens
 * Strict, bespoke design system engineered for high-performance trading & web applications.
 * Adheres to 4px spatial rhythm, zero-pill discipline, and high-contrast accessibility.
 */

export const DESIGN_TOKENS = {
  // ── 1. Color System ──
  colors: {
    // Light Mode Palette
    light: {
      canvas: '#F8FAFC',           // Studio Off-White canvas
      surfaceBase: '#FFFFFF',      // Optical pure white card surface
      surfaceSubtle: '#F1F5F9',    // Recessed background (inputs, panels)
      surfaceRaised: '#FFFFFF',    // Elevated modals & dropdowns
      
      borderSubtle: '#E2E8F0',     // 1px hairline container divider
      borderDefault: '#CBD5E1',    // Interactive element borders
      borderHover: '#94A3B8',      // Hover border state
      borderFocus: '#2563EB',      // Accessible dual-ring focus
      
      textPrimary: '#0F172A',      // Slate 900 — Maximum contrast
      textSecondary: '#475569',    // Slate 600 — Informational body
      textMuted: '#94A3B8',        // Slate 400 — Quiet metadata & captions
      textInverse: '#FFFFFF',      // White on dark backgrounds
      
      primary: '#0F172A',          // Obsidian Solid CTA
      primaryHover: '#1E293B',
      primaryActive: '#334155',
      primaryFg: '#FFFFFF',
      
      secondary: '#2563EB',        // Electric Cobalt Accent
      secondaryHover: '#1D4ED8',
      secondarySubtle: '#EFF6FF',
      secondaryFg: '#FFFFFF',
      
      success: '#059669',          // Pine Emerald 600
      successSubtle: '#ECFDF5',
      successBorder: '#A7F3D0',
      successFg: '#065F46',
      
      danger: '#DC2626',           // Crimson Berry 600
      dangerSubtle: '#FEF2F2',
      dangerBorder: '#FECACA',
      dangerFg: '#991B1B',
      
      warning: '#D97706',          // Warm Amber 600
      warningSubtle: '#FFFBEB',
      warningBorder: '#FDE68A',
      warningFg: '#92400E',
    },
    
    // Dark Mode Palette
    dark: {
      canvas: '#090D16',           // Pure Obsidian Void
      surfaceBase: '#0F172A',      // Slate 900
      surfaceSubtle: '#1E293B',    // Slate 800 recessed
      surfaceRaised: '#131D31',    // Elevated card surface
      
      borderSubtle: 'rgba(255, 255, 255, 0.08)',
      borderDefault: 'rgba(255, 255, 255, 0.14)',
      borderHover: 'rgba(255, 255, 255, 0.28)',
      borderFocus: '#3B82F6',
      
      textPrimary: '#F8FAFC',      // Slate 50 — Crisp contrast
      textSecondary: '#94A3B8',    // Slate 400
      textMuted: '#64748B',        // Slate 500
      textInverse: '#0F172A',
      
      primary: '#F8FAFC',          // High-contrast light CTA
      primaryHover: '#E2E8F0',
      primaryActive: '#CBD5E1',
      primaryFg: '#0F172A',
      
      secondary: '#3B82F6',        // Electric Azure Accent
      secondaryHover: '#60A5FA',
      secondarySubtle: 'rgba(59, 130, 246, 0.12)',
      secondaryFg: '#FFFFFF',
      
      success: '#10B981',
      successSubtle: 'rgba(16, 185, 129, 0.12)',
      successBorder: 'rgba(16, 185, 129, 0.25)',
      successFg: '#34D399',
      
      danger: '#EF4444',
      dangerSubtle: 'rgba(239, 68, 68, 0.12)',
      dangerBorder: 'rgba(239, 68, 68, 0.25)',
      dangerFg: '#F87171',
      
      warning: '#F59E0B',
      warningSubtle: 'rgba(245, 158, 11, 0.12)',
      warningBorder: 'rgba(245, 158, 11, 0.25)',
      warningFg: '#FBBF24',
    }
  },

  // ── 2. Typography Scale ──
  typography: {
    fontFamilies: {
      sans: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      mono: "'JetBrains Mono', 'Fira Code', monospace",
    },
    scale: {
      display: {
        fontSize: '36px',
        lineHeight: '1.15',
        letterSpacing: '-0.035em',
        fontWeight: '800',
        tailwind: 'text-4xl font-extrabold tracking-tight leading-tight',
      },
      h1: {
        fontSize: '28px',
        lineHeight: '1.20',
        letterSpacing: '-0.025em',
        fontWeight: '700',
        tailwind: 'text-2xl sm:text-3xl font-bold tracking-tight leading-snug',
      },
      h2: {
        fontSize: '20px',
        lineHeight: '1.30',
        letterSpacing: '-0.020em',
        fontWeight: '600',
        tailwind: 'text-lg sm:text-xl font-semibold tracking-tight leading-snug',
      },
      h3: {
        fontSize: '16px',
        lineHeight: '1.40',
        letterSpacing: '-0.010em',
        fontWeight: '600',
        tailwind: 'text-base font-semibold tracking-tight leading-normal',
      },
      bodyLarge: {
        fontSize: '15px',
        lineHeight: '1.50',
        letterSpacing: '0',
        fontWeight: '400',
        tailwind: 'text-[15px] font-normal leading-relaxed',
      },
      bodyDefault: {
        fontSize: '14px',
        lineHeight: '1.50',
        letterSpacing: '0',
        fontWeight: '400',
        tailwind: 'text-sm font-normal leading-relaxed',
      },
      bodyMedium: {
        fontSize: '14px',
        lineHeight: '1.50',
        letterSpacing: '0',
        fontWeight: '500',
        tailwind: 'text-sm font-medium leading-relaxed',
      },
      caption: {
        fontSize: '12px',
        lineHeight: '1.40',
        letterSpacing: '+0.015em',
        fontWeight: '500',
        tailwind: 'text-xs font-medium leading-normal',
      },
      micro: {
        fontSize: '10px',
        lineHeight: '1.30',
        letterSpacing: '+0.030em',
        fontWeight: '600',
        tailwind: 'text-xs font-semibold uppercase tracking-wider',
      },
      numbers: {
        fontSize: 'inherit',
        lineHeight: '1.0',
        letterSpacing: '0',
        fontWeight: '700',
        tailwind: 'font-mono font-bold tracking-tight tabular-nums',
      }
    }
  },

  // ── 3. Spacing & Spatial Math (4px Baseline Grid) ──
  spacing: {
    '3xs': '2px',
    '2xs': '4px',
    'xs':  '8px',
    'sm':  '12px',
    'md':  '16px',  // Standard component padding
    'lg':  '24px',  // Card internal padding & section gaps
    'xl':  '32px',  // Grid spacing & major section padding
    '2xl': '48px',
    '3xl': '64px',
  },

  // ── 4. Geometric Radii (r_inner = r_outer - padding) ──
  radii: {
    xs: '4px',    // Micro tags, inner elements
    sm: '6px',    // Small action buttons, inputs
    md: '10px',   // Standard inputs, buttons
    lg: '14px',   // Main cards, panels
    xl: '20px',   // Modals, floating drawers
    full: '9999px',
  },

  // ── 5. Multi-Layer Shadows ──
  shadows: {
    subtle: '0 1px 2px 0 rgba(15, 23, 42, 0.05)',
    card: '0 2px 6px -1px rgba(15, 23, 42, 0.05), 0 6px 16px -2px rgba(15, 23, 42, 0.04)',
    float: '0 16px 36px -8px rgba(15, 23, 42, 0.12), 0 4px 12px -2px rgba(15, 23, 42, 0.04)',
  }
} as const;

export type DesignTokens = typeof DESIGN_TOKENS;
