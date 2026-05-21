import { useState, useEffect } from 'react'
import { CreditCard, Zap } from 'lucide-react'
import MetricCard from '../components/ui/MetricCard'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import EmptyState from '../components/ui/EmptyState'
import { useApi } from '../hooks/useApi'
import { useToast } from '../components/ui/Toast'

export default function Billing() {
  const [subscription, setSubscription] = useState(null)
  const [usage, setUsage] = useState(null)
  const [plans, setPlans] = useState([])
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const { get, post } = useApi()
  const toast = useToast()

  useEffect(() => {
    const load = async () => {
      try {
        const [sub, usageData, plansData, invoicesData] = await Promise.all([
          get('/api/billing/subscription').catch(() => null),
          get('/api/billing/usage').catch(() => null),
          get('/api/billing/plans').catch(() => []),
          get('/api/billing/invoices').catch(() => []),
        ])
        setSubscription(sub)
        setUsage(usageData)
        setPlans(Array.isArray(plansData) ? plansData : plansData?.plans || [])
        setInvoices(Array.isArray(invoicesData) ? invoicesData : invoicesData?.items || [])
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [get])

  const handleUpgrade = async (planId) => {
    try {
      await post('/api/billing/subscribe', { plan_id: planId })
      toast('Plan upgraded successfully', 'success')
      const sub = await get('/api/billing/subscription').catch(() => null)
      setSubscription(sub)
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  if (loading) return <LoadingSkeleton rows={4} />

  const UsageBar = ({ label, used, limit }) => {
    const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
    return (
      <div>
        <div className="flex justify-between text-sm mb-1">
          <span className="text-white/70">{label}</span>
          <span className="text-white/50">{used} / {limit}</span>
        </div>
        <div className="h-2 bg-white/10 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-yellow-500' : 'bg-accent'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold text-white">Billing</h1>
        <p className="text-white/50 text-sm mt-1">Manage your subscription and usage</p>
      </div>

      {/* Current Plan */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm text-white/50">Current Plan</h3>
            <p className="text-2xl font-bold text-white mt-1">
              {subscription?.plan_name || subscription?.plan || 'Free'}
            </p>
            {subscription?.expires_at && (
              <p className="text-xs text-white/40 mt-1">Renews: {subscription.expires_at}</p>
            )}
          </div>
          <CreditCard className="w-8 h-8 text-accent" />
        </div>
      </div>

      {/* Usage */}
      {usage && (
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 space-y-4">
          <h3 className="text-sm font-medium text-white/70">Usage This Period</h3>
          <UsageBar label="Leads" used={usage.leads_used || 0} limit={usage.leads_limit || 100} />
          <UsageBar label="Emails" used={usage.emails_used || 0} limit={usage.emails_limit || 1000} />
          <UsageBar label="Campaigns" used={usage.campaigns_used || 0} limit={usage.campaigns_limit || 5} />
        </div>
      )}

      {/* Plans */}
      {plans.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-white/70 mb-3">Available Plans</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {plans.map((plan) => (
              <div key={plan.id || plan.name} className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
                <h4 className="font-semibold text-white">{plan.name}</h4>
                <p className="text-2xl font-bold text-white mt-2">
                  ${plan.price || 0}<span className="text-sm text-white/40">/mo</span>
                </p>
                {plan.features && (
                  <ul className="mt-3 space-y-1">
                    {(Array.isArray(plan.features) ? plan.features : []).map((f, i) => (
                      <li key={i} className="text-xs text-white/50 flex items-center gap-1">
                        <Zap className="w-3 h-3 text-accent" /> {f}
                      </li>
                    ))}
                  </ul>
                )}
                <button
                  onClick={() => handleUpgrade(plan.id || plan.name)}
                  disabled={subscription?.plan === plan.name}
                  className="w-full mt-4 py-2 bg-accent hover:bg-accent/80 disabled:opacity-30 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  {subscription?.plan === plan.name ? 'Current' : 'Upgrade'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Invoices */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Invoice History</h3>
        {invoices.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10">
                <th className="px-3 py-2 text-left text-white/50">Date</th>
                <th className="px-3 py-2 text-left text-white/50">Amount</th>
                <th className="px-3 py-2 text-left text-white/50">Status</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv, i) => (
                <tr key={i} className="border-b border-white/5">
                  <td className="px-3 py-2.5 text-white/80">{inv.date || inv.created_at}</td>
                  <td className="px-3 py-2.5 text-white/80">${inv.amount}</td>
                  <td className="px-3 py-2.5 text-green-400">{inv.status || 'paid'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-center py-8 text-white/30 text-sm">No invoices yet</div>
        )}
      </div>
    </div>
  )
}
