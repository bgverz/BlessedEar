import { HTMLAttributes } from 'react';

export function Panel({ children, className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`bg-panel border border-panel-border rounded-2xl p-6 shadow-panel ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
