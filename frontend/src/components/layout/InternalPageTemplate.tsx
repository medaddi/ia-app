import React from 'react';

/** A page under the navbar: the navbar already names it, so only one short line says what the page is for. */
export const InternalPageTemplate: React.FC<{ subtitle?: string; children: React.ReactNode }> = ({ subtitle, children }) => (
  <div className="space-y-4 w-full max-w-full">
    {subtitle && <p className="text-sm text-slate-400">{subtitle}</p>}
    {children}
  </div>
);
