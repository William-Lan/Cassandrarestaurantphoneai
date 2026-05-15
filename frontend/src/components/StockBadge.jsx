const STATUS = {
  critical: { label: 'Out of Stock', cls: 'bg-red-100 text-red-700' },
  low: { label: 'Low', cls: 'bg-amber-100 text-amber-700' },
  ok: { label: 'OK', cls: 'bg-green-100 text-green-700' },
  full: { label: 'Full', cls: 'bg-blue-100 text-blue-700' },
}

export function StockBadge({ status }) {
  const s = STATUS[status] || STATUS.ok
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${s.cls}`}>
      {s.label}
    </span>
  )
}
