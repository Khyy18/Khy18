import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Phone, Plus, FileText } from 'lucide-react'
import DataTable from '../components/ui/DataTable'
import StatusBadge from '../components/ui/StatusBadge'
import MetricCard from '../components/ui/MetricCard'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import { useApi } from '../hooks/useApi'
import { useToast } from '../components/ui/Toast'

export default function Voice() {
  const [calls, setCalls] = useState([])
  const [scripts, setScripts] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('calls')
  const [showScriptModal, setShowScriptModal] = useState(false)
  const [scriptForm, setScriptForm] = useState({ name: '', content: '' })
  const [creating, setCreating] = useState(false)
  const { get, post } = useApi()
  const navigate = useNavigate()
  const toast = useToast()

  useEffect(() => {
    const load = async () => {
      try {
        const [callsData, scriptsData] = await Promise.all([
          get('/api/voice/calls').catch(() => []),
          get('/api/voice/scripts').catch(() => []),
        ])
        setCalls(Array.isArray(callsData) ? callsData : callsData?.items || [])
        setScripts(Array.isArray(scriptsData) ? scriptsData : scriptsData?.items || [])
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [get])

  const handleCreateScript = async () => {
    setCreating(true)
    try {
      const created = await post('/api/voice/scripts', scriptForm)
      setScripts(prev => [created, ...prev])
      setShowScriptModal(false)
      setScriptForm({ name: '', content: '' })
      toast('Script created', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setCreating(false)
    }
  }

  const totalCalls = calls.length
  const completedCalls = calls.filter(c => c.status === 'completed').length
  const avgDuration = totalCalls > 0
    ? Math.round(calls.reduce((sum, c) => sum + (c.duration || 0), 0) / totalCalls)
    : 0

  const callColumns = [
    { key: 'lead_name', label: 'Lead', render: (v, row) => v || row.phone || 'Unknown' },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    { key: 'outcome', label: 'Outcome' },
    { key: 'duration', label: 'Duration', render: (v) => v ? `${v}s` : '-' },
  ]

  const scriptColumns = [
    { key: 'name', label: 'Script Name' },
    { key: 'created_at', label: 'Created' },
  ]

  if (loading) return <LoadingSkeleton rows={5} />

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold text-white">Voice</h1>
        <p className="text-white/50 text-sm mt-1">Call logs and scripts management</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Total Calls" value={totalCalls} icon={Phone} />
        <MetricCard title="Completed" value={completedCalls} />
        <MetricCard title="Avg Duration" value={`${avgDuration}s`} />
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10 pb-0">
        <button
          onClick={() => setActiveTab('calls')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'calls' ? 'border-accent text-accent' : 'border-transparent text-white/50 hover:text-white/70'
          }`}
        >
          Call Log
        </button>
        <button
          onClick={() => setActiveTab('scripts')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'scripts' ? 'border-accent text-accent' : 'border-transparent text-white/50 hover:text-white/70'
          }`}
        >
          Scripts
        </button>
      </div>

      {activeTab === 'calls' && (
        <>
          {calls.length === 0 ? (
            <EmptyState icon={Phone} title="No calls yet" message="Voice calls will appear here once initiated." />
          ) : (
            <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
              <DataTable columns={callColumns} data={calls} onRowClick={(row) => navigate(`/voice/${row.id}`)} />
            </div>
          )}
        </>
      )}

      {activeTab === 'scripts' && (
        <>
          <div className="flex justify-end">
            <button
              onClick={() => setShowScriptModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/80 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" /> New Script
            </button>
          </div>

          {scripts.length === 0 ? (
            <EmptyState icon={FileText} title="No scripts yet" message="Create call scripts for your voice campaigns." action="Create Script" onAction={() => setShowScriptModal(true)} />
          ) : (
            <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
              <DataTable columns={scriptColumns} data={scripts} />
            </div>
          )}
        </>
      )}

      <Modal isOpen={showScriptModal} onClose={() => setShowScriptModal(false)} title="New Script">
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-white/70 mb-1">Script Name</label>
            <input
              value={scriptForm.name}
              onChange={e => setScriptForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Cold call intro"
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Script Content</label>
            <textarea
              value={scriptForm.content}
              onChange={e => setScriptForm(f => ({ ...f, content: e.target.value }))}
              placeholder="Hi, this is..."
              rows={6}
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50 resize-none"
            />
          </div>
          <button
            onClick={handleCreateScript}
            disabled={!scriptForm.name || creating}
            className="w-full py-2.5 bg-accent hover:bg-accent/80 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {creating ? 'Creating...' : 'Create Script'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
