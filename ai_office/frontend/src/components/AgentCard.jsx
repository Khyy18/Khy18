import { Activity, Cpu, Pause } from 'lucide-react'

/**
 * Карточка агента с glass-morphism эффектом
 * Отображает: аватар, имя, роль, статус, текущую задачу
 */
export default function AgentCard({ agent }) {
  // Получаем инициалы из имени агента
  const initials = agent.name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)

  // Конфиг статусов: цвет, иконка, анимация
  const statusConfig = {
    idle: {
      color: 'bg-gray-500',
      label: 'Idle',
      icon: Pause,
      animate: '',
    },
    typing: {
      color: 'bg-yellow-500',
      label: 'Typing',
      icon: Activity,
      animate: 'animate-status-pulse',
    },
    working: {
      color: 'bg-green-500',
      label: 'Working',
      icon: Cpu,
      animate: 'animate-status-pulse',
    },
  }

  const status = statusConfig[agent.status] || statusConfig.idle
  const StatusIcon = status.icon

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 animate-slide-up">
      <div className="flex items-center gap-3">
        {/* Аватар с градиентом */}
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-accent to-secondary flex items-center justify-center text-white font-semibold text-sm shrink-0">
          {initials}
        </div>

        {/* Информация об агенте */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-white font-medium text-sm truncate">{agent.name}</h3>
            {/* Бейдж статуса */}
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${status.color}/20 text-white/80`}>
              <span className={`w-1.5 h-1.5 rounded-full ${status.color} ${status.animate}`}></span>
              {status.label}
            </span>
          </div>
          <p className="text-white/50 text-xs mt-0.5">{agent.role}</p>
        </div>
      </div>

      {/* Текущая задача */}
      {agent.current_task && (
        <div className="mt-3 pl-15">
          <div className="bg-white/5 rounded-xl px-3 py-2">
            <p className="text-white/60 text-xs truncate">
              <StatusIcon className="inline w-3 h-3 mr-1 opacity-50" />
              {agent.current_task}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
