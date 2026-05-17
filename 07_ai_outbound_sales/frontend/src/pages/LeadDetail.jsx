import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Mail, Building, Briefcase } from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import EmptyState from '../components/ui/EmptyState'
import { useApi } from '../hooks/useApi'

export default function LeadDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [lead, setLead] = useState(null)
  const [loading, setLoading] = useState(true)
  const { get } = useApi()

  useEffect(() => {
    get(`/api/leads/${id}`)
      .then(data => setLead(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [get, id])

  if (loading) return <LoadingSkeleton rows={4} />

  if (!lead) {
    return <EmptyState icon={Users} title="Lead not found" action="Go Back" onAction={() => navigate('/leads')} />
  }

  const activities = lead.activities || lead.messages || []

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/leads')} className="p-2 rounded-lg hover:bg-white/10 transition-colors">
          <ArrowLeft className="w-5 h-5 text-white/70" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white">{lead.name || lead.email}</h1>
            <StatusBadge status={lead.status || 'new'} />
          </div>
        </div>
      </div>

      {/* Contact Info */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Contact Information</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex items-center gap-3">
            <Mail className="w-4 h-4 text-white/30" />
            <span className="text-sm text-white/80">{lead.email || 'No email'}</span>
          </div>
          <div className="flex items-center gap-3">
            <Building className="w-4 h-4 text-white/30" />
            <span className="text-sm text-white/80">{lead.company || 'No company'}</span>
          </div>
          <div className="flex items-center gap-3">
            <Briefcase className="w-4 h-4 text-white/30" />
            <span className="text-sm text-white/80">{lead.title || 'No title'}</span>
          </div>
        </div>
      </div>

      {/* Activity Timeline */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Activity Timeline</h3>
        {activities.length > 0 ? (
          <div className="space-y-3">
            {activities.map((act, i) => (
              <div key={i} className="flex gap-3 p-3 bg-white/5 rounded-lg">
                <div className="w-2 h-2 rounded-full bg-accent mt-2 shrink-0" />
                <div className="flex-1">
                  <p className="text-sm text-white/80">{act.message || act.content || act.type}</p>
                  {act.timestamp && <span className="text-xs text-white/40">{act.timestamp}</span>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-white/30 text-sm">No activity recorded yet</div>
        )}
      </div>

      {/* Conversation History */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Conversation History</h3>
        {lead.conversations && lead.conversations.length > 0 ? (
          <div className="space-y-3">
            {lead.conversations.map((msg, i) => (
              <div key={i} className={`p-3 rounded-lg ${msg.direction === 'outbound' ? 'bg-accent/10 border border-accent/20' : 'bg-white/5'}`}>
                <div className="flex justify-between mb-1">
                  <span className="text-xs text-white/50">{msg.direction === 'outbound' ? 'Sent' : 'Received'}</span>
                  {msg.sent_at && <span className="text-xs text-white/30">{msg.sent_at}</span>}
                </div>
                <p className="text-sm text-white/80">{msg.content || msg.body}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-white/30 text-sm">No conversations yet</div>
        )}
      </div>
    </div>
  )
}
