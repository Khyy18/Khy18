import { useState, useEffect } from 'react'
import { Plug, Plus, Trash2, Webhook, Calendar, Database } from 'lucide-react'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import { useApi } from '../hooks/useApi'
import { useToast } from '../components/ui/Toast'

export default function Integrations() {
  const [webhooks, setWebhooks] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ url: '', events: '' })
  const [creating, setCreating] = useState(false)
  const { get, post, del } = useApi()
  const toast = useToast()

  useEffect(() => {
    get('/api/integrations/webhooks')
      .then(data => setWebhooks(Array.isArray(data) ? data : data?.items || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [get])

  const handleCreate = async () => {
    setCreating(true)
    try {
      const events = form.events.split(',').map(e => e.trim()).filter(Boolean)
      const created = await post('/api/integrations/webhooks', { url: form.url, events })
      setWebhooks(prev => [created, ...prev])
      setShowCreate(false)
      setForm({ url: '', events: '' })
      toast('Webhook created', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await del(`/api/integrations/webhooks/${id}`)
      setWebhooks(prev => prev.filter(w => w.id !== id))
      toast('Webhook deleted', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  if (loading) return <LoadingSkeleton rows={4} />

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold text-white">Integrations</h1>
        <p className="text-white/50 text-sm mt-1">Connect your tools and manage webhooks</p>
      </div>

      {/* Connection Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center">
              <Database className="w-5 h-5 text-accent" />
            </div>
            <div>
              <h4 className="font-medium text-white">CRM</h4>
              <p className="text-xs text-white/40">Sync leads with your CRM</p>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-white/30">Not connected</span>
            <button className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs transition-colors">
              Connect
            </button>
          </div>
        </div>

        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-secondary/20 flex items-center justify-center">
              <Calendar className="w-5 h-5 text-secondary" />
            </div>
            <div>
              <h4 className="font-medium text-white">Calendar</h4>
              <p className="text-xs text-white/40">Auto-schedule meetings</p>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-white/30">Not connected</span>
            <button className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs transition-colors">
              Connect
            </button>
          </div>
        </div>
      </div>

      {/* Webhooks */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-white/70">Webhooks</h3>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1 px-3 py-1.5 bg-accent hover:bg-accent/80 text-white rounded-lg text-xs font-medium transition-colors"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>

        {webhooks.length === 0 ? (
          <EmptyState
            icon={Webhook}
            title="No webhooks"
            message="Create webhooks to receive event notifications."
            action="Create Webhook"
            onAction={() => setShowCreate(true)}
          />
        ) : (
          <div className="space-y-2">
            {webhooks.map((wh) => (
              <div key={wh.id} className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white/80 truncate">{wh.url}</p>
                  <p className="text-xs text-white/40 mt-0.5">
                    Events: {Array.isArray(wh.events) ? wh.events.join(', ') : wh.events || 'all'}
                  </p>
                </div>
                <button
                  onClick={() => handleDelete(wh.id)}
                  className="p-2 hover:bg-red-500/20 rounded-lg transition-colors ml-2"
                >
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="New Webhook">
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-white/70 mb-1">Webhook URL</label>
            <input
              value={form.url}
              onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              placeholder="https://your-app.com/webhook"
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Events (comma-separated)</label>
            <input
              value={form.events}
              onChange={e => setForm(f => ({ ...f, events: e.target.value }))}
              placeholder="lead.created, campaign.completed"
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
          <button
            onClick={handleCreate}
            disabled={!form.url || creating}
            className="w-full py-2.5 bg-accent hover:bg-accent/80 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {creating ? 'Creating...' : 'Create Webhook'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
