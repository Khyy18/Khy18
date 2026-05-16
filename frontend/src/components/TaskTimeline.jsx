import { useState, useEffect } from 'react'

/**
 * Вертикальная временная шкала активности
 * Отображает записи активности в хронологическом порядке
 */
export default function TaskTimeline() {
  const [activities, setActivities] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchActivity = async () => {
      try {
        const response = await fetch('/api/activity?limit=50')
        if (response.ok) {
          const data = await response.json()
          setActivities(data.items || [])
        }
      } catch (err) {
        console.error('Failed to fetch activity:', err)
        setError('Ошибка загрузки данных')
      } finally {
        setLoading(false)
      }
    }
    fetchActivity()
  }, [])

  // Цвета для агентов по id
  const agentColors = [
    'from-violet-500 to-purple-600',
    'from-blue-500 to-cyan-600',
    'from-emerald-500 to-teal-600',
    'from-orange-500 to-red-600',
    'from-pink-500 to-rose-600',
    'from-yellow-500 to-amber-600',
  ]

  const getColor = (agentId) => agentColors[(agentId - 1) % agentColors.length]

  const getInitials = (name) => {
    if (!name) return '?'
    return name
      .split(' ')
      .map((w) => w[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  const formatTime = (timestamp) => {
    if (!timestamp) return ''
    const date = new Date(timestamp)
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }

  if (loading) {
    return (
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
        <div className="text-center py-8 text-white/30 text-sm">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
        <h2 className="text-white/80 font-medium text-sm mb-4">Timeline</h2>
        <div className="text-center py-8 text-red-400/70 text-sm">{error}</div>
      </div>
    )
  }

  if (activities.length === 0) {
    return (
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
        <h2 className="text-white/80 font-medium text-sm mb-4">Timeline</h2>
        <div className="text-center py-8 text-white/30 text-sm">
          Нет активности
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
      <h2 className="text-white/80 font-medium text-sm mb-4">Timeline</h2>
      <div className="max-h-96 overflow-y-auto pr-2 space-y-0">
        {activities.map((item, index) => (
          <div key={item.id} className="relative flex gap-3 pb-4">
            {/* Вертикальная линия */}
            {index < activities.length - 1 && (
              <div className="absolute left-[15px] top-8 w-px h-full bg-white/10" />
            )}

            {/* Аватар агента */}
            <div className="shrink-0">
              <div
                className={`w-8 h-8 rounded-full bg-gradient-to-br ${getColor(item.agent_id)} flex items-center justify-center text-white font-semibold text-[10px]`}
              >
                {getInitials(item.agent_name)}
              </div>
            </div>

            {/* Контент */}
            <div className="flex-1 min-w-0 bg-white/5 rounded-xl px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-white/70 text-xs font-medium truncate">
                  {item.agent_name || `Agent #${item.agent_id}`}
                </span>
                <span className="text-white/30 text-[10px] shrink-0">
                  {formatTime(item.timestamp)}
                </span>
              </div>
              <p className="text-white/50 text-xs mt-0.5 truncate">
                {item.action_description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
