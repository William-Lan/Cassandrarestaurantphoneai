import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Package, ShoppingCart, AlertTriangle, BrainCircuit, TrendingUp, Upload } from 'lucide-react'
import { getInventory, getAlerts, getOrders, getImportHistory } from '../api/inventory'

function StatCard({ icon: Icon, label, value, sub, color = 'blue', to }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    red: 'bg-red-50 text-red-600',
    green: 'bg-green-50 text-green-600',
    amber: 'bg-amber-50 text-amber-600',
    purple: 'bg-purple-50 text-purple-600',
  }
  const card = (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-3xl font-bold mt-1 text-gray-900">{value}</p>
          {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${colors[color]}`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  )
  return to ? <Link to={to}>{card}</Link> : card
}

export default function Dashboard() {
  const [items, setItems] = useState([])
  const [alerts, setAlerts] = useState([])
  const [orders, setOrders] = useState([])
  const [imports, setImports] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getInventory().then(r => setItems(r.data)),
      getAlerts().then(r => setAlerts(r.data)),
      getOrders().then(r => setOrders(r.data)),
      getImportHistory().then(r => setImports(r.data)),
    ]).finally(() => setLoading(false))
  }, [])

  const critical = alerts.filter(a => a.severity === 'critical').length
  const pending = orders.filter(o => o.status === 'pending').length
  const totalValue = items.reduce((s, i) => s + i.current_stock * i.cost_per_unit, 0)

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Dashboard</h2>
        <p className="text-sm text-gray-500 mt-0.5">Overview of your restaurant inventory</p>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm">Loading...</div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard icon={Package} label="Total Items" value={items.length} sub="active inventory items" color="blue" to="/inventory" />
            <StatCard icon={AlertTriangle} label="Low / Out" value={alerts.length} sub={`${critical} critical`} color={alerts.length > 0 ? 'red' : 'green'} to="/inventory?status=low" />
            <StatCard icon={ShoppingCart} label="Pending Orders" value={pending} sub="awaiting approval" color="amber" to="/orders" />
            <StatCard icon={TrendingUp} label="Inventory Value" value={`$${totalValue.toFixed(0)}`} sub="at cost" color="green" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Low stock list */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <AlertTriangle size={15} className="text-amber-500" />
                Items Needing Attention
              </h3>
              {alerts.length === 0 ? (
                <p className="text-sm text-gray-400">All items are well-stocked.</p>
              ) : (
                <div className="space-y-2">
                  {alerts.slice(0, 6).map(a => (
                    <div key={a.item_id} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{a.item_name}</span>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        a.severity === 'critical' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                      }`}>
                        {a.current_stock <= 0 ? 'Out of stock' : `${a.current_stock} ${a.unit}`}
                      </span>
                    </div>
                  ))}
                  {alerts.length > 6 && (
                    <Link to="/inventory" className="text-xs text-brand-600 hover:underline">
                      +{alerts.length - 6} more
                    </Link>
                  )}
                </div>
              )}
            </div>

            {/* Recent imports */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <Upload size={15} className="text-blue-500" />
                Recent Imports
              </h3>
              {imports.length === 0 ? (
                <div className="text-sm text-gray-400">
                  <p>No imports yet.</p>
                  <Link to="/import" className="text-brand-600 hover:underline text-xs mt-1 block">
                    Upload your first invoice or receipt →
                  </Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {imports.slice(0, 5).map(imp => (
                    <div key={imp.id} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700 truncate max-w-[180px]" title={imp.filename}>
                        {imp.filename}
                      </span>
                      <span className={`text-xs ${
                        imp.status === 'completed' ? 'text-green-600' :
                        imp.status === 'error' ? 'text-red-500' : 'text-gray-400'
                      }`}>
                        {imp.status === 'completed' ? `${imp.rows_imported} items` : imp.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Quick actions */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-3">Quick Actions</h3>
            <div className="flex flex-wrap gap-3">
              <Link to="/import" className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors">
                <Upload size={14} />
                Import Receipts
              </Link>
              <Link to="/ai" className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors">
                <BrainCircuit size={14} />
                Get AI Suggestions
              </Link>
              <Link to="/orders" className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors">
                <ShoppingCart size={14} />
                View Orders
              </Link>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
