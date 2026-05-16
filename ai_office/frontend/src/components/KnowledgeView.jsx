import { useState, useCallback } from 'react'
import { Brain, Search, Trash2 } from 'lucide-react'

/**
 * Просмотр фактов из базы знаний
 * Поиск по entity, отображение subject -> predicate -> object
 */
export default function KnowledgeView() {
  const [search, setSearch] = useState('')
  const [facts, setFacts] = useState([])
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState({})

  const handleSearch = useCallback(async () => {
    if (!search.trim()) return
    setLoading(true)
    try {
      const resp = await fetch(`/api/knowledge?entity=${encodeURIComponent(search.trim())}`)
      const data = await resp.json()
      setFacts(Array.isArray(data) ? data : (data.facts || data.items || []))
    } catch (e) {
      setFacts([])
    }
    setLoading(false)
  }, [search])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch()
  }

  const handleDelete = useCallback(async (id) => {
    setDeleting(prev => ({ ...prev, [id]: true }))
    try {
      await fetch(`/api/knowledge/${id}`, { method: 'DELETE' })
      setFacts(prev => prev.filter(f => f.id !== id))
    } catch (e) { /* ignore */ }
    setDeleting(prev => ({ ...prev, [id]: false }))
  }, [])

  return (
    <div className="space-y-4">
      <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
        <Brain className="w-4 h-4" />
        База знаний
      </h3>

      {/* Search */}
      <div className="flex gap-2">
        <div className="flex-1 flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-3 py-2">
          <Search className="w-4 h-4 text-white/40" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Поиск по сущности..."
            className="flex-1 bg-transparent text-white text-sm focus:outline-none placeholder-white/30"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading || !search.trim()}
          className="px-4 py-2 bg-accent/20 text-accent rounded-xl text-sm font-medium hover:bg-accent/30 transition-all disabled:opacity-50"
        >
          Найти
        </button>
      </div>

      {/* Results */}
      {loading ? (
        <div className="text-white/30 text-sm text-center py-6">Поиск...</div>
      ) : facts.length === 0 && search ? (
        <div className="text-white/30 text-sm text-center py-6">Факты не найдены</div>
      ) : (
        <div className="space-y-2">
          {facts.map((fact) => (
            <div key={fact.id} className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="text-white text-sm">
                    <span className="text-accent font-medium">{fact.subject}</span>
                    <span className="text-white/40 mx-2">&rarr;</span>
                    <span className="text-white/70">{fact.predicate}</span>
                    <span className="text-white/40 mx-2">&rarr;</span>
                    <span className="text-emerald-400 font-medium">{fact.object}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1.5">
                    {fact.confidence != null && (
                      <span className="px-2 py-0.5 bg-white/5 border border-white/10 rounded-full text-[10px] text-white/50">
                        {fact.confidence}
                      </span>
                    )}
                    {fact.source_agent && (
                      <span className="text-white/30 text-[10px]">{fact.source_agent}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(fact.id)}
                  disabled={deleting[fact.id]}
                  className="p-1.5 text-white/30 hover:text-red-400 transition-all disabled:opacity-50"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
