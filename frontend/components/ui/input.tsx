import { cn } from "@/lib/utils";
import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export function Input({ label, error, helperText, className, id, ...props }: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={inputId} className="text-xs font-medium text-ink-2 uppercase tracking-wider">
          {label}
          {props.required && <span className="text-red-500 ml-1" aria-hidden="true">*</span>}
        </label>
      )}
      <input
        id={inputId}
        className={cn(
          "h-9 w-full rounded border border-border-2 bg-canvas px-3 text-sm text-ink",
          "placeholder:text-ink-4 font-sans",
          "focus:outline-none focus:border-ink focus:ring-2 focus:ring-ink/10",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          "transition-all duration-150",
          error && "border-red-400 focus:border-red-500 focus:ring-red-100",
          className
        )}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined}
        {...props}
      />
      {error && (
        <p id={`${inputId}-error`} className="text-xs text-red-600" role="alert">{error}</p>
      )}
      {helperText && !error && (
        <p id={`${inputId}-helper`} className="text-xs text-ink-3">{helperText}</p>
      )}
    </div>
  );
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export function Textarea({ label, error, helperText, className, id, ...props }: TextareaProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={inputId} className="text-xs font-medium text-ink-2 uppercase tracking-wider">
          {label}
        </label>
      )}
      <textarea
        id={inputId}
        className={cn(
          "w-full rounded border border-border-2 bg-canvas px-3 py-2.5 text-sm text-ink font-mono",
          "placeholder:text-ink-4",
          "focus:outline-none focus:border-ink focus:ring-2 focus:ring-ink/10",
          "disabled:opacity-40 disabled:cursor-not-allowed resize-y min-h-[100px]",
          "transition-all duration-150",
          error && "border-red-400 focus:border-red-500 focus:ring-red-100",
          className
        )}
        {...props}
      />
      {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
      {helperText && !error && <p className="text-xs text-ink-3">{helperText}</p>}
    </div>
  );
}
