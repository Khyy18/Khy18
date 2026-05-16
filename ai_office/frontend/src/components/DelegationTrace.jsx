import { useState, useEffect } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

/**
 * Компонент трассировки делегирования - показывает диалог между агентами
 */
export default function DelegationTrace({ traceId }) {
  const [expanded, setExpanded] = useState(false)
  const [trace, setTrace] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (expanded && !trace) {
      fetchTrace()
    }
  }, [expanded])

  const fetchTrace = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/delegations/${traceId}/trace`)
      if (res.ok) {
        const data = await res.json()
        setTrace(data)
      }
    } catch (err) {
      console.error('Failed to fetch trace:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-accent/70 hover:text-accent transition-colors"
      >
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {expanded ? 'Скрыть' : 'Показать процесс решения'}
      </button>

      {expanded && (
        <div className="mt-2 space-y-2 max-h-[300px] overflow-y-auto">
          {loading && (
            <div className="text-white/40 text-xs animate-pulse">Загрузка...</div>
          )}
          {trace && trace.messages && trace.messages.map((msg, idx) => {
            const isSource = msg.role === 'system' || msg.role === 'human'
            return (
              <div
                key={idx}
                className={`flex ${isSource ? 'justify-start' : 'justify-end'}`}
              >
                <div
                  className={`max-w-[80%] rounded-xl p-3 text-xs backdrop-blur-sm border border-white/10 ${
                    isSource
                      ? 'bg-purple-500/10 text-white/80'
                      : 'bg-blue-500/10 text-white/80'
                  }`}
                >
                  <div className="text-[10px] text-white/40 mb-1">
                    {msg.role}
                  </div>
                  <div className="whitespace-pre-wrap break-words">
                    {msg.content?.substring(0, 500)}
                    {msg.content?.length > 500 && '...'}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
