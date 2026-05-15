import { useEffect, useState } from 'react'
import { Settings, Save } from 'lucide-react'
import { getPreferences, setPreference, getReorderRules, createReorderRule, deleteReorderRule, getInventory } from '../api/inventory'

export default function SettingsPage() {
  const [prefs, setPrefs] = useState([])
  const [rules, setRules] = useState([])
  const [inventoryItems, setInventoryItems] = useState([])
  const [saving, setSaving] = useState({})
  const [newRule, setNewRule] = useState({
    inventory_item_id: '',
    rule_type: 'hybrid',
    manual_min_stock: '',
    manual_reorder_quantity: '',
    lead_time_days: 2,
  })

  const load = () => {
    Promise.all([
      getPreferences().then(r => setPrefs(r.data)),
      getReorderRules().then(r => setRules(r.data)),
      getInventory().then(r => setInventoryItems(r.data)),
    ])
  }

  useEffect(load, [])

  const savePref = async (key, value) => {
    setSaving(s => ({ ...s, [key]: true }))
    try {
      await setPreference(key, { value })
    } finally {
      setSaving(s => ({ ...s, [key]: false }))
    }
  }

  const saveRule = async () => {
    if (!newRule.inventory_item_id) return
    await createReorderRule({
      ...newRule,
      inventory_item_id: +newRule.inventory_item_id,
      manual_min_stock: newRule.manual_min_stock ? +newRule.manual_min_stock : null,
      manual_reorder_quantity: newRule.manual_reorder_quantity ? +newRule.manual_reorder_quantity : null,
    })
    load()
    setNewRule({ inventory_item_id: '', rule_type: 'hybrid', manual_min_stock: '', manual_reorder_quantity: '', lead_time_days: 2 })
  }

  const EDITABLE_PREFS = ['restaurant_name', 'alert_email', 'default_lead_time_days', 'currency']

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Settings</h2>
        <p className="text-sm text-gray-500">Configure your restaurant preferences and reorder rules</p>
      </div>

      {/* General preferences */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <h3 className="font-semibold text-gray-800">General Preferences</h3>
        {prefs.filter(p => EDITABLE_PREFS.includes(p.key)).map(pref => (
          <PrefRow key={pref.key} pref={pref} saving={saving[pref.key]} onSave={savePref} />
        ))}
      </div>

      {/* Reorder rules */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <div>
          <h3 className="font-semibold text-gray-800">Manual Reorder Rules</h3>
          <p className="text-sm text-gray-400 mt-0.5">
            Override the AI for specific items. "Hybrid" uses your minimums but lets AI decide quantities.
          </p>
        </div>

        {rules.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-100">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">Item</th>
                  <th className="px-3 py-2 text-left">Rule Type</th>
                  <th className="px-3 py-2 text-right">Min Stock</th>
                  <th className="px-3 py-2 text-right">Reorder Qty</th>
                  <th className="px-3 py-2 text-right">Lead Days</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rules.map(rule => {
                  const item = inventoryItems.find(i => i.id === rule.inventory_item_id)
                  return (
                    <tr key={rule.id}>
                      <td className="px-3 py-2 font-medium text-gray-800">{item?.name || `Item #${rule.inventory_item_id}`}</td>
                      <td className="px-3 py-2 capitalize text-gray-600">{rule.rule_type.replace('_', ' ')}</td>
                      <td className="px-3 py-2 text-right">{rule.manual_min_stock ?? '—'}</td>
                      <td className="px-3 py-2 text-right">{rule.manual_reorder_quantity ?? 'AI'}</td>
                      <td className="px-3 py-2 text-right">{rule.lead_time_days}d</td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={async () => { await deleteReorderRule(rule.id); load() }} className="text-xs text-red-400 hover:underline">Remove</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Add rule form */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 pt-2 border-t border-gray-100">
          <div className="col-span-2 md:col-span-1">
            <label className="text-xs text-gray-500">Item</label>
            <select
              className="input w-full"
              value={newRule.inventory_item_id}
              onChange={e => setNewRule(r => ({ ...r, inventory_item_id: e.target.value }))}
            >
              <option value="">Select item...</option>
              {inventoryItems.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Rule Type</label>
            <select className="input w-full" value={newRule.rule_type} onChange={e => setNewRule(r => ({ ...r, rule_type: e.target.value }))}>
              <option value="hybrid">Hybrid (AI + manual min)</option>
              <option value="ai_driven">AI Driven</option>
              <option value="manual_threshold">Manual Only</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Min Stock</label>
            <input type="number" className="input w-full" placeholder="e.g. 10" value={newRule.manual_min_stock} onChange={e => setNewRule(r => ({ ...r, manual_min_stock: e.target.value }))} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Reorder Qty (blank = AI)</label>
            <input type="number" className="input w-full" placeholder="e.g. 50" value={newRule.manual_reorder_quantity} onChange={e => setNewRule(r => ({ ...r, manual_reorder_quantity: e.target.value }))} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Lead Time (days)</label>
            <input type="number" className="input w-full" value={newRule.lead_time_days} onChange={e => setNewRule(r => ({ ...r, lead_time_days: +e.target.value }))} />
          </div>
          <div className="flex items-end">
            <button onClick={saveRule} disabled={!newRule.inventory_item_id} className="btn-primary w-full">
              Add Rule
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function PrefRow({ pref, saving, onSave }) {
  const [val, setVal] = useState(pref.value)

  const LABELS = {
    restaurant_name: 'Restaurant Name',
    alert_email: 'Alert Email',
    default_lead_time_days: 'Default Lead Time (days)',
    currency: 'Currency',
  }

  return (
    <div className="flex items-center gap-4">
      <div className="flex-1">
        <label className="text-sm font-medium text-gray-700">{LABELS[pref.key] || pref.key}</label>
        {pref.description && <p className="text-xs text-gray-400">{pref.description}</p>}
      </div>
      <div className="flex items-center gap-2">
        <input
          className="input w-48"
          value={val}
          onChange={e => setVal(e.target.value)}
          type={pref.key === 'default_lead_time_days' ? 'number' : 'text'}
        />
        <button
          onClick={() => onSave(pref.key, val)}
          disabled={saving}
          className="p-2 text-green-600 hover:bg-green-50 rounded-lg disabled:opacity-50"
          title="Save"
        >
          <Save size={14} />
        </button>
      </div>
    </div>
  )
}
