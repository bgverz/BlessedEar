import { ButtonHTMLAttributes, forwardRef } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
}

const VARIANT_CLASSES: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary: 'bg-amber text-ink hover:bg-amber-dim shadow-glow',
  secondary: 'bg-panel-light text-bone border border-panel-border hover:border-amber/50',
  ghost: 'text-bone-dim hover:text-bone hover:bg-panel-light',
  danger: 'bg-coral/10 text-coral border border-coral/30 hover:bg-coral/20',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', className = '', children, ...props }, ref) => (
    <button
      ref={ref}
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 font-display font-semibold text-sm transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
);
Button.displayName = 'Button';
