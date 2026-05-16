import { useApi } from '../hooks/useApi'

/**
 * SLA Widget - компактная карточка с круговым прогрессом
 * Зеленый >90%, Желтый 70-90%, Красный <70%
 */
export default function SLAWidget() {
  const { data, loading } = useApi('sla/status', 10000)

  const percent = data?.compliance_percent ?? 0
  const radius = 28
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (percent / 100) * circumference

  const getColor = (val) => {
    if (val > 90) return '#22c55e'
    if (val >= 70) return '#eab308'
    return '#ef4444'
  }

  const color = getColor(percent)

  if (loading || !data) {
    return (
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3 flex items-center justify-center">
        <div className="w-16 h-16 bg-white/5 rounded-full animate-pulse" />
      </div>
    )
  }

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
      <div className="flex items-center gap-3">
        <div className="relative w-16 h-16 flex-shrink-0">
          <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
            <circle
              cx="32"
              cy="32"
              r={radius}
              fill="none"
              stroke="rgba(255,255,255,0.1)"
              strokeWidth="4"
            />
            <circle
              cx="32"
              cy="32"
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              className="transition-all duration-700"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-white text-xs font-semibold">{Math.round(percent)}%</span>
          </div>
        </div>
        <div>
          <span className="text-white/50 text-xs block">SLA</span>
          <span className="text-white text-sm font-medium">Соблюдение</span>
        </div>
      </div>
    </div>
  )
}
