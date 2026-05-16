import { MessageSquare, CheckCircle, Play, AlertCircle, Zap } from 'lucide-react'

/**
 * Лента активности - timeline с точками и линиями
 * Каждая запись: иконка (по типу действия), описание, агент, timestamp
 */
export default function ActivityLog({ activities = [] }) {
  // Иконки по типу действия
  const actionIcons = {
    message: MessageSquare,
    task_completed: CheckCircle,
    task_started: Play,
    error: AlertCircle,
    default: Zap,
  }

  // Цвета по типу действия
  const actionColors = {
    message: 'text-blue-400 bg-blue-500/20',
    task_completed: 'text-green-400 bg-green-500/20',
    task_started: 'text-yellow-400 bg-yellow-500/20',
    error: 'text-red-400 bg-red-500/20',
    default: 'text-purple-400 bg-purple-500/20',
  }

  // Относительное время
  const getRelativeTime = (timestamp) => {
    if (!timestamp) return ''
    const diff = Date.now() - new Date(timestamp).getTime()
    const seconds = Math.floor(diff / 1000)
    if (seconds < 60) return 'just now'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  if (activities.length === 0) {
    return (
      <div className="text-center py-8 text-white/30 text-sm">
        No activity yet
      </div>
    )
  }

  return (
    <div className="relative">
      {/* Вертикальная линия таймлайна */}
      <div className="absolute left-4 top-0 bottom-0 w-px bg-white/10" />

      <div className="space-y-1">
        {activities.map((activity, index) => {
          const Icon = actionIcons[activity.action_type] || actionIcons.default
          const colorClass = actionColors[activity.action_type] || actionColors.default

          return (
            <div
              key={activity.id || index}
              className="relative flex items-start gap-3 pl-2 py-2 animate-fade-in"
            >
              {/* Точка на таймлайне */}
              <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 z-10 ${colorClass}`}>
                <Icon className="w-3 h-3" />
              </div>

              {/* Контент */}
              <div className="flex-1 min-w-0">
                <p className="text-white/80 text-xs leading-relaxed">
                  {activity.description}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  {activity.agent_name && (
                    <span className="text-white/40 text-[10px] font-medium">
                      {activity.agent_name}
                    </span>
                  )}
                  <span className="text-white/20 text-[10px]">
                    {getRelativeTime(activity.timestamp)}
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
