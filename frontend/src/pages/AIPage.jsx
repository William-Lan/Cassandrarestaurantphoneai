import { useState } from 'react'
import { BrainCircuit, Loader, ShoppingCart, AlertTriangle, RefreshCw } from 'lucide-react'
import { getAISuggestions, createOrderFromSuggestions } from '../api/inventory'

const URGENCY_STYLE = {
  critical: 'bg-red-50 border-red-200 text-red-800',
  high: 'bg-orange-50 border-orange-200 text-orange-800',
  medium: 'bg-amber-50 border-amber-200 text-amber-800',
  low: 'bg-blue-50 border-blue-200 text-blue-800',
}

const URGENCY_DOT = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-amber-500',
  low: 'bg-blue-400',
}

export default function AIPage() {
  const [state, setState] = useState('idle')
  const [data, setData] = useState(null)
  const [orderResult, setOrderResult] = useState(null)
  const [orderLoading, setOrderLoading] = useState(false)

  const fetchSuggestions = async () => {
    setState('loading')
    setData(null)
    setOrderResult(null)
    try {
      const res = await getAISuggestions()
      setData(res.data)
      setState('done')
    } catch (e) {
      setState('error')
    }
  }

  const handleCreateOrder = async () => {
    setOrderLoading(true)
    try {
      const res = await createOrderFromSuggestions()
      setOrderResult(res.data)
    } catch (e) {
      alert('Failed to create order: ' + (e.response?.data?.detail || e.message))
    } finally {
      setOrderLoading(false)
    }
  }

  const totalCost = data?.suggestions.reduce((s, sg) => s + sg.estimated_cost, 0) || 0

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">AI Reorder Suggestions</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Claude analyzes your current stock, purchase history, and usage patterns to recommend what to reorder.
        </p>
      </div>

      {state === 'idle' && (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
          <BrainCircuit size={40} className="mx-auto text-purple-400 mb-4" />
          <h3 className="font-semibold text-gray-800">Ready to analyze your inventory</h3>
          <p className="text-sm text-gray-400 mt-1 mb-6">
            Claude will look at your stock levels, what you've ordered in the past, and how fast items are used.
          </p>
          <button
            onClick={fetchSuggestions}
            className="flex items-center gap-2 mx-auto px-6 py-2.5 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700"
          >
            <BrainCircuit size={16} />
            Analyze & Suggest Reorders
          </button>
        </div>
      )}

      {state === 'loading' && (
        <div className="flex flex-col items-center py-16 gap-4 text-gray-500">
          <Loader size={36} className="animate-spin text-purple-500" />
          <p className="font-medium">Claude is analyzing your inventory...</p>
          <p className="text-sm">Reviewing stock levels, purchase history, and usage trends</p>
        </div>
      )}

      {state === 'error' && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <AlertTriangle size={24} className="text-red-500 mx-auto mb-2" />
          <p className="text-red-700 font-medium">Analysis failed</p>
          <p className="text-sm text-red-500 mt-1">Make sure your ANTHROPIC_API_KEY is set and you have inventory data.</p>
          <button onClick={fetchSuggestions} className="mt-3 text-sm text-red-700 underline">Try again</button>
        </div>
      )}

      {state === 'done' && data && (
        <div className="space-y-4">
          {/* Summary bar */}
          <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-medium text-purple-800">{data.summary}</p>
                <p className="text-xs text-purple-600 mt-1">
                  Generated at {new Date(data.generated_at).toLocaleTimeString()}
                  · {data.suggestions.length} suggestions · Est. total ${totalCost.toFixed(2)}
                </p>
              </div>
              <button
                onClick={fetchSuggestions}
                className="p-1.5 rounded-lg hover:bg-purple-100 text-purple-600"
                title="Refresh"
              >
                <RefreshCw size={14} />
              </button>
            </div>
          </div>

          {data.suggestions.length === 0 ? (
            <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center text-green-700 text-sm">
              Your inventory looks healthy — no urgent reorders needed right now.
            </div>
          ) : (
            <>
              <div className="space-y-3">
                {data.suggestions.map(sg => (
                  <div
                    key={sg.inventory_item_id}
                    className={`border rounded-xl p-4 ${URGENCY_STYLE[sg.urgency] || URGENCY_STYLE.low}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full mt-0.5 ${URGENCY_DOT[sg.urgency]}`} />
                        <div>
                          <p className="font-medium">{sg.item_name}</p>
                          <p className="text-xs opacity-70 mt-0.5">{sg.reason}</p>
                        </div>
                      </div>
                      <div className="text-right text-sm">
                        <p className="font-semibold">Order {sg.suggested_quantity} {sg.unit}</p>
                        <p className="text-xs opacity-70">${sg.estimated_cost.toFixed(2)}</p>
                        {sg.days_until_stockout !== null && (
                          <p className="text-xs opacity-70">{sg.days_until_stockout}d until stockout</p>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 text-xs opacity-60">
                      Current: {sg.current_stock} {sg.unit}
                      <span className="mx-1.5">·</span>
                      Urgency: <span className="capitalize">{sg.urgency}</span>
                    </div>
                  </div>
                ))}
              </div>

              {orderResult ? (
                <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-800">
                  <strong>Purchase order #{orderResult.order_id} created</strong> — total ${orderResult.total_cost?.toFixed(2)}
                  <span className="text-green-600 ml-2">Go to Orders to approve it.</span>
                </div>
              ) : (
                <button
                  onClick={handleCreateOrder}
                  disabled={orderLoading}
                  className="flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-50"
                >
                  {orderLoading ? <Loader size={14} className="animate-spin" /> : <ShoppingCart size={14} />}
                  Create Purchase Order (${totalCost.toFixed(2)})
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
