/** 通用 UI 组件：状态展示、卡片、按钮、表单控件 */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from 'react'
import { ApiError } from '../api/client'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-ink-200 bg-white shadow-sm ${className}`}>
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-ink-100 px-5 py-3.5">
      <div>
        <h3 className="text-sm font-semibold text-ink-900">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
      </div>
      {actions}
    </div>
  )
}

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' | 'subtle' }) {
  const base =
    'inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50'
  const variants = {
    primary: 'bg-ink-900 text-white hover:bg-ink-800',
    subtle: 'bg-ink-100 text-ink-800 hover:bg-ink-200',
    ghost: 'text-ink-600 hover:bg-ink-100',
    danger: 'bg-red-600 text-white hover:bg-red-700',
  }
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />
}

export function Input({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-900 outline-none transition placeholder:text-ink-400 focus:border-ink-400 focus:ring-2 focus:ring-ink-100 ${className}`}
      {...props}
    />
  )
}

export function Textarea({ className = '', ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm leading-relaxed text-ink-900 outline-none transition placeholder:text-ink-400 focus:border-ink-400 focus:ring-2 focus:ring-ink-100 ${className}`}
      {...props}
    />
  )
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
        checked ? 'border-ink-900 bg-ink-900 text-white' : 'border-ink-200 bg-white text-ink-500'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${checked ? 'bg-white' : 'bg-ink-300'}`} />
      {label}
    </button>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'warn' }) {
  const tones = {
    neutral: 'bg-ink-100 text-ink-600',
    accent: 'bg-indigo-50 text-indigo-700',
    warn: 'bg-amber-50 text-amber-700',
  }
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>
}

export function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="flex items-center gap-3 px-5 py-8 text-sm text-ink-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-200 border-t-ink-600" />
      {text}
    </div>
  )
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-5 py-12 text-center">
      <p className="text-sm font-medium text-ink-700">{title}</p>
      {hint && <p className="max-w-md text-xs leading-relaxed text-ink-500">{hint}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : String(error)

  return (
    <div className="m-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
      <p className="text-sm font-medium text-red-700">请求失败</p>
      <p className="mt-1 text-xs leading-relaxed text-red-600">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 text-xs font-medium text-red-700 underline">
          重试
        </button>
      )}
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-600">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-ink-400">{hint}</span>}
    </label>
  )
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white px-5 py-4">
      <p className="text-xs text-ink-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-ink-900">{value}</p>
    </div>
  )
}
