import { useState, useEffect } from 'react'
import { Users, Activity, ListTodo, Shield } from 'lucide-react'

/**
 * Admin panel for super_admin users
 * Shows platform stats and tenant management
 */
export default function AdminPanel() {
  const [stats, setStats] = useState(null)
  const [tenants, setTenants] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('ai_office_token')
    const headers = { 'Authorization': `Bearer ${token}` }

    Promise.all([
      fetch('/api/admin/stats', { headers }).then(r => r.ok ? r.json() : null),
      fetch('/api/admin/tenants', { headers }).then(r => r.ok ? r.json() : null)
    ]).then(([statsData, tenantsData]) => {
      setStats(statsData)
      setTenants(tenantsData || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleSuspend = async (tenantId) => {
    const token = localStorage.getItem('ai_office_token')
    try {
      const response = await fetch(`/api/admin/tenants/${tenantId}/suspend`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        setTenants(prev =>
          prev.map(t => t.id === tenantId ? { ...t, is_active: false } : t)
        )
      }
    } catch (err) {
      // silent fail
    }
  }

  if (loading) {
    return (
      <div className="text-center py-8 text-white/30 text-sm">
        Loading admin panel...
      </div>
    )
  }

  const statCards = [
    { label: 'Total Tenants', value: stats?.total_tenants || 0, icon: Users },
    { label: 'Active Tenants', value: stats?.active_tenants || 0, icon: Shield },
    { label: 'Tasks Today', value: stats?.tasks_today || 0, icon: ListTodo },
    { label: 'Total Users', value: stats?.total_users || 0, icon: Activity },
  ]

  return (
    <div className="space-y-4">
      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-3">
        {statCards.map(card => {
          const Icon = card.icon
          return (
            <div key={card.label} className="bg-white/5 border border-white/10 rounded-xl p-3">
              <div className="flex items-center gap-2 mb-1">
                <Icon className="w-4 h-4 text-accent" />
                <span className="text-white/50 text-xs">{card.label}</span>
              </div>
              <p className="text-white text-xl font-semibold">{card.value}</p>
            </div>
          )
        })}
      </div>

      {/* Tenants table */}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="p-3 border-b border-white/10">
          <h3 className="text-white font-medium">Tenants</h3>
        </div>
        <div className="divide-y divide-white/5">
          {tenants.length === 0 ? (
            <div className="p-4 text-center text-white/30 text-sm">
              No tenants found
            </div>
          ) : (
            tenants.map(tenant => (
              <div key={tenant.id} className="p-3 flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">
                    {tenant.name || tenant.company_name}
                  </p>
                  <p className="text-white/40 text-xs">
                    {tenant.email} | {tenant.plan || 'trial'} | {tenant.task_count || 0} tasks
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    tenant.is_active !== false
                      ? 'bg-green-500/10 text-green-400'
                      : 'bg-red-500/10 text-red-400'
                  }`}>
                    {tenant.is_active !== false ? 'active' : 'suspended'}
                  </span>
                  {tenant.is_active !== false && (
                    <button
                      onClick={() => handleSuspend(tenant.id)}
                      className="text-xs text-red-400 hover:text-red-300 transition-colors"
                    >
                      Suspend
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
