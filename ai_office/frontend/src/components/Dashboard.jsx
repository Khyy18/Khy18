import { ListTodo, DollarSign, Zap, Users } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import Sparkline from './Sparkline'
import Skeleton from './Skeleton'
import SLAWidget from './SLAWidget'

/**
 * Панель метрик (замена SystemStatus)
 * Показывает: задачи сегодня, расходы LLM, время ответа, активные агенты
 * + полоска активности за 24 часа
 */
export default function Dashboard() {
  const { data, loading } = useApi('dashboard', 10000)

  if (loading || !data) {
    return (
      <div className="grid grid-cols-2 gap-3">
        <Skeleton type="metric" count={4} />
      </div>
    )
  }

  const costPercent = Math.min((data.cost_today / 10) * 100, 100)
  const maxHourly = Math.max(...(data.hourly_activity || []), 1)

  return (
    <div className="space-y-3">
      {/* Row 1: метрики */}
      <div className="grid grid-cols-2 gap-3">
        {/* Задачи сегодня */}
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <ListTodo className="w-4 h-4 text-accent" />
            <span className="text-white/50 text-xs">Задачи сегодня</span>
          </div>
          <div className="flex items-end justify-between">
            <span className="text-white text-xl font-semibold">{data.tasks_today}</span>
            <Sparkline data={data.tasks_week_history} color="#3b82f6" width={60} height={20} />
          </div>
        </div>

        {/* Расходы LLM */}
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-secondary" />
            <span className="text-white/50 text-xs">Расходы LLM</span>
          </div>
          <div className="flex items-end justify-between mb-2">
            <span className="text-white text-xl font-semibold">${data.cost_today.toFixed(2)}</span>
            <span className="text-white/30 text-xs">/ $10.00</span>
          </div>
          <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-secondary to-accent rounded-full transition-all"
              style={{ width: `${costPercent}%` }}
            />
          </div>
        </div>

        {/* Время ответа */}
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-yellow-400" />
            <span className="text-white/50 text-xs">Время ответа</span>
          </div>
          <div className="flex items-end justify-between">
            <span className="text-white text-xl font-semibold">{data.avg_response_ms}<span className="text-sm text-white/50">мс</span></span>
            <Sparkline data={data.response_time_history} color="#eab308" width={60} height={20} />
          </div>
        </div>

        {/* Агенты */}
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-emerald-400" />
            <span className="text-white/50 text-xs">Агенты</span>
          </div>
          <div className="flex items-end justify-between">
            <span className="text-white text-xl font-semibold">{data.active_agents}<span className="text-sm text-white/50">/8</span></span>
            <div className="flex gap-0.5">
              {Array.from({ length: 8 }, (_, i) => (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full ${i < data.active_agents ? 'bg-emerald-400' : 'bg-white/10'}`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Активность 24ч */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
        <span className="text-white/50 text-xs mb-2 block">Активность 24ч</span>
        <div className="flex items-end gap-0.5 h-8">
          {(data.hourly_activity || []).map((val, i) => (
            <div
              key={i}
              className="flex-1 bg-accent/60 rounded-sm transition-all"
              style={{ height: `${Math.max((val / maxHourly) * 100, 4)}%` }}
            />
          ))}
        </div>
      </div>

      {/* Row 3: SLA Widget */}
      <SLAWidget />
    </div>
  )
}
