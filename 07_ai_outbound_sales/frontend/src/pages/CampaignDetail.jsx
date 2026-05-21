import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Megaphone } from 'lucide-react'
import MetricCard from '../components/ui/MetricCard'
import StatusBadge from '../components/ui/StatusBadge'
import FunnelChart from '../components/ui/FunnelChart'
import DataTable from '../components/ui/DataTable'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import EmptyState from '../components/ui/EmptyState'
import { useApi } from '../hooks/useApi'

export default function CampaignDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [campaign, setCampaign] = useState(null)
  const [leads, setLeads] = useState([])
  const [funnel, setFunnel] = useState([])
  const [loading, setLoading] = useState(true)
  const { get } = useApi()

  useEffect(() => {
    const load = async () => {
      try {
        const [camp, leadsData] = await Promise.all([
          get(`/api/campaigns/${id}`),
          get(`/api/campaigns/${id}/leads`).catch(() => []),
        ])
        setCampaign(camp)
        setLeads(Array.isArray(leadsData) ? leadsData : leadsData?.items || [])

        if (camp?.funnel) {
          setFunnel(camp.funnel)
        } else {
          setFunnel([
            { name: 'Sent', value: camp?.sent_count || 0 },
            { name: 'Opened', value: camp?.opened_count || 0 },
            { name: 'Replied', value: camp?.replied_count || 0 },
            { name: 'Converted', value: camp?.converted_count || 0 },
          ])
        }
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [get, id])

  if (loading) return <LoadingSkeleton rows={4} />

  if (!campaign) {
    return <EmptyState icon={Megaphone} title="Campaign not found" action="Go Back" onAction={() => navigate('/campaigns')} />
  }

  const leadColumns = [
    { key: 'name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
  ]

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/campaigns')} className="p-2 rounded-lg hover:bg-white/10 transition-colors">
          <ArrowLeft className="w-5 h-5 text-white/70" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white">{campaign.name}</h1>
            <StatusBadge status={campaign.status} />
          </div>
          <p className="text-white/50 text-sm mt-1">{campaign.channel || 'Multi-channel'} campaign</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Total Leads" value={leads.length} />
        <MetricCard title="Reply Rate" value={`${campaign.reply_rate || 0}%`} />
        <MetricCard title="Meetings" value={campaign.meetings_booked || 0} />
      </div>

      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Campaign Funnel</h3>
        {funnel.some(f => f.value > 0) ? (
          <FunnelChart data={funnel} />
        ) : (
          <div className="h-48 flex items-center justify-center text-white/30 text-sm">No data yet</div>
        )}
      </div>

      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Leads in Campaign</h3>
        {leads.length > 0 ? (
          <DataTable columns={leadColumns} data={leads} onRowClick={(row) => navigate(`/leads/${row.id}`)} />
        ) : (
          <div className="text-center py-8 text-white/30 text-sm">No leads in this campaign</div>
        )}
      </div>
    </div>
  )
}
