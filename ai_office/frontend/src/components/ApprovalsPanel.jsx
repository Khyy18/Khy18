import { useState, useCallback } from 'react'
import { ShieldCheck, Check, X, Clock } from 'lucide-react'
import { useApi } from '../hooks/useApi'

/**
 * Панель одобрений - показывает запросы на одобрение действий агентов
 * Pending: желтый, Approved: зеленый, Rejected: красный
 */
export default function ApprovalsPanel() {
  const { data, loading } = useApi('approvals', 5000)
  const [acting, setActing] = useState({})

  const handleResolve = useCallback(async (id, decision) => {
    setActing(prev => ({ ...prev, [id]: true }))
    try {
      await fetch(`/api/approvals/${id}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      })
    } catch (e) { /* ignore */ }
    setActing(prev => ({ ...prev, [id]: false }))
  }, [])

  if (loading || !data) {
    return (
      <div className="space-y-3">
        <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
          <ShieldCheck className="w-4 h-4" />
          Одобрения
        </h3>
        <div className="text-white/30 text-sm text-center py-6">Загрузка...</div>
      </div>
    )
  }

  const items = Array.isArray(data) ? data : (data.items || [])

  const statusBadge = (status) => {
    const map = {
      pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
      approved: 'bg-green-500/20 text-green-400 border-green-500/30',
      rejected: 'bg-red-500/20 text-red-400 border-red-500/30',
    }
    const labels = { pending: 'Ожидает', approved: 'Одобрено', rejected: 'Отклонено' }
    return (
      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${map[status] || map.pending}`}>
        {labels[status] || status}
      </span>
    )
  }

  return (
    <div className="space-y-3">
      <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
        <ShieldCheck className="w-4 h-4" />
        Одобрения
      </h3>

      {items.length === 0 ? (
        <div className="text-white/30 text-sm text-center py-6">
          Нет запросов на одобрение
        </div>
      ) : (
        items.map((item) => (
          <div key={item.id} className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-white text-sm font-medium">{item.agent_name}</span>
              {statusBadge(item.status)}
            </div>

            <div className="space-y-1">
              <span className="text-accent text-xs font-medium">{item.action_type}</span>
              <p className="text-white/60 text-xs">{item.description}</p>
            </div>

            <div className="flex items-center gap-2 text-white/30 text-[10px]">
              <Clock className="w-3 h-3" />
              <span>{item.created_at ? new Date(item.created_at).toLocaleString('ru-RU') : ''}</span>
            </div>

            {item.status === 'pending' && (
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => handleResolve(item.id, 'approved')}
                  disabled={acting[item.id]}
                  className="flex items-center gap-1 px-3 py-1.5 bg-green-500/20 text-green-400 rounded-lg text-xs font-medium hover:bg-green-500/30 transition-all disabled:opacity-50"
                >
                  <Check className="w-3.5 h-3.5" />
                  Одобрить
                </button>
                <button
                  onClick={() => handleResolve(item.id, 'rejected')}
                  disabled={acting[item.id]}
                  className="flex items-center gap-1 px-3 py-1.5 bg-red-500/20 text-red-400 rounded-lg text-xs font-medium hover:bg-red-500/30 transition-all disabled:opacity-50"
                >
                  <X className="w-3.5 h-3.5" />
                  Отклонить
                </button>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  )
}
