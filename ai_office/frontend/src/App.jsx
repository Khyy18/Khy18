import { useState, useEffect, useCallback, useRef } from 'react'
import { Users, ListTodo, Activity, GitBranch, Clock, Settings, BarChart3, UserPlus } from 'lucide-react'
import AgentCard from './components/AgentCard'
import TaskCard from './components/TaskCard'
import ActivityLog from './components/ActivityLog'
import Dashboard from './components/Dashboard'
import AgentGraph from './components/AgentGraph'
import TaskTimeline from './components/TaskTimeline'
import KanbanBoard from './components/KanbanBoard'
import AgentDetailView from './components/AgentDetailView'
import AdminPanel from './components/AdminPanel'
import AnalyticsTab from './components/AnalyticsTab'
import Skeleton from './components/Skeleton'
import InviteSection from './components/InviteSection'
import SubscriptionBadge from './components/SubscriptionBadge'
import PublicDemo from './components/PublicDemo'
import { ToastContainer, showToast } from './components/Toast'
import { useApi } from './hooks/useApi'
import { useWebSocket } from './hooks/useWebSocket'

/**
 * Главный компонент AI Office Mini App
 * Пять табов: Agents, Tasks, Activity, Graph, Timeline
 * Интеграция с Telegram Web App SDK
 */
export default function App() {
  const [activeTab, setActiveTab] = useState('agents')
  const [wsAgents, setWsAgents] = useState(null)
  const [wsTasks, setWsTasks] = useState(null)
  const [wsActivity, setWsActivity] = useState(null)
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [userRole, setUserRole] = useState('viewer')
  const [streamingMessages, setStreamingMessages] = useState({})
  const [taskView, setTaskView] = useState('kanban')
  const [pullDistance, setPullDistance] = useState(0)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [subscriptionTier, setSubscriptionTier] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(true)
  const touchStartY = useRef(0)
  const mainRef = useRef(null)

  // Агенты, доступные бесплатно
  const FREE_AGENTS = ['Alice', 'Sam']

  // Инициализация Telegram Web App и определение роли
  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready()
      window.Telegram.WebApp.expand()
      setIsAuthenticated(true)
    } else {
      // Нет Telegram WebApp - проверяем через API
      setIsAuthenticated(false)
    }

    // Theme sync
    const applyTheme = () => {
      const colorScheme = window.Telegram?.WebApp?.colorScheme
      if (colorScheme === 'light') {
        document.documentElement.classList.add('light-theme')
      } else {
        document.documentElement.classList.remove('light-theme')
      }
    }
    applyTheme()
    window.Telegram?.WebApp?.onEvent?.('themeChanged', applyTheme)

    // Получаем роль из /api/status
    fetch('/api/status')
      .then(res => {
        if (!res.ok) throw new Error('not ok')
        return res.json()
      })
      .then(data => {
        if (data && data.user_role) {
          setUserRole(data.user_role)
        }
        setIsAuthenticated(true)
      })
      .catch(() => {
        if (!window.Telegram?.WebApp) {
          setIsAuthenticated(false)
        }
      })

    // Получаем статус подписки
    fetch('/api/subscription/status')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data && data.tier) {
          setSubscriptionTier(data.tier)
        }
      })
      .catch(() => {})
  }, [])

  // Определяем, является ли пользователь viewer (только чтение)
  const isViewer = userRole === 'viewer'

  // WebSocket connection state (declared early for polling control)
  const [wsConnected, setWsConnected] = useState(false)

  // Polling данных с API (initial load + fallback, paused when WS connected)
  const { data: apiAgents } = useApi('agents', 3000, wsConnected)
  const { data: apiTasks } = useApi('tasks', 3000, wsConnected)
  const { data: apiActivity } = useApi('activity', 3000, wsConnected)

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

  // Tab switch with haptic feedback
  const handleTabSwitch = useCallback((tabId) => {
    setActiveTab(tabId)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }, [])

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
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
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

    agent_typing_chunk: useCallback((data) => {
      setStreamingMessages(prev => {
        const existing = prev[data.message_id] || { text: '', agent: data.agent, isComplete: false }
        return {
          ...prev,
          [data.message_id]: {
            ...existing,
            text: existing.text + data.chunk,
          },
        }
      })
    }, []),

    agent_response_complete: useCallback((data) => {
      setStreamingMessages(prev => {
        const updated = {
          ...prev,
          [data.message_id]: {
            text: data.full_text,
            agent: data.agent,
            isComplete: true,
          },
        }
        // Clear completed message after 2 seconds
        setTimeout(() => {
          setStreamingMessages(current => {
            const { [data.message_id]: _, ...rest } = current
            return rest
          })
        }, 2000)
        return updated
      })
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

  // Pull-to-refresh handlers
  const handleTouchStart = useCallback((e) => {
    touchStartY.current = e.touches[0].clientY
  }, [])

  const handleTouchMove = useCallback((e) => {
    if (!mainRef.current || mainRef.current.scrollTop > 0) return
    const distance = e.touches[0].clientY - touchStartY.current
    if (distance > 0) {
      setPullDistance(Math.min(distance, 100))
    }
  }, [])

  const handleTouchEnd = useCallback(() => {
    if (pullDistance > 60) {
      setIsRefreshing(true)
      // Trigger re-fetch by resetting WS state
      setWsAgents(null)
      setWsTasks(null)
      setWsActivity(null)
      setTimeout(() => {
        setIsRefreshing(false)
      }, 1000)
    }
    setPullDistance(0)
  }, [pullDistance])

  // Конфигурация табов
  const tabs = [
    { id: 'agents', label: 'Agents', icon: Users },
    { id: 'tasks', label: 'Tasks', icon: ListTodo },
    { id: 'activity', label: 'Activity', icon: Activity },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'invite', label: 'Invite', icon: UserPlus },
    { id: 'graph', label: 'Graph', icon: GitBranch },
    { id: 'timeline', label: 'Timeline', icon: Clock },
    ...(userRole === 'owner' ? [{ id: 'admin', label: 'Admin', icon: Settings }] : []),
  ]

  // Показываем PublicDemo если нет аутентификации
  if (!isAuthenticated) {
    return <PublicDemo />
  }

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
        {/* Бейдж подписки */}
        <div className="mt-2">
          <SubscriptionBadge />
        </div>
      </header>

      {/* Pull-to-refresh indicator */}
      <div
        className="flex justify-center transition-all duration-200"
        style={{ height: pullDistance > 0 ? `${pullDistance * 0.4}px` : '0px', opacity: pullDistance > 30 ? 1 : 0 }}
      >
        <div className={`w-6 h-6 border-2 border-accent/50 border-t-accent rounded-full ${isRefreshing ? 'animate-spin' : ''}`} />
      </div>

      {/* Основной контент */}
      <main
        ref={mainRef}
        className="flex-1 overflow-y-auto px-4 py-4 pb-20"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Dashboard - замена SystemStatus */}
        <Dashboard />

        {/* Контент табов */}
        <div className="mt-4 space-y-3">
          <div key={activeTab} className="animate-tab-transition">
            {activeTab === 'agents' && (
              <div className="space-y-3">
                {agents && agents.length > 0 ? (
                  agents.map((agent) => (
                    <AgentCard
                      key={agent.id || agent.name}
                      agent={agent}
                      onSelect={setSelectedAgent}
                      isLocked={subscriptionTier === 'free' && !FREE_AGENTS.includes(agent.name)}
                      streamingText={
                        Object.values(streamingMessages).find(
                          m => m.agent === agent.name && !m.isComplete
                        ) || Object.values(streamingMessages).find(
                          m => m.agent === agent.name
                        ) || null
                      }
                    />
                  ))
                ) : (
                  <Skeleton type="card" count={4} />
                )}
              </div>
            )}

            {activeTab === 'tasks' && (
              <div className="space-y-3">
                {!isViewer && (
                  <div className="text-center py-2">
                    <span className="text-white/30 text-xs">
                      Создание задач через чат с агентами
                    </span>
                  </div>
                )}
                {isViewer && (
                  <div className="text-center py-2 px-3 bg-yellow-500/10 border border-yellow-500/20 rounded-xl">
                    <span className="text-yellow-400/70 text-xs">
                      Режим наблюдателя - только просмотр
                    </span>
                  </div>
                )}
                {/* Переключатель вида: Kanban / Timeline */}
                <div className="flex gap-2 mb-3">
                  <button
                    onClick={() => setTaskView('kanban')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      taskView === 'kanban'
                        ? 'bg-accent/20 text-accent'
                        : 'bg-white/5 text-white/40'
                    }`}
                  >
                    Kanban
                  </button>
                  <button
                    onClick={() => setTaskView('timeline')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      taskView === 'timeline'
                        ? 'bg-accent/20 text-accent'
                        : 'bg-white/5 text-white/40'
                    }`}
                  >
                    Timeline
                  </button>
                </div>
                {tasks === null ? (
                  <Skeleton type="kanban" count={3} />
                ) : taskView === 'kanban' ? (
                  <KanbanBoard tasks={tasks} isViewer={isViewer} />
                ) : (
                  <TaskTimeline />
                )}
              </div>
            )}

            {activeTab === 'activity' && (
              <ActivityLog activities={activity || []} />
            )}

            {activeTab === 'analytics' && (
              <AnalyticsTab />
            )}

            {activeTab === 'invite' && (
              <InviteSection />
            )}

            {activeTab === 'graph' && (
              <AgentGraph />
            )}

            {activeTab === 'timeline' && (
              <TaskTimeline />
            )}

            {activeTab === 'admin' && userRole === 'owner' && (
              <AdminPanel />
            )}
          </div>
        </div>
      </main>

      {/* AgentDetailView overlay */}
      {selectedAgent && (
        <AgentDetailView agent={selectedAgent} onClose={() => setSelectedAgent(null)} />
      )}

      {/* Toast notifications */}
      <ToastContainer />

      {/* Нижний таб-бар */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 bg-background/90 backdrop-blur-xl border-t border-white/5">
        <div className="flex items-center justify-around py-2 px-2">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => handleTabSwitch(tab.id)}
                className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-xl transition-all ${
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
