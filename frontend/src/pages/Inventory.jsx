import { useEffect, useState } from 'react'
import { Plus, Search, SlidersHorizontal } from 'lucide-react'
import { getInventory, createItem, updateItem, deleteItem, addTransaction, getSuppliers } from '../api/inventory'
import { StockBadge } from '../components/StockBadge'

function ItemModal({ item, suppliers, onSave, onClose }) {
  const [form, setForm] = useState(item || {
    name: '', category: 'General', unit: 'unit',
    current_stock: 0, min_stock: 0, max_stock: 100,
    cost_per_unit: 0, supplier_id: null,
  })
  const [loading, setLoading] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSave = async () => {
    setLoading(true)
    try {
      if (item?.id) {
        await updateItem(item.id, form)
      } else {
        await createItem(form)
      }
      onSave()
    } catch (e) {
      alert(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-md p-6 space-y-4">
        <h3 className="font-semibold text-gray-900">{item?.id ? 'Edit Item' : 'Add Inventory Item'}</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="text-xs text-gray-500">Item Name *</label>
            <input className="input w-full" value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Chicken Breast" />
          </div>
          <div>
            <label className="text-xs text-gray-500">Category</label>
            <input className="input w-full" value={form.category} onChange={e => set('category', e.target.value)} placeholder="Meat, Produce..." />
          </div>
          <div>
            <label className="text-xs text-gray-500">Unit</label>
            <input className="input w-full" value={form.unit} onChange={e => set('unit', e.target.value)} placeholder="lb, kg, case..." />
          </div>
          <div>
            <label className="text-xs text-gray-500">Current Stock</label>
            <input type="number" className="input w-full" value={form.current_stock} onChange={e => set('current_stock', +e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Min Stock (alert threshold)</label>
            <input type="number" className="input w-full" value={form.min_stock} onChange={e => set('min_stock', +e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Cost per Unit ($)</label>
            <input type="number" step="0.01" className="input w-full" value={form.cost_per_unit} onChange={e => set('cost_per_unit', +e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Supplier</label>
            <select className="input w-full" value={form.supplier_id || ''} onChange={e => set('supplier_id', e.target.value ? +e.target.value : null)}>
              <option value="">None</option>
              {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
        </div>
        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} disabled={loading || !form.name} className="btn-primary flex-1">
            {loading ? 'Saving...' : 'Save'}
          </button>
          <button onClick={onClose} className="btn-secondary flex-1">Cancel</button>
        </div>
      </div>
    </div>
  )
}

function AdjustModal({ item, onSave, onClose }) {
  const [qty, setQty] = useState(0)
  const [type, setType] = useState('adjustment')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSave = async () => {
    setLoading(true)
    try {
      await addTransaction({
        inventory_item_id: item.id,
        quantity_change: type === 'usage' || type === 'waste' ? -Math.abs(qty) : Math.abs(qty),
        transaction_type: type,
        notes,
      })
      onSave()
    } catch (e) {
      alert(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-sm p-6 space-y-4">
        <h3 className="font-semibold text-gray-900">Adjust Stock — {item.name}</h3>
        <p className="text-sm text-gray-500">Current: {item.current_stock} {item.unit}</p>
        <div>
          <label className="text-xs text-gray-500">Type</label>
          <select className="input w-full" value={type} onChange={e => setType(e.target.value)}>
            <option value="purchase">Purchase / Restock (+)</option>
            <option value="usage">Usage (−)</option>
            <option value="waste">Waste / Spoilage (−)</option>
            <option value="adjustment">Manual Adjustment</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500">Quantity</label>
          <input type="number" step="0.1" className="input w-full" value={qty} onChange={e => setQty(+e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-gray-500">Notes (optional)</label>
          <input className="input w-full" value={notes} onChange={e => setNotes(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <button onClick={handleSave} disabled={loading || qty === 0} className="btn-primary flex-1">
            {loading ? 'Saving...' : 'Apply'}
          </button>
          <button onClick={onClose} className="btn-secondary flex-1">Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function Inventory() {
  const [items, setItems] = useState([])
  const [suppliers, setSuppliers] = useState([])
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [modal, setModal] = useState(null)
  const [adjustItem, setAdjustItem] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    Promise.all([
      getInventory().then(r => setItems(r.data)),
      getSuppliers().then(r => setSuppliers(r.data)),
    ]).finally(() => setLoading(false))
  }

  useEffect(load, [])

  const filtered = items.filter(item => {
    const matchSearch = item.name.toLowerCase().includes(search.toLowerCase()) ||
      item.category.toLowerCase().includes(search.toLowerCase())
    const matchStatus = !filterStatus || item.stock_status === filterStatus
    return matchSearch && matchStatus
  })

  const categories = [...new Set(items.map(i => i.category))].sort()

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Inventory</h2>
          <p className="text-sm text-gray-500">{items.length} items tracked</p>
        </div>
        <button onClick={() => setModal({})} className="btn-primary flex items-center gap-2">
          <Plus size={14} />
          Add Item
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input w-full pl-9"
            placeholder="Search items..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select className="input" value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="">All Status</option>
          <option value="critical">Out of Stock</option>
          <option value="low">Low</option>
          <option value="ok">OK</option>
          <option value="full">Full</option>
        </select>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-8 text-center">Loading inventory...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          {items.length === 0 ? (
            <>
              <p className="font-medium text-gray-600">No inventory items yet</p>
              <p className="text-sm mt-1">Add items manually or import from a supplier invoice.</p>
            </>
          ) : (
            <p>No items match your search.</p>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Item</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-right">Stock</th>
                <th className="px-4 py-3 text-right">Min</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-left">Supplier</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(item => (
                <tr key={item.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{item.name}</td>
                  <td className="px-4 py-3 text-gray-500">{item.category}</td>
                  <td className="px-4 py-3 text-right font-mono">{item.current_stock} {item.unit}</td>
                  <td className="px-4 py-3 text-right text-gray-400 font-mono">{item.min_stock}</td>
                  <td className="px-4 py-3 text-right text-gray-500">${item.cost_per_unit.toFixed(2)}</td>
                  <td className="px-4 py-3 text-gray-400">{item.supplier?.name || '—'}</td>
                  <td className="px-4 py-3 text-center"><StockBadge status={item.stock_status} /></td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <button onClick={() => setAdjustItem(item)} className="text-xs text-blue-600 hover:underline">Adjust</button>
                      <button onClick={() => setModal(item)} className="text-xs text-gray-500 hover:underline">Edit</button>
                      <button onClick={async () => { if (confirm('Archive this item?')) { await deleteItem(item.id); load() } }} className="text-xs text-red-400 hover:underline">Archive</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal !== null && (
        <ItemModal
          item={modal?.id ? modal : null}
          suppliers={suppliers}
          onSave={() => { setModal(null); load() }}
          onClose={() => setModal(null)}
        />
      )}
      {adjustItem && (
        <AdjustModal
          item={adjustItem}
          onSave={() => { setAdjustItem(null); load() }}
          onClose={() => setAdjustItem(null)}
        />
      )}
    </div>
  )
}
