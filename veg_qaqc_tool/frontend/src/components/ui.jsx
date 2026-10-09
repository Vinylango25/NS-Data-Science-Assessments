import { clsx } from 'clsx'

export function SeverityBadge({ severity }) {
  const cls = { HIGH: 'badge-high', MEDIUM: 'badge-medium', LOW: 'badge-low' }[severity] || 'badge-low'
  return <span className={cls}>{severity}</span>
}

export function StatusBadge({ status }) {
  const cls = { pass: 'badge-pass', warning: 'badge-warning', fail: 'badge-fail' }[status] || 'badge-low'
  return <span className={cls}>{status ? status.charAt(0).toUpperCase() + status.slice(1) : '—'}</span>
}

export function StatCard({ label, value, sub, color = 'text-white', icon }) {
  return (
    <div className="stat-card">
      <div className="flex items-start justify-between mb-1">
        <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
        {icon && <span className="text-gray-600">{icon}</span>}
      </div>
      <p className={clsx('text-3xl font-bold tracking-tight', color)}>{value ?? '—'}</p>
      {sub && <p className="text-xs text-gray-500 mt-1.5">{sub}</p>}
    </div>
  )
}

export function Spinner({ size = 'md' }) {
  const sz = size === 'sm' ? 'h-4 w-4' : 'h-7 w-7'
  return <div className={clsx('animate-spin rounded-full border-2 border-gray-700 border-t-emerald-500', sz)} />
}

export function Loading({ text = 'Loading…' }) {
  return (
    <div className="flex items-center gap-3 text-gray-500 py-16 justify-center">
      <Spinner /><span className="text-sm">{text}</span>
    </div>
  )
}

export function ErrorBox({ message }) {
  return (
    <div className="rounded-lg bg-red-950/50 border border-red-800/50 px-4 py-3 text-red-400 text-sm">
      <strong className="text-red-300">Error:</strong> {message || 'Something went wrong'}
    </div>
  )
}

export function Empty({ text = 'No data found.' }) {
  return <div className="text-center py-16 text-gray-600 text-sm">{text}</div>
}

export function PageWrapper({ title, subtitle, children, action }) {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="page-title">{title}</h1>
          {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

export function SectionCard({ title, children, className }) {
  return (
    <div className={clsx('card-p', className)}>
      {title && <h2 className="section-title">{title}</h2>}
      {children}
    </div>
  )
}
