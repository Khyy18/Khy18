import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Megaphone, Users, Phone, BarChart3,
  CreditCard, Plug, Settings, LogOut, ChevronLeft, ChevronRight, Menu
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/campaigns', label: 'Campaigns', icon: Megaphone },
  { to: '/leads', label: 'Leads', icon: Users },
  { to: '/voice', label: 'Voice', icon: Phone },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/billing', label: 'Billing', icon: CreditCard },
  { to: '/integrations', label: 'Integrations', icon: Plug },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { logout, user } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-background flex">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/60 z-40 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50
        ${collapsed ? 'w-16' : 'w-60'}
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        bg-card/50 backdrop-blur-xl border-r border-white/10
        flex flex-col transition-all duration-300
      `}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          {!collapsed && <span className="text-lg font-bold text-white">OutboundAI</span>}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-lg hover:bg-white/10 transition-colors hidden lg:block"
          >
            {collapsed ? <ChevronRight className="w-4 h-4 text-white/50" /> : <ChevronLeft className="w-4 h-4 text-white/50" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `
                flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors
                ${isActive ? 'bg-accent/20 text-accent' : 'text-white/60 hover:text-white hover:bg-white/5'}
              `}
            >
              <item.icon className="w-5 h-5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-3 border-t border-white/10">
          {!collapsed && user && (
            <div className="px-3 py-2 mb-2 text-xs text-white/40 truncate">{user.email}</div>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-white/60 hover:text-red-400 hover:bg-red-500/10 transition-colors"
          >
            <LogOut className="w-5 h-5 shrink-0" />
            {!collapsed && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <header className="lg:hidden flex items-center gap-3 p-4 border-b border-white/10 bg-background/80 backdrop-blur-xl sticky top-0 z-30">
          <button onClick={() => setMobileOpen(true)} className="p-2 rounded-lg hover:bg-white/10">
            <Menu className="w-5 h-5 text-white" />
          </button>
          <span className="text-lg font-bold text-white">OutboundAI</span>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
