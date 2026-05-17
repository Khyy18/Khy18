import { useState, useEffect } from 'react'
import { Megaphone, Users, Calendar, MessageSquare, Activity } from 'lucide-react'
import MetricCard from '../components/ui/MetricCard'
import FunnelChart from '../components/ui/FunnelChart'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import { useApi } from '../hooks/useApi'

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null)
  const [funnel, setFunnel] = useState([])
  const [recentActivity, setRecentActivity] = useState([])
  const [loading, setLoading] = useState(true)
  const { get } = useApi()

  useEffect(() => {
    const load = async () => {
      try {
        const [funnelData, campaigns, leads] = await Promise.all([
          get('/api/analytics/funnel').catch(() => null),
          get('/api/campaigns').catch(() => []),
          get('/api/leads').catch(() => []),
        ])

        const campaignList = Array.isArray(campaigns) ? campaigns : campaigns?.items || []
        const leadList = Array.isArray(leads) ? leads : leads?.items || []
        const activeCampaigns = campaignList.filter(c => c.status === 'active').length

        setMetrics({
          activeCampaigns,
          totalLeads: leadList.length,
          meetingsBooked: funnelData?.meetings_booked || 0,
          replyRate: funnelData?.reply_rate || 0,
        })

        if (funnelData?.stages) {
          setFunnel(funnelData.stages)
        } else if (funnelData) {
          setFunnel([
            { name: 'Contacted', value: funnelData.contacted || 0 },
            { name: 'Opened', value: funnelData.opened || 0 },
            { name: 'Replied', value: funnelData.replied || 0 },
            { name: 'Meetings', value: funnelData.meetings_booked || 0 },
          ])
        }

        setRecentActivity(leadList.slice(0, 5).map(l => ({
          id: l.id,
          message: `Lead ${l.name || l.email} - ${l.status}`,
          time: l.updated_at || l.created_at,
        })))
      } catch (err) {
        console.error('Dashboard load error:', err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [get])

  if (loading) return <LoadingSkeleton rows={4} />

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-white/50 text-sm mt-1">Overview of your outbound performance</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Active Campaigns" value={metrics?.activeCampaigns || 0} icon={Megaphone} />
        <MetricCard title="Total Leads" value={metrics?.totalLeads || 0} icon={Users} />
        <MetricCard title="Meetings Booked" value={metrics?.meetingsBooked || 0} icon={Calendar} />
        <MetricCard title="Reply Rate" value={`${metrics?.replyRate || 0}%`} icon={MessageSquare} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-4">Outreach Funnel</h3>
          {funnel.length > 0 ? (
            <FunnelChart data={funnel} />
          ) : (
            <div className="h-48 flex items-center justify-center text-white/30 text-sm">
              No funnel data yet
            </div>
          )}
        </div>

        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-4">Recent Activity</h3>
          {recentActivity.length > 0 ? (
            <div className="space-y-3">
              {recentActivity.map((item) => (
                <div key={item.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5">
                  <Activity className="w-4 h-4 text-accent shrink-0" />
                  <span className="text-sm text-white/70 flex-1">{item.message}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-48 flex items-center justify-center text-white/30 text-sm">
              No recent activity
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
