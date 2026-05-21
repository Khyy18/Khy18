import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Phone, Clock, User } from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import EmptyState from '../components/ui/EmptyState'
import { useApi } from '../hooks/useApi'

export default function VoiceDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [call, setCall] = useState(null)
  const [loading, setLoading] = useState(true)
  const { get } = useApi()

  useEffect(() => {
    get(`/api/voice/calls/${id}`)
      .then(data => setCall(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [get, id])

  if (loading) return <LoadingSkeleton rows={4} />

  if (!call) {
    return <EmptyState icon={Phone} title="Call not found" action="Go Back" onAction={() => navigate('/voice')} />
  }

  const transcript = call.transcript || []

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/voice')} className="p-2 rounded-lg hover:bg-white/10 transition-colors">
          <ArrowLeft className="w-5 h-5 text-white/70" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white">Call Details</h1>
            <StatusBadge status={call.status} />
          </div>
        </div>
      </div>

      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Call Info</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="flex items-center gap-3">
            <User className="w-4 h-4 text-white/30" />
            <div>
              <p className="text-xs text-white/40">Lead</p>
              <p className="text-sm text-white/80">{call.lead_name || call.phone || 'Unknown'}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Clock className="w-4 h-4 text-white/30" />
            <div>
              <p className="text-xs text-white/40">Duration</p>
              <p className="text-sm text-white/80">{call.duration ? `${call.duration}s` : 'N/A'}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Phone className="w-4 h-4 text-white/30" />
            <div>
              <p className="text-xs text-white/40">Outcome</p>
              <p className="text-sm text-white/80">{call.outcome || 'N/A'}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <h3 className="text-sm font-medium text-white/70 mb-4">Transcript</h3>
        {transcript.length > 0 ? (
          <div className="space-y-3">
            {transcript.map((line, i) => (
              <div key={i} className={`p-3 rounded-lg ${line.speaker === 'agent' ? 'bg-accent/10 border border-accent/20 ml-4' : 'bg-white/5 mr-4'}`}>
                <span className="text-xs text-white/40 block mb-1">{line.speaker || 'Speaker'}</span>
                <p className="text-sm text-white/80">{line.text || line.content}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-white/30 text-sm">No transcript available</div>
        )}
      </div>
    </div>
  )
}
