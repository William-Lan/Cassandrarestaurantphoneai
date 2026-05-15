import { useEffect, useState } from 'react'
import { ShoppingCart, CheckCircle, Package, X } from 'lucide-react'
import { getOrders, updateOrderStatus, cancelOrder } from '../api/inventory'

const STATUS_STYLE = {
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-blue-100 text-blue-700',
  ordered: 'bg-purple-100 text-purple-700',
  received: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-500',
}

const NEXT_STATUS = {
  pending: 'approved',
  approved: 'ordered',
  ordered: 'received',
}

const NEXT_LABEL = {
  pending: 'Approve',
  approved: 'Mark Ordered',
  ordered: 'Mark Received',
}

export default function Orders() {
  const [orders, setOrders] = useState([])
  const [filter, setFilter] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    getOrders(filter || undefined).then(r => setOrders(r.data)).finally(() => setLoading(false))
  }

  useEffect(load, [filter])

  const advance = async (order) => {
    const next = NEXT_STATUS[order.status]
    if (!next) return
    if (next === 'received' && !confirm('Mark as received? This will update inventory stock levels.')) return
    await updateOrderStatus(order.id, next)
    load()
  }

  const cancel = async (id) => {
    if (!confirm('Cancel this order?')) return
    await cancelOrder(id)
    load()
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Purchase Orders</h2>
          <p className="text-sm text-gray-500">{orders.length} orders</p>
        </div>
        <div className="flex gap-2">
          {['', 'pending', 'approved', 'ordered', 'received', 'cancelled'].map(s => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                filter === s ? 'bg-gray-900 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-8 text-center">Loading orders...</div>
      ) : orders.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <ShoppingCart size={32} className="mx-auto mb-3 opacity-30" />
          <p>No orders found. Use AI Reorder to generate suggestions.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {orders.map(order => (
            <div key={order.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">Order #{order.id}</span>
                      {order.ai_generated && (
                        <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded-full">AI</span>
                      )}
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLE[order.status]}`}>
                        {order.status}
                      </span>
                    </div>
                    <p className="text-sm text-gray-400 mt-0.5">
                      {order.items.length} items · ${order.total_cost.toFixed(2)}
                      {order.supplier && ` · ${order.supplier.name}`}
                      · {new Date(order.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setExpanded(expanded === order.id ? null : order.id)}
                    className="text-xs text-gray-500 hover:text-gray-700"
                  >
                    {expanded === order.id ? 'Hide' : 'View'} items
                  </button>
                  {NEXT_STATUS[order.status] && (
                    <button
                      onClick={() => advance(order)}
                      className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700"
                    >
                      <CheckCircle size={12} />
                      {NEXT_LABEL[order.status]}
                    </button>
                  )}
                  {order.status !== 'received' && order.status !== 'cancelled' && (
                    <button onClick={() => cancel(order.id)} className="p-1.5 text-gray-400 hover:text-red-500">
                      <X size={14} />
                    </button>
                  )}
                </div>
              </div>

              {expanded === order.id && (
                <div className="border-t border-gray-100 px-4 py-3">
                  {order.notes && <p className="text-xs text-gray-400 mb-2 italic">{order.notes}</p>}
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-gray-400 uppercase">
                        <th className="text-left pb-1">Item</th>
                        <th className="text-right pb-1">Qty</th>
                        <th className="text-right pb-1">Unit Cost</th>
                        <th className="text-right pb-1">Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {order.items.map(oi => (
                        <tr key={oi.id}>
                          <td className="py-1.5 text-gray-800">{oi.inventory_item?.name || `Item #${oi.inventory_item_id}`}</td>
                          <td className="py-1.5 text-right text-gray-600">{oi.quantity} {oi.inventory_item?.unit}</td>
                          <td className="py-1.5 text-right text-gray-500">${oi.unit_cost.toFixed(2)}</td>
                          <td className="py-1.5 text-right font-medium">${(oi.quantity * oi.unit_cost).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-gray-200">
                        <td colSpan={3} className="pt-2 text-right text-xs text-gray-500 font-medium">Total</td>
                        <td className="pt-2 text-right font-bold">${order.total_cost.toFixed(2)}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
