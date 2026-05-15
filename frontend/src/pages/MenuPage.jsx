import { useEffect, useState, useCallback, useRef } from 'react'
import { Plus, UtensilsCrossed, Trash2, Upload, X, FileText, CheckCircle, AlertTriangle } from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import { getMenu, createMenuItem, updateMenuItem, deleteMenuItem, getInventory, uploadMenuImport, getMenuImportStatus, confirmMenuImport } from '../api/inventory'

// ── Menu item edit modal ──────────────────────────────────────────────────────

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

// ── Menu import modal ─────────────────────────────────────────────────────────

const POLL_MESSAGES = [
  'Reading your menu…',
  'Identifying dishes…',
  'Extracting categories & prices…',
  'Almost done…',
]

function MenuImportModal({ onDone, onClose }) {
  const [phase, setPhase] = useState('drop')   // drop | processing | review | confirming | done
  const [importId, setImportId] = useState(null)
  const [msgIdx, setMsgIdx] = useState(0)
  const [items, setItems] = useState([])        // extracted items for review
  const [error, setError] = useState(null)
  const pollRef = useRef(null)
  const msgRef = useRef(null)

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (msgRef.current) clearInterval(msgRef.current)
  }

  useEffect(() => () => stopPolling(), [])

  const onDrop = useCallback(async (accepted) => {
    if (!accepted.length) return
    const file = accepted[0]
    setPhase('processing')
    setError(null)
    setMsgIdx(0)

    msgRef.current = setInterval(() => setMsgIdx(i => Math.min(i + 1, POLL_MESSAGES.length - 1)), 4000)

    try {
      const res = await uploadMenuImport(file)
      const id = res.data.import_id
      setImportId(id)

      pollRef.current = setInterval(async () => {
        try {
          const s = await getMenuImportStatus(id)
          const { status, preview, error_message } = s.data
          if (status === 'pending_review' && preview) {
            stopPolling()
            setItems(preview.items.map(it => ({ ...it })))
            setPhase('review')
          } else if (status === 'error') {
            stopPolling()
            setError(error_message || 'Processing failed')
            setPhase('drop')
          }
        } catch {
          // keep polling
        }
      }, 3000)
    } catch (e) {
      stopPolling()
      setError(e.response?.data?.detail || e.message)
      setPhase('drop')
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/*': ['.png', '.jpg', '.jpeg', '.webp'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    },
    maxFiles: 1,
    disabled: phase !== 'drop',
  })

  const updateItem = (i, k, v) => setItems(prev => prev.map((it, idx) => idx === i ? { ...it, [k]: v } : it))
  const removeItem = (i) => setItems(prev => prev.filter((_, idx) => idx !== i))

  const handleConfirm = async () => {
    setPhase('confirming')
    try {
      const res = await confirmMenuImport({ import_id: importId, items })
      setPhase('done')
      setTimeout(() => { onDone(res.data.created) }, 1200)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
      setPhase('review')
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-2xl p-6 space-y-4 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Import Menu from File</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>

        {/* Drop zone */}
        {(phase === 'drop') && (
          <div>
            {error && (
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg p-3 mb-3">
                <AlertTriangle size={15} /> {error}
              </div>
            )}
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${isDragActive ? 'border-brand-400 bg-brand-50' : 'border-gray-200 hover:border-brand-300 hover:bg-gray-50'}`}
            >
              <input {...getInputProps()} />
              <Upload size={28} className="mx-auto mb-3 text-gray-400" />
              <p className="font-medium text-gray-700">Drop your menu file here</p>
              <p className="text-sm text-gray-400 mt-1">PDF, image (JPG/PNG), CSV, or Excel</p>
              <p className="text-xs text-gray-300 mt-2">Claude will extract all dishes, categories & prices</p>
            </div>
          </div>
        )}

        {/* Processing */}
        {phase === 'processing' && (
          <div className="flex-1 flex flex-col items-center justify-center py-12 space-y-4">
            <div className="w-10 h-10 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-gray-600 animate-pulse">{POLL_MESSAGES[msgIdx]}</p>
          </div>
        )}

        {/* Review table */}
        {phase === 'review' && (
          <>
            <p className="text-sm text-gray-500">
              Claude found <strong>{items.length} dishes</strong>. Review and edit below, then confirm to add them to your menu.
            </p>
            <div className="flex-1 overflow-y-auto border border-gray-200 rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 text-xs font-semibold text-gray-500">Name</th>
                    <th className="text-left px-3 py-2 text-xs font-semibold text-gray-500">Category</th>
                    <th className="text-left px-3 py-2 text-xs font-semibold text-gray-500 w-24">Price</th>
                    <th className="px-3 py-2 w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, i) => (
                    <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                      <td className="px-3 py-1.5">
                        <input
                          className="input w-full text-sm py-1"
                          value={it.name}
                          onChange={e => updateItem(i, 'name', e.target.value)}
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <input
                          className="input w-full text-sm py-1"
                          value={it.category || ''}
                          onChange={e => updateItem(i, 'category', e.target.value)}
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <input
                          type="number"
                          step="0.01"
                          className="input w-full text-sm py-1"
                          value={it.price || 0}
                          onChange={e => updateItem(i, 'price', +e.target.value)}
                        />
                      </td>
                      <td className="px-3 py-1.5 text-center">
                        <button onClick={() => removeItem(i)} className="text-red-300 hover:text-red-500">
                          <X size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {error && (
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg p-3">
                <AlertTriangle size={15} /> {error}
              </div>
            )}
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleConfirm}
                disabled={items.length === 0}
                className="btn-primary flex-1"
              >
                Add {items.length} item{items.length !== 1 ? 's' : ''} to menu
              </button>
              <button onClick={onClose} className="btn-secondary">Cancel</button>
            </div>
          </>
        )}

        {/* Confirming */}
        {phase === 'confirming' && (
          <div className="flex-1 flex flex-col items-center justify-center py-12 space-y-3">
            <div className="w-10 h-10 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-gray-500">Saving dishes…</p>
          </div>
        )}

        {/* Done */}
        {phase === 'done' && (
          <div className="flex-1 flex flex-col items-center justify-center py-12 space-y-3">
            <CheckCircle size={40} className="text-green-500" />
            <p className="font-medium text-gray-700">Menu imported!</p>
            <p className="text-sm text-gray-400">Now open each dish to link its ingredients.</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MenuPage() {
  const [items, setItems] = useState([])
  const [inventoryItems, setInventoryItems] = useState([])
  const [modal, setModal] = useState(null)
  const [importModal, setImportModal] = useState(false)
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
        <div className="flex gap-2">
          <button onClick={() => setImportModal(true)} className="btn-secondary flex items-center gap-2">
            <FileText size={14} />
            Import from File
          </button>
          <button onClick={() => setModal({})} className="btn-primary flex items-center gap-2">
            <Plus size={14} />
            Add Menu Item
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-8 text-center">Loading...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <UtensilsCrossed size={32} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium text-gray-600">No menu items yet</p>
          <p className="text-sm mt-1">Import your menu file or add items manually, then link them to ingredients.</p>
          <button onClick={() => setImportModal(true)} className="mt-4 btn-primary inline-flex items-center gap-2">
            <Upload size={14} /> Import Menu
          </button>
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
                    {item.ingredients.length > 0 ? (
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
                    ) : (
                      <div className="mt-2 pt-2 border-t border-gray-100">
                        <button onClick={() => setModal(item)} className="text-xs text-amber-500 hover:underline">
                          + Link ingredients
                        </button>
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

      {importModal && (
        <MenuImportModal
          onDone={(created) => { setImportModal(false); load() }}
          onClose={() => setImportModal(false)}
        />
      )}
    </div>
  )
}
