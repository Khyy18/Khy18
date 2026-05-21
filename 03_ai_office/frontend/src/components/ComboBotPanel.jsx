import { Bot, Users, Terminal, Clock } from 'lucide-react'
import { useApi } from '../hooks/useApi'

/**
 * ComboBotPanel - панель интеграции с Combo Bot
 * Показывает статус бота, метрики использования
 */
export default function ComboBotPanel() {
  const { data, loading, error } = useApi('services/combo-bot', 10000)

  const isOnline = data?.status === 'online'
  const stats = data?.stats

  return (
    <div className="space-y-4">
      {/* Service Status Card */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-green-400" />
            <h3 className="text-sm font-semibold text-white">Combo Bot</h3>
          </div>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wider ${
            isOnline
              ? 'bg-green-500/20 text-green-400 border border-green-500/30'
              : 'bg-red-500/20 text-red-400 border border-red-500/30'
          }`}>
            {loading ? 'Checking...' : isOnline ? 'Online' : 'Offline'}
          </span>
        </div>

        {error && (
          <p className="text-red-400/70 text-xs">Connection error: {error}</p>
        )}

        {!isOnline && !loading && (
          <p className="text-white/40 text-xs">
            Service is not reachable. Make sure Combo Bot is running.
          </p>
        )}
      </div>

      {/* Stats Grid */}
      {isOnline && stats && (
        <div className="grid grid-cols-2 gap-3">
          <MetricCard
            icon={Users}
            label="Active Users"
            value={stats.active_users ?? '-'}
            gradient="from-green-500 to-emerald-400"
          />
          <MetricCard
            icon={Terminal}
            label="Commands Today"
            value={stats.commands_today ?? '-'}
            gradient="from-blue-500 to-cyan-400"
          />
          <MetricCard
            icon={Clock}
            label="Uptime"
            value={stats.uptime != null ? `${stats.uptime}%` : '-'}
            gradient="from-purple-500 to-pink-400"
          />
          <MetricCard
            icon={Bot}
            label="Total Users"
            value={stats.total_users ?? '-'}
            gradient="from-orange-500 to-yellow-400"
          />
        </div>
      )}
    </div>
  )
}

function MetricCard({ icon: Icon, label, value, gradient }) {
  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 text-center">
      <Icon className="w-4 h-4 mx-auto mb-2 text-white/40" />
      <p className="text-white font-semibold text-lg leading-none">{value}</p>
      <p className="text-white/40 text-[10px] mt-1 uppercase tracking-wider">{label}</p>
      <div className="mt-2 h-1 bg-white/5 rounded-full overflow-hidden">
        <div className={`h-full w-2/3 bg-gradient-to-r ${gradient} rounded-full`} />
      </div>
    </div>
  )
}
