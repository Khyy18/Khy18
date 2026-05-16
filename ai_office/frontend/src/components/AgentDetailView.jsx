import { useState, useEffect } from 'react'
import { X } from 'lucide-react'

/**
 * Детальная панель агента (slide-in с правой стороны)
 * Показывает: имя, роль, статус, инструменты, активность, задачи
 */

// Маппинг инструментов агентов
const AGENT_TOOLS = {
  Alice: ['task_management', 'delegation', 'scheduling', 'communication'],
  Sam: ['code_generation', 'code_review', 'debugging', 'testing'],
  Max: ['ui_design', 'wireframing', 'prototyping', 'asset_generation'],
  Eva: ['data_analysis', 'reporting', 'forecasting', 'visualization'],
  Leo: ['test_execution', 'bug_tracking', 'automation', 'quality_metrics'],
  Nova: ['deployment', 'monitoring', 'ci_cd', 'infrastructure'],
  Iris: ['content_creation', 'social_media', 'seo_optimization', 'analytics'],
  Oscar: ['budgeting', 'invoicing', 'financial_analysis', 'expense_tracking'],
}

export default function AgentDetailView({ agent, onClose }) {
  const [activity, setActivity] = useState([])
  const [tasks, setTasks] = useState([])
  const [visible, setVisible] = useState(false)

  // Анимация появления
  useEffect(() => {
    requestAnimationFrame(() => setVisible(true))
  }, [])

  // Загрузка данных
  useEffect(() => {
    if (!agent) return

    const fetchData = async () => {
      try {
        const [actRes, taskRes] = await Promise.all([
          fetch(`/api/agents/${agent.id}/activity?limit=10`),
          fetch(`/api/agents/${agent.id}/tasks`),
        ])
        if (actRes.ok) {
          const actData = await actRes.json()
          setActivity(actData.items || [])
        }
        if (taskRes.ok) {
          const taskData = await taskRes.json()
          setTasks(taskData)
        }
      } catch (err) {
        // ignore
      }
    }
    fetchData()
  }, [agent])

  const handleClose = () => {
    setVisible(false)
    setTimeout(onClose, 200)
  }

  const tools = AGENT_TOOLS[agent.name] || []

  const statusColors = {
    idle: 'bg-gray-500',
    working: 'bg-green-500',
    busy: 'bg-green-500',
    typing: 'bg-yellow-500',
    processing: 'bg-blue-500',
  }

  const statusColor = statusColors[agent.status] || 'bg-gray-500'

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={handleClose}>
      <div
        className={`w-80 max-w-full h-full bg-background/95 backdrop-blur-xl border-l border-white/10 p-4 overflow-y-auto transition-transform duration-200 ${
          visible ? 'translate-x-0' : 'translate-x-full'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold text-base">{agent.name}</h2>
          <button
            onClick={handleClose}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 transition-colors"
          >
            <X className="w-4 h-4 text-white/70" />
          </button>
        </div>

        {/* Role & Status */}
        <div className="mb-4">
          <p className="text-white/50 text-sm">{agent.role}</p>
          <div className="flex items-center gap-2 mt-2">
            <span className={`w-2 h-2 rounded-full ${statusColor}`} />
            <span className="text-white/60 text-xs capitalize">{agent.status}</span>
          </div>
        </div>

        {/* Tools */}
        {tools.length > 0 && (
          <div className="mb-4">
            <h3 className="text-white/70 font-medium text-xs uppercase tracking-wider mb-2">
              Инструменты
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {tools.map((tool) => (
                <span
                  key={tool}
                  className="px-2 py-0.5 bg-white/5 border border-white/10 rounded-lg text-white/60 text-[10px]"
                >
                  {tool}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Activity */}
        <div className="mb-4">
          <h3 className="text-white/70 font-medium text-xs uppercase tracking-wider mb-2">
            Последняя активность
          </h3>
          {activity.length > 0 ? (
            <div className="space-y-2">
              {activity.map((item) => (
                <div
                  key={item.id}
                  className="bg-white/5 rounded-xl px-3 py-2"
                >
                  <p className="text-white/50 text-xs truncate">
                    {item.action_description}
                  </p>
                  <span className="text-white/30 text-[10px]">
                    {item.action_type}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-white/30 text-xs">Нет записей</p>
          )}
        </div>

        {/* Tasks */}
        <div>
          <h3 className="text-white/70 font-medium text-xs uppercase tracking-wider mb-2">
            Задачи
          </h3>
          {tasks.length > 0 ? (
            <div className="space-y-2">
              {tasks.map((task) => (
                <div
                  key={task.id}
                  className="bg-white/5 rounded-xl px-3 py-2"
                >
                  <p className="text-white/60 text-xs truncate">
                    {task.description}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-white/30 text-[10px] capitalize">
                      {task.status}
                    </span>
                    <span className="text-white/20 text-[10px]">
                      {task.priority}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-white/30 text-xs">Нет задач</p>
          )}
        </div>
      </div>
    </div>
  )
}
