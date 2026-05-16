import { TrendingUp, Award, Clock, AlertTriangle } from 'lucide-react'
import { useApi } from '../hooks/useApi'

/**
 * Аналитика - KPI, лидерборд, графики (чистый SVG)
 */
export default function AnalyticsTab() {
  const { data: overview, loading: loadingOverview } = useApi('analytics/overview', 15000)
  const { data: productivity, loading: loadingProd } = useApi('analytics/productivity', 15000)

  if (loadingOverview || loadingProd || !overview) {
    return (
      <div className="space-y-4">
        <h2 className="text-white text-base font-semibold">Аналитика</h2>
        <div className="text-white/30 text-sm text-center py-8">Загрузка данных...</div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h2 className="text-white text-base font-semibold">Аналитика</h2>

      {/* KPI Cards */}
      <KPICards overview={overview} />

      {/* Agent Leaderboard */}
      <AgentLeaderboard data={productivity?.agent_leaderboard || overview?.agent_leaderboard || []} />

      {/* Time-to-Resolve Bar Chart */}
      <ResolveTimeChart data={productivity?.time_to_resolve || overview?.time_to_resolve || []} />

      {/* Activity Heatmap */}
      <ActivityHeatmap data={productivity?.heatmap || overview?.heatmap || []} />

      {/* Throughput Trend */}
      <ThroughputChart data={productivity?.throughput || overview?.throughput || []} />
    </div>
  )
}

function KPICards({ overview }) {
  const cards = [
    {
      icon: TrendingUp,
      label: 'За неделю',
      value: overview.tasks_completed_week ?? 0,
      color: 'text-accent',
    },
    {
      icon: Award,
      label: 'За месяц',
      value: overview.tasks_completed_month ?? 0,
      color: 'text-emerald-400',
    },
    {
      icon: Clock,
      label: 'Среднее время',
      value: overview.avg_resolve_time ? `${overview.avg_resolve_time}м` : 'N/A',
      color: 'text-yellow-400',
    },
    {
      icon: AlertTriangle,
      label: 'Узкое место',
      value: overview.bottleneck_agent || 'N/A',
      color: 'text-red-400',
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3">
      {cards.map((card, i) => {
        const Icon = card.icon
        return (
          <div key={i} className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
            <div className="flex items-center gap-2 mb-2">
              <Icon className={`w-4 h-4 ${card.color}`} />
              <span className="text-white/50 text-xs">{card.label}</span>
            </div>
            <span className="text-white text-lg font-semibold">{card.value}</span>
          </div>
        )
      })}
    </div>
  )
}

function AgentLeaderboard({ data }) {
  if (!data || data.length === 0) return null

  const sorted = [...data].sort((a, b) => (b.tasks_completed || 0) - (a.tasks_completed || 0))

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden">
      <div className="px-4 py-3 border-b border-white/10">
        <span className="text-white/70 text-sm font-medium">Лидерборд агентов</span>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/10">
            <th className="text-left text-white/50 px-4 py-2">#</th>
            <th className="text-left text-white/50 px-4 py-2">Агент</th>
            <th className="text-right text-white/50 px-4 py-2">Задачи</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((agent, idx) => (
            <tr key={idx} className="border-b border-white/5">
              <td className="px-4 py-2 text-white/40">{idx + 1}</td>
              <td className="px-4 py-2 text-white">{agent.name || agent.agent_name}</td>
              <td className="px-4 py-2 text-right text-accent font-medium">{agent.tasks_completed || 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ResolveTimeChart({ data }) {
  if (!data || data.length === 0) return null

  const maxVal = Math.max(...data.map(d => d.avg_time || d.value || 0), 1)

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
      <span className="text-white/70 text-sm font-medium block mb-3">Время решения по приоритету</span>
      <svg width="100%" height={data.length * 32 + 8} viewBox={`0 0 300 ${data.length * 32 + 8}`} preserveAspectRatio="xMidYMid meet">
        {data.map((item, idx) => {
          const val = item.avg_time || item.value || 0
          const barWidth = (val / maxVal) * 200
          const y = idx * 32 + 4
          return (
            <g key={idx}>
              <text x="0" y={y + 16} fill="rgba(255,255,255,0.5)" fontSize="10" dominantBaseline="middle">
                {item.priority || item.label}
              </text>
              <rect x="70" y={y + 4} width={barWidth} height="16" rx="4" fill="var(--accent, #6366f1)" opacity="0.7" />
              <text x={75 + barWidth} y={y + 16} fill="rgba(255,255,255,0.7)" fontSize="10" dominantBaseline="middle">
                {val}м
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function ActivityHeatmap({ data }) {
  if (!data || data.length === 0) return null

  const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
  // data should be 7x24 array or flat array of 168 values
  const flat = Array.isArray(data[0]) ? data.flat() : data
  const maxVal = Math.max(...flat.map(v => typeof v === 'number' ? v : (v?.count || 0)), 1)

  const getValue = (day, hour) => {
    if (Array.isArray(data[0])) {
      return data[day]?.[hour] || 0
    }
    const idx = day * 24 + hour
    const item = flat[idx]
    return typeof item === 'number' ? item : (item?.count || 0)
  }

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
      <span className="text-white/70 text-sm font-medium block mb-3">Активность (день/час)</span>
      <div className="overflow-x-auto">
        <div className="grid grid-rows-7 gap-0.5" style={{ minWidth: '400px' }}>
          {days.map((day, dayIdx) => (
            <div key={dayIdx} className="flex items-center gap-0.5">
              <span className="text-white/40 text-[9px] w-5 flex-shrink-0">{day}</span>
              {Array.from({ length: 24 }, (_, hour) => {
                const val = getValue(dayIdx, hour)
                const intensity = val / maxVal
                return (
                  <div
                    key={hour}
                    className="w-3 h-3 rounded-sm flex-shrink-0"
                    style={{
                      backgroundColor: intensity > 0
                        ? `rgba(99, 102, 241, ${0.1 + intensity * 0.8})`
                        : 'rgba(255,255,255,0.05)',
                    }}
                    title={`${day} ${hour}:00 - ${val}`}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ThroughputChart({ data }) {
  if (!data || data.length === 0) return null

  const values = data.map(d => typeof d === 'number' ? d : (d.count || d.value || 0))
  const maxVal = Math.max(...values, 1)
  const width = 300
  const height = 100
  const padding = 10

  const points = values.map((val, idx) => {
    const x = padding + (idx / Math.max(values.length - 1, 1)) * (width - 2 * padding)
    const y = height - padding - (val / maxVal) * (height - 2 * padding)
    return `${x},${y}`
  }).join(' ')

  const areaPoints = `${padding},${height - padding} ${points} ${padding + ((values.length - 1) / Math.max(values.length - 1, 1)) * (width - 2 * padding)},${height - padding}`

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
      <span className="text-white/70 text-sm font-medium block mb-3">Пропускная способность (задач/день)</span>
      <svg width="100%" height="100" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
        {/* Area fill */}
        <polygon points={areaPoints} fill="var(--accent, #6366f1)" opacity="0.1" />
        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke="var(--accent, #6366f1)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Data points */}
        {values.map((val, idx) => {
          const x = padding + (idx / Math.max(values.length - 1, 1)) * (width - 2 * padding)
          const y = height - padding - (val / maxVal) * (height - 2 * padding)
          return <circle key={idx} cx={x} cy={y} r="3" fill="var(--accent, #6366f1)" />
        })}
      </svg>
    </div>
  )
}
