import api from './client'

export const getInventory = (params) => api.get('/inventory/', { params })
export const getItem = (id) => api.get(`/inventory/${id}`)
export const createItem = (data) => api.post('/inventory/', data)
export const updateItem = (id, data) => api.patch(`/inventory/${id}`, data)
export const deleteItem = (id) => api.delete(`/inventory/${id}`)
export const getAlerts = () => api.get('/inventory/alerts')
export const addTransaction = (data) => api.post('/inventory/transactions/', data)
export const getTransactions = (itemId) => api.get(`/inventory/${itemId}/transactions`)

export const getMenu = () => api.get('/menu/')
export const createMenuItem = (data) => api.post('/menu/', data)
export const updateMenuItem = (id, data) => api.patch(`/menu/${id}`, data)
export const deleteMenuItem = (id) => api.delete(`/menu/${id}`)

export const getSuppliers = () => api.get('/suppliers/')
export const createSupplier = (data) => api.post('/suppliers/', data)
export const updateSupplier = (id, data) => api.patch(`/suppliers/${id}`, data)

export const getOrders = (status) => api.get('/orders/', { params: status ? { status } : {} })
export const createOrder = (data) => api.post('/orders/', data)
export const updateOrderStatus = (id, status) => api.patch(`/orders/${id}/status`, null, { params: { status } })
export const cancelOrder = (id) => api.delete(`/orders/${id}`)

export const uploadImport = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/import/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
}
export const confirmImport = (data) => api.post('/import/confirm', data)
export const getImportHistory = () => api.get('/import/history')

export const getAISuggestions = () => api.get('/ai/reorder-suggestions')
export const createOrderFromSuggestions = () => api.post('/ai/create-order-from-suggestions')

export const getPreferences = () => api.get('/preferences/')
export const setPreference = (key, data) => api.put(`/preferences/${key}`, data)
export const getReorderRules = () => api.get('/preferences/reorder-rules/')
export const createReorderRule = (data) => api.post('/preferences/reorder-rules/', data)
export const deleteReorderRule = (id) => api.delete(`/preferences/reorder-rules/${id}`)
