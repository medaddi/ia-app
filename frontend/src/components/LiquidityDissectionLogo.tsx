import React from 'react';

interface LogoProps {
  /** Size variant */
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  /** Whether to render brand title and subtitle text */
  withText?: boolean;
  /** Layout orientation when text is included */
  layout?: 'horizontal' | 'vertical';
  /** Optional custom class name */
  className?: string;
  /** Kept for older call sites */
  theme?: 'light' | 'dark';
  showWireframe?: boolean;
}

/** The official LD emblem (public/brand). Small sizes load the 192 px file, large ones the 512 px file. */
export const LDEmblem: React.FC<{ className?: string; showWireframe?: boolean; large?: boolean }> = ({ className = 'w-10 h-10', large = false }) => (
  <img
    src={large ? '/brand/emblem-512.webp' : '/brand/emblem-192.webp'}
    alt="LiquidityDissection"
    width={large ? 512 : 192}
    height={large ? 512 : 192}
    decoding="async"
    draggable={false}
    className={`shrink-0 select-none rounded-[22%] object-cover ring-1 ring-gold-500/20 ${className}`}
  />
);

/** Emblem + brand name, used in the navigation, drawers and login. */
export const LiquidityDissectionLogo: React.FC<LogoProps> = ({ size = 'md', withText = true, layout = 'horizontal', className = '' }) => {
  const iconSizes = { xs: 'w-6 h-6', sm: 'w-8 h-8', md: 'w-10 h-10', lg: 'w-14 h-14', xl: 'w-20 h-20', '2xl': 'w-28 h-28' };
  const textSizes = {
    xs: { title: 'text-xs tracking-[0.14em]', sub: 'text-[10px] tracking-[0.24em]' },
    sm: { title: 'text-xs tracking-[0.16em]', sub: 'text-[10px] tracking-[0.26em]' },
    md: { title: 'text-sm tracking-[0.18em]', sub: 'text-xs tracking-[0.28em]' },
    lg: { title: 'text-lg tracking-[0.20em]', sub: 'text-xs tracking-[0.30em]' },
    xl: { title: 'text-xl tracking-[0.22em]', sub: 'text-xs tracking-[0.32em]' },
    '2xl': { title: 'text-2xl tracking-[0.24em]', sub: 'text-sm tracking-[0.34em]' },
  };
  const large = size === 'xl' || size === '2xl';
  const title = (
    <>
      LIQUIDITY{' '}
      <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-500 to-gold-700 bg-clip-text text-transparent">DISSECTION</span>
    </>
  );
  if (layout === 'vertical') {
    return (
      <div className={`flex flex-col items-center text-center select-none ${className}`}>
        <LDEmblem className={iconSizes[size]} large={large} />
        {withText && (
          <div className="mt-3 flex flex-col items-center">
            <h2 className={`font-black uppercase font-sans text-white leading-tight ${textSizes[size].title}`}>{title}</h2>
            <span className={`font-bold uppercase font-mono text-gold-500 mt-1 ${textSizes[size].sub}`}>- PRIVATE DESK -</span>
          </div>
        )}
      </div>
    );
  }
  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      <LDEmblem className={iconSizes[size]} large={large} />
      {withText && (
        <div className="flex flex-col text-start min-w-0">
          <span className={`font-black uppercase font-sans text-white truncate leading-none ${textSizes[size].title}`}>{title}</span>
          <span className={`font-bold uppercase font-mono text-gold-500 mt-1 block truncate ${textSizes[size].sub}`}>- PRIVATE DESK -</span>
        </div>
      )}
    </div>
  );
};
