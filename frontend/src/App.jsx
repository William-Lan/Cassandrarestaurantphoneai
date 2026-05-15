import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Package, UtensilsCrossed, ShoppingCart,
  Truck, Upload, Settings, BrainCircuit, Bell
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Inventory from './pages/Inventory'
import MenuPage from './pages/MenuPage'
import Orders from './pages/Orders'
import Suppliers from './pages/Suppliers'
import ImportPage from './pages/ImportPage'
import AIPage from './pages/AIPage'
import SettingsPage from './pages/SettingsPage'
import { AlertsBanner } from './components/AlertsBanner'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/inventory', icon: Package, label: 'Inventory' },
  { to: '/menu', icon: UtensilsCrossed, label: 'Menu' },
  { to: '/orders', icon: ShoppingCart, label: 'Orders' },
  { to: '/suppliers', icon: Truck, label: 'Suppliers' },
  { to: '/import', icon: Upload, label: 'Import History' },
  { to: '/ai', icon: BrainCircuit, label: 'AI Reorder' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        {/* Sidebar */}
        <aside className="w-56 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
          <div className="p-5 border-b border-gray-100">
            <h1 className="text-lg font-bold text-brand-600">Cassandra</h1>
            <p className="text-xs text-gray-400 mt-0.5">Restaurant Inventory</p>
          </div>
          <nav className="flex-1 p-3 space-y-0.5">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-brand-50 text-brand-600'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="p-4 border-t border-gray-100 text-xs text-gray-400">
            Powered by Claude AI
          </div>
        </aside>

        {/* Main content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <AlertsBanner />
          <main className="flex-1 overflow-y-auto p-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/inventory" element={<Inventory />} />
              <Route path="/menu" element={<MenuPage />} />
              <Route path="/orders" element={<Orders />} />
              <Route path="/suppliers" element={<Suppliers />} />
              <Route path="/import" element={<ImportPage />} />
              <Route path="/ai" element={<AIPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
