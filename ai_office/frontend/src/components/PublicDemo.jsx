import { useState, useEffect } from 'react'
import { Bot, Activity, ArrowRight } from 'lucide-react'

/**
 * Публичная демо-страница для неаутентифицированных пользователей
 * Показывает агентов и активность демо-воркспейса
 */
export default function PublicDemo() {
  const [agents, setAgents] = useState([])
  const [activity, setActivity] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    // DEMO: workspace_id=1 - демонстрационный workspace для landing page.
    // В production заменить на конфигурируемый ID или lookup по домену.
    fetch('/api/public/1/agents')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => setAgents(data))
      .catch(err => setError(err.message))

    fetch('/api/public/1/activity')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => setActivity(data))
      .catch(err => setError(err.message))
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900/20 to-gray-900 text-white flex flex-col">
      {/* Hero секция */}
      <div className="text-center px-6 pt-12 pb-8">
        <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-accent to-secondary rounded-2xl flex items-center justify-center">
          <Bot className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-2xl font-bold mb-2">AI Office</h1>
        <p className="text-white/60 text-sm max-w-xs mx-auto">
          Ваша карманная компания с ИИ-агентами. Автоматизируйте задачи, делегируйте рутину.
        </p>
      </div>

      {/* Агенты */}
      {agents.length > 0 && (
        <div className="px-4 mb-6">
          <h2 className="text-white/70 text-xs font-medium uppercase tracking-wider mb-3 px-1">
            Агенты
          </h2>
          <div className="space-y-2">
            {agents.slice(0, 5).map((agent, idx) => (
              <div
                key={idx}
                className="bg-white/5 border border-white/10 rounded-xl p-3 flex items-center gap-3"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent/50 to-secondary/50 flex items-center justify-center text-white text-xs font-semibold">
                  {(agent.name || 'A')[0]}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">{agent.name}</p>
                  <p className="text-white/40 text-xs truncate">{agent.role || agent.status}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Активность */}
      {activity.length > 0 && (
        <div className="px-4 mb-8">
          <h2 className="text-white/70 text-xs font-medium uppercase tracking-wider mb-3 px-1 flex items-center gap-1">
            <Activity className="w-3 h-3" />
            Активность
          </h2>
          <div className="space-y-2">
            {activity.slice(0, 5).map((item, idx) => (
              <div
                key={idx}
                className="bg-white/5 border border-white/10 rounded-xl px-3 py-2"
              >
                <p className="text-white/70 text-xs truncate">
                  <span className="text-accent font-medium">{item.agent || 'System'}</span>
                  {' - '}
                  {item.action || item.description || item.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CTA */}
      <div className="px-4 mt-auto pb-8">
        <a
          href="https://t.me/ai_office_bot"
          target="_blank"
          rel="noopener noreferrer"
          className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-accent to-secondary hover:opacity-90 text-white font-semibold py-4 px-6 rounded-2xl transition-all text-base"
        >
          Попробовать бесплатно
          <ArrowRight className="w-5 h-5" />
        </a>
        <p className="text-white/30 text-xs text-center mt-3">
          Бесплатный доступ к базовым агентам
        </p>
      </div>

      {error && (
        <p className="text-red-400/50 text-xs text-center pb-4">{error}</p>
      )}
    </div>
  )
}
