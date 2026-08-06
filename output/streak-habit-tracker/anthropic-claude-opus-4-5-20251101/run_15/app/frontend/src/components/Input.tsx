import { type InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="space-y-1">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-900">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`
            w-full px-3 py-2 text-sm rounded-lg border
            bg-surface text-gray-900 placeholder-muted
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
            ${error ? 'border-danger' : 'border-border'}
            ${className}
          `}
          {...props}
        />
        {error && (
          <p className="text-xs text-danger">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
