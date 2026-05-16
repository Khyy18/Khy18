import { useState, useEffect } from 'react'
import { Crown, Zap } from 'lucide-react'

/**
 * Бейдж подписки - отображает текущий тариф и использование
 * Компактный вариант для хедера/дашборда
 */
export default function SubscriptionBadge() {
  const [subscription, setSubscription] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/subscription/status')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => setSubscription(data))
      .catch(err => setError(err.message))
  }, [])

  if (error || !subscription) return null

  const tier = subscription.tier || 'free'
  const messagesUsed = subscription.messages_used ?? 0
  const messagesLimit = subscription.messages_limit ?? 100
  const usagePercent = Math.min((messagesUsed / messagesLimit) * 100, 100)

  const tierConfig = {
    free: { label: 'Free', color: 'bg-gray-500/20 text-gray-300', icon: null },
    pro: { label: 'Pro', color: 'bg-purple-500/20 text-purple-300', icon: Crown },
    team: { label: 'Team', color: 'bg-amber-500/20 text-amber-300', icon: Crown },
  }

  const config = tierConfig[tier] || tierConfig.free
  const TierIcon = config.icon

  const handleUpgrade = () => {
    // Открываем бота с командой /upgrade
    window.open('https://t.me/ai_office_bot?start=upgrade', '_blank')
  }

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
      {/* Тариф */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {TierIcon && <TierIcon className="w-4 h-4" />}
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${config.color}`}>
            {config.label}
          </span>
        </div>
        {tier === 'free' && (
          <button
            onClick={handleUpgrade}
            className="flex items-center gap-1 px-3 py-1 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white text-xs font-medium rounded-full transition-all"
          >
            <Zap className="w-3 h-3" />
            Улучшить план
          </button>
        )}
      </div>

      {/* Прогресс использования для бесплатного тарифа */}
      {tier === 'free' && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-white/50 text-xs">Сообщения</span>
            <span className="text-white/70 text-xs">{messagesUsed}/{messagesLimit}</span>
          </div>
          <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                usagePercent > 80 ? 'bg-red-500' : usagePercent > 50 ? 'bg-yellow-500' : 'bg-accent'
              }`}
              style={{ width: `${usagePercent}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
