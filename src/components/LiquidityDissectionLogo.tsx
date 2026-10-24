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
  /** Color theme support */
  theme?: 'light' | 'dark';
  /** Show or hide the subtle wireframe background around emblem */
  showWireframe?: boolean;
}

/**
 * High-Precision 3D Metallic Gold "LD" Hexagonal Shield Emblem
 * Recreated accurately from the official Liquidity Dissection - Private Desk brand asset.
 */
export const LDEmblem: React.FC<{
  className?: string;
  showWireframe?: boolean;
}> = ({ className = 'w-10 h-10', showWireframe = true }) => {
  const uniqueId = React.useId().replace(/:/g, '');

  return (
    <svg
      viewBox="0 0 200 200"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 select-none ${className}`}
      aria-label="Liquidity Dissection LD Logo"
    >
      <defs>
        {/* Specular Highlight Gradient */}
        <linearGradient id={`goldSpecular_${uniqueId}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#FFFDF7" />
          <stop offset="25%" stopColor="#FDEBC4" />
          <stop offset="60%" stopColor="#DFB96E" />
          <stop offset="100%" stopColor="#A88133" />
        </linearGradient>

        {/* Polished Metallic Gold Surface */}
        <linearGradient id={`goldPolished_${uniqueId}`} x1="20%" y1="0%" x2="80%" y2="100%">
          <stop offset="0%" stopColor="#F9E5B6" />
          <stop offset="35%" stopColor="#E2C175" />
          <stop offset="70%" stopColor="#C5A059" />
          <stop offset="100%" stopColor="#8C6621" />
        </linearGradient>

        {/* Deep Chiseled Bevel Shadow */}
        <linearGradient id={`goldShadow_${uniqueId}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#75541A" />
          <stop offset="50%" stopColor="#4A340E" />
          <stop offset="100%" stopColor="#241906" />
        </linearGradient>

        {/* Dark Obsidian Facet (Inner Cavities) */}
        <linearGradient id={`obsidianFacet_${uniqueId}`} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#1C1812" />
          <stop offset="50%" stopColor="#12100C" />
          <stop offset="100%" stopColor="#080705" />
        </linearGradient>

        {/* Subtle Ambient Gold Glow */}
        <radialGradient id={`ambientGlow_${uniqueId}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#C5A059" stopOpacity="0.22" />
          <stop offset="70%" stopColor="#C5A059" stopOpacity="0.04" />
          <stop offset="100%" stopColor="#C5A059" stopOpacity="0" />
        </radialGradient>

        {/* Drop Shadow Filter for 3D Pop */}
        <filter id={`emblemShadow_${uniqueId}`} x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="8" stdDeviation="10" floodColor="#000000" floodOpacity="0.75" />
          <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#C5A059" floodOpacity="0.25" />
        </filter>
      </defs>

      {/* 1. Ambient Glow Backdrop */}
      <circle cx="100" cy="100" r="92" fill={`url(#ambientGlow_${uniqueId})`} />

      {/* 2. Micro Sacred Geometry Hexagonal Wireframe (matching brand image) */}
      {showWireframe && (
        <g opacity="0.3" stroke="#C5A059" strokeWidth="0.6">
          {/* Outer concentric hexagon */}
          <polygon points="100,10 178,55 178,145 100,190 22,145 22,55" fill="none" />
          {/* Radial vertex rays */}
          <line x1="100" y1="10" x2="100" y2="190" strokeDasharray="3 3" />
          <line x1="22" y1="55" x2="178" y2="145" strokeDasharray="3 3" />
          <line x1="22" y1="145" x2="178" y2="55" strokeDasharray="3 3" />
          {/* Inner isometric star wireframe */}
          <polygon points="100,24 166,62 166,138 100,176 34,138 34,62" fill="none" opacity="0.5" />
        </g>
      )}

      {/* 3. Main 3D Interlocking "LD" Hexagonal Shield */}
      <g filter={`url(#emblemShadow_${uniqueId})`}>
        {/* --- Top Vertex Diamond Facet --- */}
        <polygon
          points="100,26 114,40 100,48 86,40"
          fill={`url(#goldSpecular_${uniqueId})`}
        />
        <polygon
          points="100,26 86,40 100,48"
          fill={`url(#goldPolished_${uniqueId})`}
        />

        {/* --- Outer Hexagon Left Rim (Part of L structure) --- */}
        {/* Top-Left Chamfer Edge */}
        <polygon
          points="100,26 86,40 54,64 62,54"
          fill={`url(#goldPolished_${uniqueId})`}
        />
        {/* Left Vertical Chamfer */}
        <polygon
          points="54,64 62,54 62,118 54,110"
          fill={`url(#goldShadow_${uniqueId})`}
        />

        {/* --- The "L" Monogram (Thick 3D Faceted Block on Left) --- */}
        {/* L Main Vertical Pillar - Front Face */}
        <polygon
          points="70,54 84,54 84,130 70,130"
          fill={`url(#goldPolished_${uniqueId})`}
        />
        {/* L Left Bevel (Shadow) */}
        <polygon
          points="58,62 70,54 70,130 58,124"
          fill={`url(#goldShadow_${uniqueId})`}
        />
        {/* L Right Bevel (Inner Highlight) */}
        <polygon
          points="84,54 88,58 88,126 84,130"
          fill={`url(#goldSpecular_${uniqueId})`}
        />

        {/* L Base Foot Shelf - Front Face */}
        <polygon
          points="70,118 116,118 108,130 70,130"
          fill={`url(#goldSpecular_${uniqueId})`}
        />
        {/* L Base Bottom Bevel */}
        <polygon
          points="70,130 108,130 100,146 58,124"
          fill={`url(#goldShadow_${uniqueId})`}
        />

        {/* --- Central Obsidian Depth Shadow (Recessed Area Behind LD) --- */}
        <path
          d="M84 62 L106 62 L106 118 L84 118 Z"
          fill={`url(#obsidianFacet_${uniqueId})`}
        />

        {/* --- The "D" Monogram (Bold 3D Interlocking Arch on Right) --- */}
        {/* D Top Horizontal Spine */}
        <polygon
          points="90,44 136,44 146,54 100,54"
          fill={`url(#goldSpecular_${uniqueId})`}
        />
        <polygon
          points="100,54 146,54 138,62 106,62"
          fill={`url(#goldPolished_${uniqueId})`}
        />

        {/* D Outer Curved / Faceted Arch */}
        {/* Upper-Right Facet */}
        <polygon
          points="136,44 154,64 142,74 126,58"
          fill={`url(#goldSpecular_${uniqueId})`}
        />
        {/* Right Vertical Facet */}
        <polygon
          points="154,64 154,104 140,100 142,74"
          fill={`url(#goldPolished_${uniqueId})`}
        />
        {/* Lower-Right Facet */}
        <polygon
          points="154,104 134,132 118,120 140,100"
          fill={`url(#goldShadow_${uniqueId})`}
        />
        {/* Lower Inward Flourish (Interlocking with L) */}
        <polygon
          points="134,132 108,144 114,130 118,120"
          fill={`url(#goldPolished_${uniqueId})`}
        />

        {/* D Inner Curved Aperture (The Window in D) */}
        <path
          d="M106 62 L128 62 C138 62 144 72 144 84 C144 96 138 106 128 106 L106 106 Z"
          fill={`url(#obsidianFacet_${uniqueId})`}
        />
        {/* D Inner Aperture Chiseled Highlight */}
        <path
          d="M108 66 L126 66 C134 66 139 74 139 84 C139 94 134 102 126 102 L108 102 Z"
          fill="none"
          stroke={`url(#goldSpecular_${uniqueId})`}
          strokeWidth="2.5"
          opacity="0.85"
        />

        {/* D Exterior Decorative Sweeping Wing / Ribbon Tip */}
        <polygon
          points="154,84 172,106 160,122 146,112"
          fill={`url(#goldSpecular_${uniqueId})`}
        />
        <polygon
          points="160,122 146,112 134,132 142,136"
          fill={`url(#goldShadow_${uniqueId})`}
        />

        {/* --- Bottom Shield Vertex / Anchor --- */}
        <polygon
          points="100,146 108,130 118,142"
          fill={`url(#goldPolished_${uniqueId})`}
        />
        <polygon
          points="100,146 88,138 100,154"
          fill={`url(#goldShadow_${uniqueId})`}
        />
      </g>
    </svg>
  );
};

/**
 * Universal Liquidity Dissection - Private Desk Brand Logo Component
 */
export const LiquidityDissectionLogo: React.FC<LogoProps> = ({
  size = 'md',
  withText = true,
  layout = 'horizontal',
  className = '',
  showWireframe = true,
}) => {
  const iconSizes = {
    xs: 'w-6 h-6',
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-14 h-14',
    xl: 'w-20 h-20',
    '2xl': 'w-28 h-28',
  };

  const textSizes = {
    xs: { title: 'text-xs tracking-[0.14em]', sub: 'text-xs tracking-[0.24em]' },
    sm: { title: 'text-xs tracking-[0.16em]', sub: 'text-xs tracking-[0.26em]' },
    md: { title: 'text-sm tracking-[0.18em]', sub: 'text-xs tracking-[0.28em]' },
    lg: { title: 'text-lg tracking-[0.20em]', sub: 'text-xs tracking-[0.30em]' },
    xl: { title: 'text-xl tracking-[0.22em]', sub: 'text-xs tracking-[0.32em]' },
    '2xl': { title: 'text-2xl tracking-[0.24em]', sub: 'text-sm tracking-[0.34em]' },
  };

  if (layout === 'vertical') {
    return (
      <div className={`flex flex-col items-center text-center select-none ${className}`}>
        <LDEmblem className={iconSizes[size]} showWireframe={showWireframe} />
        {withText && (
          <div className="mt-3 flex flex-col items-center">
            <h2
              className={`font-black uppercase font-sans text-white leading-tight ${textSizes[size].title}`}
            >
              LIQUIDITY{' '}
              <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-500 to-gold-700 bg-clip-text text-transparent">
                DISSECTION
              </span>
            </h2>
            <span
              className={`font-bold uppercase font-mono text-gold-500 mt-1 ${textSizes[size].sub}`}
            >
              - PRIVATE DESK -
            </span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      <LDEmblem className={iconSizes[size]} showWireframe={showWireframe} />
      {withText && (
        <div className="flex flex-col text-start min-w-0">
          <div className="flex items-center gap-1.5 leading-none">
            <span
              className={`font-black uppercase font-sans text-white truncate ${textSizes[size].title}`}
            >
              LIQUIDITY{' '}
              <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-500 to-gold-700 bg-clip-text text-transparent">
                DISSECTION
              </span>
            </span>
          </div>
            <span
              className={`font-bold uppercase font-mono text-gold-500 mt-1 block truncate ${textSizes[size].sub}`}
            >
              - PRIVATE GOLD DESK -
            </span>
        </div>
      )}
    </div>
  );
};
