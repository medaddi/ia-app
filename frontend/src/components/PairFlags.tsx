import React from 'react';

/**
 * Small round flags for the currencies the app trades, drawn inline (nothing to download), and a pair icon made of two
 * overlapping circles: the base currency in front, the quote behind it. Gold (XAU) is a gold coin.
 */
type Ccy = 'USD' | 'EUR' | 'GBP' | 'CAD' | 'NZD' | 'CHF' | 'AUD' | 'XAU';

const UnionJack = ({ w = 60, h = 30 }: { w?: number; h?: number }) => (
  <g>
    <rect width={w} height={h} fill="#012169" />
    <path d={`M0 0L${w} ${h}M${w} 0L0 ${h}`} stroke="#fff" strokeWidth={h / 5} />
    <path d={`M0 0L${w} ${h}M${w} 0L0 ${h}`} stroke="#C8102E" strokeWidth={h / 15} />
    <path d={`M${w / 2} 0V${h}M0 ${h / 2}H${w}`} stroke="#fff" strokeWidth={h / 3} />
    <path d={`M${w / 2} 0V${h}M0 ${h / 2}H${w}`} stroke="#C8102E" strokeWidth={h / 5} />
  </g>
);

const star = (cx: number, cy: number, r: number) => {
  const p: string[] = [];
  for (let i = 0; i < 10; i++) {
    const a = (Math.PI / 5) * i - Math.PI / 2;
    const rr = i % 2 ? r * 0.45 : r;
    p.push(`${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`);
  }
  return p.join(' ');
};

/** The flag drawn in a 64 × 64 box (shown inside a circle). */
function FlagArt({ ccy }: { ccy: Ccy }) {
  switch (ccy) {
    case 'USD': {
      const h = 64 / 13;  // 13 stripes, red first
      return (
        <g>
          <rect width="64" height="64" fill="#fff" />
          {Array.from({ length: 7 }).map((_, i) => <rect key={i} y={i * 2 * h} width="64" height={h} fill="#B22234" />)}
          <rect width="30" height={7 * h} fill="#3C3B6E" />
          {[5, 12, 19, 26].map(y => [5, 12, 19, 26].map(x => <circle key={`${x}-${y}`} cx={x + ((y / 7) % 2 ? 2 : 0)} cy={y} r="1.5" fill="#fff" />))}
        </g>
      );
    }
    case 'EUR':
      return (
        <g>
          <rect width="64" height="64" fill="#003399" />
          {Array.from({ length: 12 }).map((_, i) => {
            const a = (Math.PI * 2 * i) / 12;
            return <polygon key={i} points={star(32 + 18 * Math.cos(a), 32 + 18 * Math.sin(a), 3.4)} fill="#FFCC00" />;
          })}
        </g>
      );
    case 'GBP':
      return <g transform="translate(-16 0) scale(1.6 2.1333)"><UnionJack /></g>;
    case 'CAD':
      return (
        <g>
          <rect width="64" height="64" fill="#fff" />
          <rect width="16" height="64" fill="#D80621" />
          <rect x="48" width="16" height="64" fill="#D80621" />
          <path d="M32 14l3 6 4-2-1 9 5-4 1 3 5-1-2 6 2 1-9 7 1 4-7-1 0 8h-4l0-8-7 1 1-4-9-7 2-1-2-6 5 1 1-3 5 4-1-9 4 2z" fill="#D80621" />
        </g>
      );
    case 'NZD':
      return (
        <g>
          <rect width="64" height="64" fill="#012169" />
          <g transform="scale(0.53 0.95)"><UnionJack w={60} h={34} /></g>
          {[[46, 18, 3.6], [53, 32, 3.2], [40, 33, 3.2], [46, 48, 4]].map(([x, y, r], i) => (
            <polygon key={i} points={star(x, y, r)} fill="#C8102E" stroke="#fff" strokeWidth="1" />
          ))}
        </g>
      );
    case 'AUD':
      return (
        <g>
          <rect width="64" height="64" fill="#012169" />
          <g transform="scale(0.53 0.95)"><UnionJack w={60} h={34} /></g>
          <polygon points={star(16, 48, 6)} fill="#fff" />
          {[[47, 16, 3.2], [55, 30, 3.2], [40, 30, 3.2], [47, 50, 3.6]].map(([x, y, r], i) => <polygon key={i} points={star(x, y, r)} fill="#fff" />)}
        </g>
      );
    case 'CHF':
      return (
        <g>
          <rect width="64" height="64" fill="#D52B1E" />
          <rect x="27" y="13" width="10" height="38" fill="#fff" />
          <rect x="13" y="27" width="38" height="10" fill="#fff" />
        </g>
      );
    case 'XAU':  // a gold coin (solid colours: a gradient id would clash between the many copies on a page)
      return (
        <g>
          <rect width="64" height="64" fill="#C9A04A" />
          <circle cx="24" cy="20" r="30" fill="#E3C374" />
          <circle cx="20" cy="16" r="14" fill="#F7EBC8" opacity="0.7" />
          <circle cx="32" cy="32" r="22" fill="none" stroke="#7F632A" strokeOpacity="0.6" strokeWidth="2.5" />
          <text x="32" y="40" textAnchor="middle" fontSize="22" fontWeight="800" fontFamily="Inter, sans-serif" fill="#5A4519">Au</text>
        </g>
      );
  }
}

export function CurrencyFlag({ ccy, size = 20, className = '' }: { ccy: string; size?: number; className?: string }) {
  const id = `f-${ccy}-${size}`;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={`shrink-0 rounded-full ring-1 ring-black/40 shadow-[0_1px_3px_rgba(0,0,0,0.5)] ${className}`} aria-hidden="true">
      <defs><clipPath id={id}><circle cx="32" cy="32" r="32" /></clipPath></defs>
      <g clipPath={`url(#${id})`}><FlagArt ccy={(ccy as Ccy)} /></g>
    </svg>
  );
}

/** Two overlapping round flags for a pair ("EUR/USD": the euro in front, the dollar behind). */
export function PairFlags({ symbol, size = 18, className = '' }: { symbol: string; size?: number; className?: string }) {
  const [base, quote] = symbol.includes('/') ? symbol.split('/') : [symbol.slice(0, 3), symbol.slice(3)];
  return (
    <span className={`relative inline-flex shrink-0 ${className}`} style={{ width: size * 1.55, height: size }} aria-hidden="true">
      <CurrencyFlag ccy={quote} size={size} className="absolute end-0 top-0 opacity-90" />
      <CurrencyFlag ccy={base} size={size} className="absolute start-0 top-0" />
    </span>
  );
}
