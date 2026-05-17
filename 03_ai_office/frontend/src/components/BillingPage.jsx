import { useState, useEffect } from 'react'
import { CreditCard } from 'lucide-react'

/**
 * Billing page showing current plan, usage stats, and upgrade option
 */
export default function BillingPage() {
  const [usage, setUsage] = useState(null)
  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [upgrading, setUpgrading] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('ai_office_token')
    const headers = { 'Authorization': `Bearer ${token}` }

    Promise.all([
      fetch('/api/billing/usage', { headers }).then(r => r.ok ? r.json() : null),
      fetch('/api/billing/subscription', { headers }).then(r => r.ok ? r.json() : null)
    ]).then(([usageData, subData]) => {
      setUsage(usageData)
      setSubscription(subData)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleUpgrade = async () => {
    setUpgrading(true)
    try {
      const token = localStorage.getItem('ai_office_token')
      const response = await fetch('/api/billing/checkout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      if (response.ok) {
        const data = await response.json()
        if (data.checkout_url) {
          window.location.href = data.checkout_url
        }
      }
    } catch (err) {
      // silent fail
    } finally {
      setUpgrading(false)
    }
  }

  if (loading) {
    return (
      <div className="text-center py-8 text-white/30 text-sm">
        Loading billing info...
      </div>
    )
  }

  const tasksUsed = usage?.tasks_used || 0
  const tasksLimit = usage?.tasks_limit || 1000
  const agentsActive = usage?.agents_active || 0
  const agentsLimit = usage?.agents_limit || 5
  const tasksPercent = Math.min((tasksUsed / tasksLimit) * 100, 100)
  const agentsPercent = Math.min((agentsActive / agentsLimit) * 100, 100)

  return (
    <div className="space-y-4">
      {/* Current Plan Card */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4">
        <div className="flex items-center gap-3 mb-3">
          <CreditCard className="w-5 h-5 text-accent" />
          <h3 className="text-white font-medium">Current Plan</h3>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-white text-lg font-semibold capitalize">
              {subscription?.plan_name || 'Free'}
            </p>
            <p className="text-white/50 text-sm">
              Status: <span className="text-green-400">{subscription?.status || 'active'}</span>
            </p>
          </div>
          <button
            onClick={handleUpgrade}
            disabled={upgrading}
            className="bg-accent hover:bg-accent/80 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            {upgrading ? 'Loading...' : 'Upgrade Plan'}
          </button>
        </div>
      </div>

      {/* Usage Stats */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-4">
        <h3 className="text-white font-medium">Usage This Month</h3>

        {/* Tasks usage */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-white/60 text-sm">Tasks</span>
            <span className="text-white/60 text-sm">{tasksUsed} / {tasksLimit}</span>
          </div>
          <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all"
              style={{ width: `${tasksPercent}%` }}
            />
          </div>
        </div>

        {/* Agents usage */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-white/60 text-sm">Active Agents</span>
            <span className="text-white/60 text-sm">{agentsActive} / {agentsLimit}</span>
          </div>
          <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 rounded-full transition-all"
              style={{ width: `${agentsPercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
