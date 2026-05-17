import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { BarChart3 } from 'lucide-react'
import FunnelChart from '../components/ui/FunnelChart'
import MetricCard from '../components/ui/MetricCard'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import EmptyState from '../components/ui/EmptyState'
import { useApi } from '../hooks/useApi'

export default function Analytics() {
  const [funnel, setFunnel] = useState([])
  const [channelPerformance, setChannelPerformance] = useState([])
  const [conversion, setConversion] = useState(null)
  const [loading, setLoading] = useState(true)
  const { get } = useApi()

  useEffect(() => {
    const load = async () => {
      try {
        const [funnelData, channelData, convData] = await Promise.all([
          get('/api/analytics/funnel').catch(() => null),
          get('/api/analytics/channel-performance').catch(() => null),
          get('/api/analytics/conversion').catch(() => null),
        ])

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

        if (channelData) {
          const channels = Array.isArray(channelData) ? channelData : channelData.channels || []
          setChannelPerformance(channels)
        }

        if (convData) setConversion(convData)
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [get])

  if (loading) return <LoadingSkeleton rows={5} />

  const hasData = funnel.length > 0 || channelPerformance.length > 0 || conversion

  if (!hasData) {
    return (
      <div className="space-y-6 animate-slide-up">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics</h1>
          <p className="text-white/50 text-sm mt-1">Track your outbound performance</p>
        </div>
        <EmptyState icon={BarChart3} title="No analytics data yet" message="Start campaigns to see performance analytics." />
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold text-white">Analytics</h1>
        <p className="text-white/50 text-sm mt-1">Track your outbound performance</p>
      </div>

      {conversion && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <MetricCard
            title="Overall Conversion"
            value={`${conversion.overall_rate || conversion.rate || 0}%`}
            delta={conversion.delta}
          />
          <MetricCard
            title="Leads Converted"
            value={conversion.converted || 0}
          />
          <MetricCard
            title="Avg Days to Convert"
            value={conversion.avg_days || 'N/A'}
          />
        </div>
      )}

      {/* Funnel */}
      {funnel.length > 0 && (
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-4">Outreach Funnel</h3>
          <FunnelChart data={funnel} />
        </div>
      )}

      {/* Channel Performance */}
      {channelPerformance.length > 0 && (
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-4">Channel Performance</h3>
          <div className="w-full h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={channelPerformance} margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
                <XAxis dataKey="channel" tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }} />
                <Legend wrapperStyle={{ color: 'rgba(255,255,255,0.5)' }} />
                <Bar dataKey="sent" name="Sent" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="replied" name="Replied" fill="#a855f7" radius={[4, 4, 0, 0]} />
                <Bar dataKey="converted" name="Converted" fill="#22c55e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Conversion Table */}
      {conversion?.periods && (
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-4">Period-over-Period</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10">
                <th className="px-3 py-2 text-left text-white/50">Period</th>
                <th className="px-3 py-2 text-left text-white/50">Conversion Rate</th>
                <th className="px-3 py-2 text-left text-white/50">Change</th>
              </tr>
            </thead>
            <tbody>
              {conversion.periods.map((p, i) => (
                <tr key={i} className="border-b border-white/5">
                  <td className="px-3 py-2.5 text-white/80">{p.period}</td>
                  <td className="px-3 py-2.5 text-white/80">{p.rate}%</td>
                  <td className={`px-3 py-2.5 ${p.change > 0 ? 'text-green-400' : p.change < 0 ? 'text-red-400' : 'text-white/40'}`}>
                    {p.change > 0 ? '+' : ''}{p.change || 0}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
