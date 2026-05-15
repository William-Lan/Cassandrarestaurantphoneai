import { useEffect, useState } from 'react'
import { Plus, Truck } from 'lucide-react'
import { getSuppliers, createSupplier, updateSupplier } from '../api/inventory'

function SupplierModal({ supplier, onSave, onClose }) {
  const [form, setForm] = useState(supplier || { name: '', contact_email: '', contact_phone: '', notes: '' })
  const [loading, setLoading] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSave = async () => {
    setLoading(true)
    try {
      if (supplier?.id) await updateSupplier(supplier.id, form)
      else await createSupplier(form)
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
        <h3 className="font-semibold text-gray-900">{supplier?.id ? 'Edit Supplier' : 'Add Supplier'}</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500">Supplier Name *</label>
            <input className="input w-full" value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Gordon's Choice" />
          </div>
          <div>
            <label className="text-xs text-gray-500">Contact Email</label>
            <input type="email" className="input w-full" value={form.contact_email || ''} onChange={e => set('contact_email', e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Contact Phone</label>
            <input className="input w-full" value={form.contact_phone || ''} onChange={e => set('contact_phone', e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Notes</label>
            <textarea className="input w-full resize-none" rows={2} value={form.notes || ''} onChange={e => set('notes', e.target.value)} />
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleSave} disabled={loading || !form.name} className="btn-primary flex-1">
            {loading ? 'Saving...' : 'Save'}
          </button>
          <button onClick={onClose} className="btn-secondary flex-1">Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function Suppliers() {
  const [suppliers, setSuppliers] = useState([])
  const [modal, setModal] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    getSuppliers().then(r => setSuppliers(r.data)).finally(() => setLoading(false))
  }

  useEffect(load, [])

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Suppliers</h2>
          <p className="text-sm text-gray-500">{suppliers.length} suppliers</p>
        </div>
        <button onClick={() => setModal({})} className="btn-primary flex items-center gap-2">
          <Plus size={14} />
          Add Supplier
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-8 text-center">Loading...</div>
      ) : suppliers.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Truck size={32} className="mx-auto mb-3 opacity-30" />
          <p>No suppliers yet. Add your vendors here, or they'll be auto-created when you import invoices.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {suppliers.map(s => (
            <div key={s.id} className="bg-white border border-gray-200 rounded-xl p-4 flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900">{s.name}</p>
                <div className="text-sm text-gray-400 mt-0.5 space-x-3">
                  {s.contact_email && <span>{s.contact_email}</span>}
                  {s.contact_phone && <span>{s.contact_phone}</span>}
                  {s.notes && <span className="italic">{s.notes}</span>}
                </div>
              </div>
              <button onClick={() => setModal(s)} className="text-xs text-blue-600 hover:underline">Edit</button>
            </div>
          ))}
        </div>
      )}

      {modal !== null && (
        <SupplierModal
          supplier={modal?.id ? modal : null}
          onSave={() => { setModal(null); load() }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
