import { TrendingUp, TrendingDown } from 'lucide-react'

export default function MetricCard({ title, value, delta, icon: Icon }) {
  const isPositive = delta && delta > 0
  const isNegative = delta && delta < 0

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-white/50">{title}</span>
        {Icon && <Icon className="w-4 h-4 text-white/30" />}
      </div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold text-white">{value}</span>
        {delta !== undefined && delta !== null && (
          <span className={`flex items-center gap-0.5 text-xs font-medium ${
            isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-white/40'
          }`}>
            {isPositive && <TrendingUp className="w-3 h-3" />}
            {isNegative && <TrendingDown className="w-3 h-3" />}
            {isPositive ? '+' : ''}{delta}%
          </span>
        )}
      </div>
    </div>
  )
}
