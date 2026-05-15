import { useEffect, useState } from 'react'
import { Plus, UtensilsCrossed, Trash2 } from 'lucide-react'
import { getMenu, createMenuItem, updateMenuItem, deleteMenuItem, getInventory } from '../api/inventory'

function MenuModal({ item, inventoryItems, onSave, onClose }) {
  const [form, setForm] = useState(item || { name: '', category: 'Main', description: '', price: 0 })
  const [ingredients, setIngredients] = useState(item?.ingredients?.map(i => ({
    inventory_item_id: i.inventory_item_id,
    quantity_per_serving: i.quantity_per_serving,
  })) || [])
  const [loading, setLoading] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const addIngredient = () => setIngredients(prev => [...prev, { inventory_item_id: '', quantity_per_serving: 1 }])
  const updateIng = (i, k, v) => setIngredients(prev => prev.map((ing, idx) => idx === i ? { ...ing, [k]: v } : ing))
  const removeIng = (i) => setIngredients(prev => prev.filter((_, idx) => idx !== i))

  const handleSave = async () => {
    setLoading(true)
    try {
      const payload = { ...form, ingredients: ingredients.filter(i => i.inventory_item_id) }
      if (item?.id) await updateMenuItem(item.id, payload)
      else await createMenuItem(payload)
      onSave()
    } catch (e) {
      alert(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <h3 className="font-semibold text-gray-900">{item?.id ? 'Edit Menu Item' : 'Add Menu Item'}</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="text-xs text-gray-500">Item Name *</label>
            <input className="input w-full" value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Grilled Salmon" />
          </div>
          <div>
            <label className="text-xs text-gray-500">Category</label>
            <input className="input w-full" value={form.category} onChange={e => set('category', e.target.value)} placeholder="Starters, Mains..." />
          </div>
          <div>
            <label className="text-xs text-gray-500">Price ($)</label>
            <input type="number" step="0.01" className="input w-full" value={form.price} onChange={e => set('price', +e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-gray-500">Description</label>
            <textarea className="input w-full resize-none" rows={2} value={form.description || ''} onChange={e => set('description', e.target.value)} />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-gray-700">Ingredients (links to inventory)</label>
            <button onClick={addIngredient} className="text-xs text-brand-600 hover:underline flex items-center gap-1">
              <Plus size={12} /> Add
            </button>
          </div>
          {ingredients.length === 0 && (
            <p className="text-xs text-gray-400">No ingredients linked. Add them so the AI can track ingredient usage.</p>
          )}
          {ingredients.map((ing, i) => (
            <div key={i} className="flex gap-2 mb-2">
              <select
                className="input flex-1"
                value={ing.inventory_item_id}
                onChange={e => updateIng(i, 'inventory_item_id', +e.target.value)}
              >
                <option value="">Select ingredient...</option>
                {inventoryItems.map(item => (
                  <option key={item.id} value={item.id}>{item.name} ({item.unit})</option>
                ))}
              </select>
              <input
                type="number"
                step="0.1"
                className="input w-24"
                placeholder="Qty"
                value={ing.quantity_per_serving}
                onChange={e => updateIng(i, 'quantity_per_serving', +e.target.value)}
              />
              <button onClick={() => removeIng(i)} className="text-red-400 hover:text-red-600">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
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

export default function MenuPage() {
  const [items, setItems] = useState([])
  const [inventoryItems, setInventoryItems] = useState([])
  const [modal, setModal] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    Promise.all([
      getMenu().then(r => setItems(r.data)),
      getInventory().then(r => setInventoryItems(r.data)),
    ]).finally(() => setLoading(false))
  }

  useEffect(load, [])

  const categories = [...new Set(items.map(i => i.category))].sort()

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Menu</h2>
          <p className="text-sm text-gray-500">Link menu items to ingredients for usage tracking</p>
        </div>
        <button onClick={() => setModal({})} className="btn-primary flex items-center gap-2">
          <Plus size={14} />
          Add Menu Item
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-8 text-center">Loading...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <UtensilsCrossed size={32} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium text-gray-600">No menu items yet</p>
          <p className="text-sm mt-1">Add your menu items and link them to ingredients to enable AI usage tracking.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {categories.map(cat => (
            <div key={cat}>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">{cat}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {items.filter(i => i.category === cat).map(item => (
                  <div key={item.id} className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-medium text-gray-900">{item.name}</p>
                        {item.description && <p className="text-xs text-gray-400 mt-0.5">{item.description}</p>}
                        <p className="text-sm font-semibold text-gray-700 mt-1">${item.price.toFixed(2)}</p>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => setModal(item)} className="text-xs text-blue-600 hover:underline">Edit</button>
                        <button
                          onClick={async () => { if (confirm('Remove this menu item?')) { await deleteMenuItem(item.id); load() } }}
                          className="text-xs text-red-400 hover:underline"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                    {item.ingredients.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-gray-100">
                        <p className="text-xs text-gray-400 mb-1">Ingredients:</p>
                        <div className="flex flex-wrap gap-1">
                          {item.ingredients.map(ing => (
                            <span key={ing.id} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                              {ing.inventory_item?.name} × {ing.quantity_per_serving}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {modal !== null && (
        <MenuModal
          item={modal?.id ? modal : null}
          inventoryItems={inventoryItems}
          onSave={() => { setModal(null); load() }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
