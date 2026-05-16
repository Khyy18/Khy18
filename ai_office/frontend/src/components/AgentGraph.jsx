import { useState, useEffect } from 'react'

/**
 * Граф делегирований между агентами
 * Отображает агентов как цветные круги с линиями делегирований между ними
 */
export default function AgentGraph() {
  const [delegations, setDelegations] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchDelegations = async () => {
      try {
        const response = await fetch('/api/delegations')
        if (response.ok) {
          const data = await response.json()
          setDelegations(data)
        }
      } catch (err) {
        // ignore
      } finally {
        setLoading(false)
      }
    }
    fetchDelegations()
  }, [])

  // Извлекаем уникальных агентов из делегирований
  const agentMap = {}
  delegations.forEach((d) => {
    if (d.agent_name && !agentMap[d.agent_id]) {
      agentMap[d.agent_id] = d.agent_name
    }
  })
  const agents = Object.entries(agentMap).map(([id, name]) => ({ id: Number(id), name }))

  // Цвета для агентов
  const gradients = [
    'from-violet-500 to-purple-600',
    'from-blue-500 to-cyan-600',
    'from-emerald-500 to-teal-600',
    'from-orange-500 to-red-600',
    'from-pink-500 to-rose-600',
    'from-yellow-500 to-amber-600',
  ]

  // Позиционирование агентов по кругу
  const getPosition = (index, total) => {
    const angle = (2 * Math.PI * index) / Math.max(total, 1) - Math.PI / 2
    const radius = 90
    const cx = 50 + radius * Math.cos(angle) * 0.9
    const cy = 50 + radius * Math.sin(angle) * 0.7
    return { left: `${cx}%`, top: `${cy}%` }
  }

  const getInitials = (name) => {
    return name
      .split(' ')
      .map((w) => w[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  if (loading) {
    return (
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
        <div className="text-center py-8 text-white/30 text-sm">Loading...</div>
      </div>
    )
  }

  if (agents.length === 0) {
    return (
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
        <h2 className="text-white/80 font-medium text-sm mb-4">Delegation Graph</h2>
        <div className="text-center py-8 text-white/30 text-sm">
          Нет делегирований
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
      <h2 className="text-white/80 font-medium text-sm mb-4">Delegation Graph</h2>
      <div className="relative w-full h-64">
        {/* SVG линии между агентами */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          {delegations.map((d, i) => {
            const fromIdx = agents.findIndex((a) => a.id === d.agent_id)
            // Рисуем линии от агента к центру (общий узел)
            if (fromIdx === -1) return null
            const fromPos = getPosition(fromIdx, agents.length)
            return (
              <line
                key={i}
                x1={fromPos.left.replace('%', '') + '%'}
                y1={fromPos.top.replace('%', '') + '%'}
                x2="50%"
                y2="50%"
                stroke="rgba(139, 92, 246, 0.3)"
                strokeWidth="1"
                strokeDasharray="4 4"
              />
            )
          })}
        </svg>

        {/* Агенты как круги */}
        {agents.map((agent, index) => {
          const pos = getPosition(index, agents.length)
          const gradient = gradients[index % gradients.length]
          return (
            <div
              key={agent.id}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: pos.left, top: pos.top }}
              title={agent.name}
            >
              <div
                className={`w-12 h-12 rounded-full bg-gradient-to-br ${gradient} flex items-center justify-center text-white font-semibold text-xs shadow-lg border border-white/20`}
              >
                {getInitials(agent.name)}
              </div>
              <p className="text-white/60 text-[10px] text-center mt-1 whitespace-nowrap">
                {agent.name}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
