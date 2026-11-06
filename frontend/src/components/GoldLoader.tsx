import React from 'react';

/** The app's logo in a spinning gold arc (styles: .ld-logo-loader in index.html, next to the intro's). */
export const LogoLoader: React.FC<{ small?: boolean; className?: string }> = ({ small = false, className = '' }) => (
  <div className={`ld-logo-loader ${small ? 'is-small' : ''} ${className}`} aria-hidden="true">
    <div className="ld-circle" />
    <img src="/brand/emblem-clear-192.webp" alt="" />
  </div>
);

/** Full screen, while the app loads after the intro (e.g. the server waking up): the logo and what is loading. */
export const GoldLoader: React.FC<{ label?: string }> = ({ label }) => (
  <div className="fixed inset-0 z-[9998] flex flex-col items-center justify-center gap-6 bg-[radial-gradient(circle_at_50%_46%,#0E121A_0%,#090B10_55%,#07090D_100%)]"
    role="status" aria-live="polite">
    <LogoLoader />
    {label && <p className="text-xs text-slate-400 text-center max-w-xs px-4">{label}</p>}
  </div>
);
