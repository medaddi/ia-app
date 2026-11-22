import React from 'react';

/** A page under the navbar (which already names it): just its content. */
export const InternalPageTemplate: React.FC<{ subtitle?: string; children: React.ReactNode }> = ({ children }) => (
  <div className="space-y-4 w-full max-w-full">{children}</div>
);
