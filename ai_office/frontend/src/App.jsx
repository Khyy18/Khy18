import { useState, useEffect, useCallback } from 'react'
import { Users, ListTodo, Activity } from 'lucide-react'
import AgentCard from './components/AgentCard'
import TaskCard from './components/TaskCard'
import ActivityLog from './components/ActivityLog'
import SystemStatus from './components/SystemStatus'
import { ToastContainer, showToast } from './components/Toast'
import { useApi } from './hooks/useApi'
import { useWebSocket } from './hooks/useWebSocket'

/**
 * Главный компонент AI Office Mini App
 * Три таба: Agents, Tasks, Activity
 * Интеграция с Telegram Web App SDK
 */
export default function App() {
  const [activeTab, setActiveTab] = useState('agents')
  const [wsAgents, setWsAgents] = useState(null)
  const [wsTasks, setWsTasks] = useState(null)
  const [wsActivity, setWsActivity] = useState(null)

  // Инициализация Telegram Web App
  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready()
      window.Telegram.WebApp.expand()
    }
  }, [])

  // WebSocket connection state (declared early for polling control)
  const [wsConnected, setWsConnected] = useState(false)

  // Polling данных с API (initial load + fallback, paused when WS connected)
  const { data: apiAgents } = useApi('agents', 3000, wsConnected)
  const { data: apiTasks } = useApi('tasks', 3000, wsConnected)
  const { data: apiActivity } = useApi('activity', 3000, wsConnected)
  const { data: systemStatus } = useApi('status', 5000)

  // Initialize WS state from API data
  useEffect(() => {
    if (apiAgents && !wsAgents) setWsAgents(apiAgents)
  }, [apiAgents, wsAgents])

  useEffect(() => {
    if (apiTasks && !wsTasks) setWsTasks(apiTasks)
  }, [apiTasks, wsTasks])

  useEffect(() => {
    if (apiActivity && !wsActivity) setWsActivity(apiActivity)
  }, [apiActivity, wsActivity])

  // WebSocket event handlers
  const wsHandlers = {
    new_task: useCallback((data) => {
      setWsTasks(prev => prev ? [data, ...prev] : [data])
      showToast('Новая задача создана', 'info')
    }, []),

    task_updated: useCallback((data) => {
      setWsTasks(prev => {
        if (!prev) return prev
        return prev.map(t => t.id === data.id ? { ...t, ...data } : t)
      })
      if (data.status === 'done') {
        showToast('Задача завершена', 'success')
      }
    }, []),

    agent_status_changed: useCallback((data) => {
      setWsAgents(prev => {
        if (!prev) return prev
        return prev.map(a => a.id === data.id ? { ...a, ...data } : a)
      })
    }, []),

    new_activity: useCallback((data) => {
      setWsActivity(prev => prev ? [data, ...prev] : [data])
    }, []),
  }

  const { connected, error: wsError } = useWebSocket('/api/ws', wsHandlers)

  // Sync WS connection status for polling control
  useEffect(() => {
    setWsConnected(connected)
  }, [connected])

  // Use WS state if available, otherwise fall back to API polling data
  const agents = wsAgents || apiAgents
  const tasks = wsTasks || apiTasks
  const activity = wsActivity || apiActivity

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
            <span className={`w-2 h-2 rounded-full ${
              connected ? 'bg-green-500 animate-status-pulse' : wsError ? 'bg-red-500' : 'bg-yellow-500 animate-status-pulse'
            }`} />
            <span className="text-white/50 text-xs">
              {connected ? 'Online' : wsError ? 'Offline' : 'Connecting...'}
            </span>
          </div>
        </div>
      </header>

      {/* Основной контент */}
      <main className="flex-1 overflow-y-auto px-4 py-4 pb-20">
        {/* Системный статус - всегда виден */}
        <SystemStatus status={systemStatus} />

        {/* Контент табов */}
        <div className="mt-4 space-y-3">
          <div key={activeTab} className="animate-tab-transition">
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
        </div>
      </main>

      {/* Toast notifications */}
      <ToastContainer />

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
