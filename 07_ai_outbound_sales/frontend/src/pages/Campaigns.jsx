import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Megaphone } from 'lucide-react'
import DataTable from '../components/ui/DataTable'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import { useApi } from '../hooks/useApi'
import { useToast } from '../components/ui/Toast'

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', channel: 'email', status: 'draft' })
  const [creating, setCreating] = useState(false)
  const { get, post } = useApi()
  const navigate = useNavigate()
  const toast = useToast()

  useEffect(() => {
    get('/api/campaigns')
      .then(data => setCampaigns(Array.isArray(data) ? data : data?.items || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [get])

  const handleCreate = async () => {
    setCreating(true)
    try {
      const created = await post('/api/campaigns', form)
      setCampaigns(prev => [created, ...prev])
      setShowCreate(false)
      setForm({ name: '', channel: 'email', status: 'draft' })
      toast('Campaign created', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setCreating(false)
    }
  }

  const columns = [
    { key: 'name', label: 'Name' },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    { key: 'channel', label: 'Channel' },
    { key: 'leads_count', label: 'Leads' },
    { key: 'reply_rate', label: 'Reply Rate', render: (v) => v != null ? `${v}%` : '-' },
  ]

  if (loading) return <LoadingSkeleton rows={5} />

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Campaigns</h1>
          <p className="text-white/50 text-sm mt-1">Manage your outbound campaigns</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/80 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" /> New Campaign
        </button>
      </div>

      {campaigns.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="No campaigns yet"
          message="Create your first outbound campaign to start reaching prospects."
          action="Create Campaign"
          onAction={() => setShowCreate(true)}
        />
      ) : (
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <DataTable
            columns={columns}
            data={campaigns}
            onRowClick={(row) => navigate(`/campaigns/${row.id}`)}
          />
        </div>
      )}

      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="New Campaign">
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-white/70 mb-1">Campaign Name</label>
            <input
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Q1 Outreach"
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Channel</label>
            <select
              value={form.channel}
              onChange={e => setForm(f => ({ ...f, channel: e.target.value }))}
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-accent/50"
            >
              <option value="email" className="bg-card">Email</option>
              <option value="linkedin" className="bg-card">LinkedIn</option>
              <option value="voice" className="bg-card">Voice</option>
              <option value="multi" className="bg-card">Multi-channel</option>
            </select>
          </div>
          <button
            onClick={handleCreate}
            disabled={!form.name || creating}
            className="w-full py-2.5 bg-accent hover:bg-accent/80 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {creating ? 'Creating...' : 'Create Campaign'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
