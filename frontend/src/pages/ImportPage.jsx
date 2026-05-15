import { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, CheckCircle, AlertCircle, Loader } from 'lucide-react'
import { uploadImport, confirmImport, getImportHistory } from '../api/inventory'
import api from '../api/client'

function DropZone({ onFile }) {
  const onDrop = useCallback(files => files[0] && onFile(files[0]), [onFile])
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.ms-excel': ['.xls'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
    },
    maxFiles: 1,
  })
  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
        isDragActive ? 'border-brand-500 bg-brand-50' : 'border-gray-300 hover:border-brand-400 hover:bg-gray-50'
      }`}
    >
      <input {...getInputProps()} />
      <Upload size={32} className="mx-auto text-gray-400 mb-3" />
      <p className="text-gray-700 font-medium">Drop your invoice or receipt here</p>
      <p className="text-sm text-gray-400 mt-1">CSV, Excel, PDF, or image — any supplier format</p>
      <p className="text-xs text-gray-400 mt-3">Gordon's Choice, Sysco, US Foods, Restaurant Depot, handwritten receipts...</p>
      <button className="mt-4 px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700">
        Or click to browse files
      </button>
    </div>
  )
}

function ImportPreviewTable({ preview, onConfirm, onCancel }) {
  const [lines, setLines] = useState(preview.lines)
  const [createMissing, setCreateMissing] = useState(true)
  const [loading, setLoading] = useState(false)

  const updateLine = (i, field, value) =>
    setLines(prev => prev.map((l, idx) => idx === i ? { ...l, [field]: value } : l))

  const handleConfirm = async () => {
    setLoading(true)
    try {
      await confirmImport({ import_id: preview.import_id, lines, create_missing_items: createMissing })
      onConfirm()
    } catch (e) {
      alert('Import failed: ' + (e.response?.data?.detail || e.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
        <strong>Claude extracted {preview.lines.length} items</strong> from {preview.filename}
        {preview.supplier_detected && <span> · Supplier: <strong>{preview.supplier_detected}</strong></span>}
        {preview.date_range && <span> · Dates: <strong>{preview.date_range}</strong></span>}
        {preview.unmatched_items.length > 0 && (
          <div className="mt-2 text-amber-700">
            <strong>{preview.unmatched_items.length} items</strong> not matched to existing inventory —
            {createMissing ? ' will be created automatically.' : ' will be skipped.'}
          </div>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600 text-xs uppercase">
            <tr>
              <th className="px-4 py-3 text-left">Item</th>
              <th className="px-4 py-3 text-right">Qty</th>
              <th className="px-4 py-3 text-left">Unit</th>
              <th className="px-4 py-3 text-right">Unit Cost</th>
              <th className="px-4 py-3 text-left">Supplier</th>
              <th className="px-4 py-3 text-left">Date</th>
              <th className="px-4 py-3 text-center">Match</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {lines.map((line, i) => (
              <tr key={i} className={line.matched_inventory_id ? '' : 'bg-amber-50'}>
                <td className="px-4 py-2">
                  <input
                    className="border-0 bg-transparent w-full focus:outline-none focus:ring-1 focus:ring-blue-300 rounded px-1"
                    value={line.item_name}
                    onChange={e => updateLine(i, 'item_name', e.target.value)}
                  />
                </td>
                <td className="px-4 py-2 text-right">{line.quantity}</td>
                <td className="px-4 py-2">{line.unit || '—'}</td>
                <td className="px-4 py-2 text-right">{line.unit_cost ? `$${line.unit_cost.toFixed(2)}` : '—'}</td>
                <td className="px-4 py-2 text-gray-500">{line.supplier || '—'}</td>
                <td className="px-4 py-2 text-gray-500">{line.date || '—'}</td>
                <td className="px-4 py-2 text-center">
                  {line.matched_inventory_id
                    ? <CheckCircle size={14} className="text-green-500 mx-auto" />
                    : <span className="text-xs text-amber-600">New</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
        <input type="checkbox" checked={createMissing} onChange={e => setCreateMissing(e.target.checked)} className="rounded" />
        Automatically create new inventory items for unmatched products
      </label>

      <div className="flex gap-3">
        <button
          onClick={handleConfirm}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
        >
          {loading ? <Loader size={14} className="animate-spin" /> : <CheckCircle size={14} />}
          Import {lines.length} Items
        </button>
        <button onClick={onCancel} className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </div>
  )
}

const POLL_INTERVAL_MS = 3000

export default function ImportPage() {
  const [state, setState] = useState('idle') // idle | uploading | processing | preview | done | error
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])
  const [processingMsg, setProcessingMsg] = useState('')
  const pollRef = useRef(null)

  const loadHistory = () => getImportHistory().then(r => setHistory(r.data)).catch(() => {})
  useEffect(() => { loadHistory() }, [])

  // Stop polling on unmount
  useEffect(() => () => clearInterval(pollRef.current), [])

  const startPolling = (importId) => {
    let attempts = 0
    const msgs = [
      'Claude is reading your file...',
      'Extracting items and prices...',
      'Matching to your inventory...',
      'Almost done...',
    ]
    pollRef.current = setInterval(async () => {
      attempts++
      setProcessingMsg(msgs[Math.min(Math.floor(attempts / 3), msgs.length - 1)])
      try {
        const res = await api.get(`/import/${importId}/status`)
        const { status, preview: previewData, error_message } = res.data

        if (status === 'pending_review') {
          clearInterval(pollRef.current)
          setPreview(previewData)
          setState('preview')
        } else if (status === 'error') {
          clearInterval(pollRef.current)
          setError(error_message || 'Unknown error during processing')
          setState('error')
        }
        // still 'processing' — keep polling
      } catch {
        clearInterval(pollRef.current)
        setError('Lost connection while processing. Please try again.')
        setState('error')
      }
    }, POLL_INTERVAL_MS)
  }

  const handleFile = async (file) => {
    setState('uploading')
    setError('')
    try {
      const res = await uploadImport(file)
      const { import_id } = res.data
      setState('processing')
      startPolling(import_id)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
      setState('error')
    }
  }

  const handleConfirm = () => {
    setState('done')
    loadHistory()
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Import Purchase History</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Upload any supplier invoice, receipt, or CSV export. Claude AI extracts and maps the data automatically.
        </p>
      </div>

      {state === 'idle' && <DropZone onFile={handleFile} />}

      {state === 'uploading' && (
        <div className="flex flex-col items-center py-16 gap-4 text-gray-500">
          <Loader size={36} className="animate-spin text-brand-500" />
          <p className="font-medium">Uploading file...</p>
        </div>
      )}

      {state === 'processing' && (
        <div className="flex flex-col items-center py-16 gap-4 text-gray-500">
          <Loader size={36} className="animate-spin text-purple-500" />
          <p className="font-medium">{processingMsg || 'Claude is reading your file...'}</p>
          <p className="text-sm text-gray-400">Large files can take up to a minute — you can leave this page and come back</p>
        </div>
      )}

      {state === 'preview' && preview && (
        <ImportPreviewTable
          preview={preview}
          onConfirm={handleConfirm}
          onCancel={() => setState('idle')}
        />
      )}

      {state === 'done' && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-8 text-center">
          <CheckCircle size={36} className="text-green-500 mx-auto mb-3" />
          <h3 className="font-semibold text-green-800 text-lg">Import Complete</h3>
          <p className="text-sm text-green-700 mt-1">Your purchase history is now part of the AI's knowledge base.</p>
          <button onClick={() => setState('idle')} className="mt-4 px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700">
            Import Another File
          </button>
        </div>
      )}

      {state === 'error' && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <div className="flex items-center gap-2 text-red-700 font-medium">
            <AlertCircle size={16} />
            Import Failed
          </div>
          <p className="text-sm text-red-600 mt-1">{error}</p>
          <button onClick={() => setState('idle')} className="mt-3 text-sm text-red-700 underline">Try again</button>
        </div>
      )}

      {history.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-800 mb-3">Import History</h3>
          <div className="space-y-2">
            {history.map(imp => (
              <div key={imp.id} className="flex items-center justify-between text-sm py-1">
                <div>
                  <span className="text-gray-800 font-medium">{imp.filename}</span>
                  {imp.supplier_name && <span className="text-gray-400 ml-2">· {imp.supplier_name}</span>}
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-400">
                  <span>{imp.rows_imported}/{imp.rows_extracted} items</span>
                  <span className={
                    imp.status === 'completed' ? 'text-green-600' :
                    imp.status === 'error' ? 'text-red-500' : 'text-gray-400'
                  }>{imp.status}</span>
                  <span>{new Date(imp.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
