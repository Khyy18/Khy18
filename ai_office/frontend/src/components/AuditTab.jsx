import { useState, useCallback } from 'react'
import { FileText, Download, Search } from 'lucide-react'
import { useApi } from '../hooks/useApi'

/**
 * Аудит - фильтруемая таблица событий с экспортом
 */
export default function AuditTab() {
  const [actorType, setActorType] = useState('all')
  const [actionFilter, setActionFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)

  const buildQuery = useCallback(() => {
    const params = new URLSearchParams()
    if (actorType !== 'all') params.append('actor_type', actorType)
    if (actionFilter) params.append('action', actionFilter)
    if (dateFrom) params.append('date_from', dateFrom)
    if (dateTo) params.append('date_to', dateTo)
    params.append('page', '1')
    params.append('limit', '20')
    return `audit?${params.toString()}`
  }, [actorType, actionFilter, dateFrom, dateTo])

  const { data, loading } = useApi(buildQuery(), 10000)

  const displayItems = items.length > 0 ? items : (Array.isArray(data) ? data : (data?.items || []))

  const handleLoadMore = async () => {
    setLoadingMore(true)
    const nextPage = page + 1
    const params = new URLSearchParams()
    if (actorType !== 'all') params.append('actor_type', actorType)
    if (actionFilter) params.append('action', actionFilter)
    if (dateFrom) params.append('date_from', dateFrom)
    if (dateTo) params.append('date_to', dateTo)
    params.append('page', String(nextPage))
    params.append('limit', '20')

    try {
      const resp = await fetch(`/api/audit?${params.toString()}`)
      const json = await resp.json()
      const newItems = Array.isArray(json) ? json : (json?.items || [])
      if (newItems.length === 0) {
        setHasMore(false)
      } else {
        setItems(prev => [...(prev.length > 0 ? prev : displayItems), ...newItems])
        setPage(nextPage)
      }
    } catch (e) { /* ignore */ }
    setLoadingMore(false)
  }

  const handleExport = (format) => {
    const params = new URLSearchParams()
    if (actorType !== 'all') params.append('actor_type', actorType)
    if (actionFilter) params.append('action', actionFilter)
    if (dateFrom) params.append('date_from', dateFrom)
    if (dateTo) params.append('date_to', dateTo)
    params.append('format', format)
    window.open(`/api/audit/export?${params.toString()}`, '_blank')
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
          <FileText className="w-4 h-4" />
          Аудит
        </h3>
        <div className="flex gap-2">
          <button
            onClick={() => handleExport('csv')}
            className="flex items-center gap-1 px-2 py-1 bg-white/5 text-white/60 rounded-lg text-[10px] hover:bg-white/10 transition-all"
          >
            <Download className="w-3 h-3" />
            Экспорт CSV
          </button>
          <button
            onClick={() => handleExport('pdf')}
            className="flex items-center gap-1 px-2 py-1 bg-white/5 text-white/60 rounded-lg text-[10px] hover:bg-white/10 transition-all"
          >
            <Download className="w-3 h-3" />
            Экспорт PDF
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <select
          value={actorType}
          onChange={(e) => { setActorType(e.target.value); setItems([]); setPage(1); setHasMore(true) }}
          className="bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-white text-xs focus:outline-none focus:border-accent/50"
        >
          <option value="all">Все типы</option>
          <option value="user">Пользователь</option>
          <option value="agent">Агент</option>
          <option value="system">Система</option>
        </select>

        <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl px-3 py-1.5">
          <Search className="w-3 h-3 text-white/40" />
          <input
            type="text"
            value={actionFilter}
            onChange={(e) => { setActionFilter(e.target.value); setItems([]); setPage(1); setHasMore(true) }}
            placeholder="Действие..."
            className="bg-transparent text-white text-xs w-20 focus:outline-none placeholder-white/30"
          />
        </div>

        <input
          type="date"
          value={dateFrom}
          onChange={(e) => { setDateFrom(e.target.value); setItems([]); setPage(1); setHasMore(true) }}
          className="bg-white/5 border border-white/10 rounded-xl px-2 py-1.5 text-white text-xs focus:outline-none focus:border-accent/50"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => { setDateTo(e.target.value); setItems([]); setPage(1); setHasMore(true) }}
          className="bg-white/5 border border-white/10 rounded-xl px-2 py-1.5 text-white text-xs focus:outline-none focus:border-accent/50"
        />
      </div>

      {/* Table */}
      {loading && displayItems.length === 0 ? (
        <div className="text-white/30 text-sm text-center py-6">Загрузка...</div>
      ) : displayItems.length === 0 ? (
        <div className="text-white/30 text-sm text-center py-6">Нет записей аудита</div>
      ) : (
        <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left text-white/50 px-3 py-2">Время</th>
                  <th className="text-left text-white/50 px-3 py-2">Актор</th>
                  <th className="text-left text-white/50 px-3 py-2">Действие</th>
                  <th className="text-left text-white/50 px-3 py-2">Ресурс</th>
                  <th className="text-left text-white/50 px-3 py-2">Детали</th>
                </tr>
              </thead>
              <tbody>
                {displayItems.map((entry, idx) => (
                  <tr key={idx} className="border-b border-white/5">
                    <td className="px-3 py-2 text-white/60 whitespace-nowrap">
                      {entry.timestamp ? new Date(entry.timestamp).toLocaleString('ru-RU', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : ''}
                    </td>
                    <td className="px-3 py-2 text-white">{entry.actor || entry.actor_name || ''}</td>
                    <td className="px-3 py-2 text-accent">{entry.action || ''}</td>
                    <td className="px-3 py-2 text-white/60">{entry.resource || ''}</td>
                    <td className="px-3 py-2 text-white/40 max-w-[120px] truncate">{entry.details || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Load More */}
      {hasMore && displayItems.length > 0 && (
        <div className="text-center">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="px-4 py-2 bg-white/5 text-white/60 rounded-xl text-xs font-medium hover:bg-white/10 transition-all disabled:opacity-50"
          >
            {loadingMore ? 'Загрузка...' : 'Загрузить ещё'}
          </button>
        </div>
      )}
    </div>
  )
}
