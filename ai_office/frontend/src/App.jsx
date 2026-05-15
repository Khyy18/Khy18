import { useState, useEffect } from 'react'
import { Users, ListTodo, Activity } from 'lucide-react'
import AgentCard from './components/AgentCard'
import TaskCard from './components/TaskCard'
import ActivityLog from './components/ActivityLog'
import SystemStatus from './components/SystemStatus'
import { useApi } from './hooks/useApi'

/**
 * Главный компонент AI Office Mini App
 * Три таба: Agents, Tasks, Activity
 * Интеграция с Telegram Web App SDK
 */
export default function App() {
  const [activeTab, setActiveTab] = useState('agents')

  // Инициализация Telegram Web App
  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready()
      window.Telegram.WebApp.expand()
    }
  }, [])

  // Polling данных с API
  const { data: agents } = useApi('agents', 3000)
  const { data: tasks } = useApi('tasks', 3000)
  const { data: activity } = useApi('activity', 3000)
  const { data: systemStatus } = useApi('status', 5000)

  // Конфигурация табов
  const tabs = [
    { id: 'agents', label: 'Agents', icon: Users },
    { id: 'tasks', label: 'Tasks', icon: ListTodo },
    { id: 'activity', label: 'Activity', icon: Activity },
  ]

  return (
    <div className="min-h-screen bg-background text-white flex flex-col">
      {/* Хедер */}
      <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-xl border-b border-white/5 px-4 py-3">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight">AI Office</h1>
          {/* Индикатор статуса системы */}
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-status-pulse" />
            <span className="text-white/50 text-xs">Online</span>
          </div>
        </div>
      </header>

      {/* Основной контент */}
      <main className="flex-1 overflow-y-auto px-4 py-4 pb-20">
        {/* Системный статус - всегда виден */}
        <SystemStatus status={systemStatus} />

        {/* Контент табов */}
        <div className="mt-4 space-y-3">
          {activeTab === 'agents' && (
            <div className="space-y-3">
              {agents && agents.length > 0 ? (
                agents.map((agent) => (
                  <AgentCard key={agent.id || agent.name} agent={agent} />
                ))
              ) : (
                <div className="text-center py-8 text-white/30 text-sm">
                  Loading agents...
                </div>
              )}
            </div>
          )}

          {activeTab === 'tasks' && (
            <div className="space-y-3">
              {tasks && tasks.length > 0 ? (
                tasks.map((task) => (
                  <TaskCard key={task.id} task={task} />
                ))
              ) : (
                <div className="text-center py-8 text-white/30 text-sm">
                  No tasks yet
                </div>
              )}
            </div>
          )}

          {activeTab === 'activity' && (
            <ActivityLog activities={activity || []} />
          )}
        </div>
      </main>

      {/* Нижний таб-бар */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 bg-background/90 backdrop-blur-xl border-t border-white/5">
        <div className="flex items-center justify-around py-2 px-4">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex flex-col items-center gap-0.5 px-4 py-1.5 rounded-xl transition-all ${
                  isActive
                    ? 'text-accent'
                    : 'text-white/40 hover:text-white/60'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="text-[10px] font-medium">{tab.label}</span>
              </button>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
