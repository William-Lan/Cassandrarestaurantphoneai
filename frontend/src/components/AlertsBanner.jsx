import { useEffect, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { getAlerts } from '../api/inventory'

export function AlertsBanner() {
  const [alerts, setAlerts] = useState([])
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    getAlerts().then(r => setAlerts(r.data)).catch(() => {})
    const id = setInterval(() => {
      getAlerts().then(r => setAlerts(r.data)).catch(() => {})
    }, 60000)
    return () => clearInterval(id)
  }, [])

  if (dismissed || alerts.length === 0) return null

  const criticals = alerts.filter(a => a.severity === 'critical')
  const warnings = alerts.filter(a => a.severity === 'warning')

  return (
    <div className={`px-6 py-2 flex items-center justify-between text-sm ${
      criticals.length > 0 ? 'bg-red-50 border-b border-red-200 text-red-800' : 'bg-amber-50 border-b border-amber-200 text-amber-800'
    }`}>
      <div className="flex items-center gap-2">
        <AlertTriangle size={15} />
        <span className="font-medium">
          {criticals.length > 0
            ? `${criticals.length} item${criticals.length > 1 ? 's' : ''} out of stock`
            : `${warnings.length} item${warnings.length > 1 ? 's' : ''} running low`}
        </span>
        <span className="text-xs opacity-70">
          — {alerts.slice(0, 3).map(a => a.item_name).join(', ')}
          {alerts.length > 3 ? ` +${alerts.length - 3} more` : ''}
        </span>
      </div>
      <button onClick={() => setDismissed(true)} className="opacity-60 hover:opacity-100">
        <X size={14} />
      </button>
    </div>
  )
}
