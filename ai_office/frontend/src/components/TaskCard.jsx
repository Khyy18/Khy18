import { Clock, ArrowRight } from 'lucide-react'

/**
 * Карточка задачи
 * Левая цветная полоска по приоритету: high=red, medium=yellow, low=green
 * Статус-бейдж: open=blue, in_progress=yellow, done=green
 */
export default function TaskCard({ task, isViewer = false }) {
  // Цвет левой полоски по приоритету
  const priorityColors = {
    high: 'bg-red-500',
    medium: 'bg-yellow-500',
    low: 'bg-green-500',
  }

  // Конфиг статусов
  const statusConfig = {
    open: { color: 'bg-blue-500/20 text-blue-400', label: 'Open' },
    in_progress: { color: 'bg-yellow-500/20 text-yellow-400', label: 'In Progress' },
    done: { color: 'bg-green-500/20 text-green-400', label: 'Done' },
  }

  const priority = priorityColors[task.priority] || priorityColors.low
  const status = statusConfig[task.status] || statusConfig.open

  // Расчет времени с момента создания
  const getTimeAgo = (timestamp) => {
    if (!timestamp) return ''
    const diff = Date.now() - new Date(timestamp).getTime()
    const minutes = Math.floor(diff / 60000)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden animate-slide-up">
      <div className="flex">
        {/* Цветная полоска приоритета */}
        <div className={`w-1 ${priority} shrink-0`} />

        <div className="flex-1 p-4">
          {/* Заголовок и статус */}
          <div className="flex items-start justify-between gap-2">
            <p className="text-white/90 text-sm font-medium leading-snug flex-1">
              {task.description}
            </p>
            <span className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium ${status.color}`}>
              {status.label}
            </span>
          </div>

          {/* Создатель -> Исполнитель */}
          <div className="flex items-center gap-1.5 mt-2 text-white/40 text-xs">
            <span>{task.creator || 'System'}</span>
            <ArrowRight className="w-3 h-3" />
            <span>{task.assigned_to || 'Unassigned'}</span>
          </div>

          {/* Время */}
          {task.created_at && (
            <div className="flex items-center gap-1 mt-2 text-white/30 text-[10px]">
              <Clock className="w-3 h-3" />
              <span>{getTimeAgo(task.created_at)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
