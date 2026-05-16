import { Cpu, MemoryStick, Users } from 'lucide-react'

/**
 * Компонент системного статуса
 * Отображает: CPU, RAM, количество агентов онлайн
 * Стиль: тонкие градиентные полоски с крупными числами
 */
export default function SystemStatus({ status }) {
  const metrics = [
    {
      icon: Cpu,
      label: 'CPU',
      value: status?.cpu_usage ?? 0,
      suffix: '%',
      gradient: 'from-blue-500 to-cyan-400',
    },
    {
      icon: MemoryStick,
      label: 'RAM',
      value: status?.ram_usage ?? 0,
      suffix: '%',
      gradient: 'from-purple-500 to-pink-400',
    },
    {
      icon: Users,
      label: 'Agents',
      value: status?.agents_online ?? 0,
      suffix: '',
      gradient: 'from-green-500 to-emerald-400',
      max: status?.agents_total ?? 4,
    },
  ]

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
      <div className="grid grid-cols-3 gap-4">
        {metrics.map((metric) => {
          const Icon = metric.icon
          const percentage = metric.max
            ? (metric.value / metric.max) * 100
            : metric.value
          return (
            <div key={metric.label} className="text-center">
              <Icon className="w-4 h-4 mx-auto mb-1 text-white/40" />
              <p className="text-white font-semibold text-lg leading-none">
                {metric.value}{metric.suffix}
              </p>
              <p className="text-white/40 text-[10px] mt-1 uppercase tracking-wider">
                {metric.label}
              </p>
              {/* Прогресс-бар */}
              <div className="mt-2 h-1 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={`h-full bg-gradient-to-r ${metric.gradient} rounded-full transition-all duration-500`}
                  style={{ width: `${Math.min(percentage, 100)}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
