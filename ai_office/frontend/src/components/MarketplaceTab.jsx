import { useState, useCallback } from 'react'
import { Store, Download, Trash2, Package } from 'lucide-react'
import { useApi } from '../hooks/useApi'

/**
 * Маркетплейс плагинов - сетка карточек с установкой/удалением
 */
export default function MarketplaceTab() {
  const { data, loading } = useApi('marketplace', 10000)
  const [acting, setActing] = useState({})

  const handleInstall = useCallback(async (id) => {
    setActing(prev => ({ ...prev, [id]: 'installing' }))
    try {
      await fetch(`/api/marketplace/install/${id}`, { method: 'POST' })
    } catch (e) { /* ignore */ }
    setActing(prev => ({ ...prev, [id]: null }))
  }, [])

  const handleUninstall = useCallback(async (id) => {
    setActing(prev => ({ ...prev, [id]: 'uninstalling' }))
    try {
      await fetch(`/api/marketplace/${id}`, { method: 'DELETE' })
    } catch (e) { /* ignore */ }
    setActing(prev => ({ ...prev, [id]: null }))
  }, [])

  if (loading || !data) {
    return (
      <div className="space-y-4">
        <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
          <Store className="w-4 h-4" />
          Маркетплейс
        </h3>
        <div className="text-white/30 text-sm text-center py-6">Загрузка...</div>
      </div>
    )
  }

  const plugins = Array.isArray(data) ? data : (data.plugins || data.items || [])

  return (
    <div className="space-y-4">
      <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
        <Store className="w-4 h-4" />
        Маркетплейс
      </h3>

      {plugins.length === 0 ? (
        <div className="text-white/30 text-sm text-center py-6">
          Плагины недоступны
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {plugins.map((plugin) => (
            <div
              key={plugin.id}
              className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 space-y-3"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Package className="w-5 h-5 text-accent" />
                  <div>
                    <span className="text-white text-sm font-medium block">{plugin.name}</span>
                    {plugin.author && (
                      <span className="text-white/30 text-[10px]">{plugin.author}</span>
                    )}
                  </div>
                </div>
                {plugin.version && (
                  <span className="text-white/40 text-[10px] px-1.5 py-0.5 bg-white/5 rounded">
                    v{plugin.version}
                  </span>
                )}
              </div>

              {plugin.description && (
                <p className="text-white/50 text-xs">{plugin.description}</p>
              )}

              <div className="flex items-center justify-between">
                {plugin.tools_count != null && (
                  <span className="px-2 py-0.5 bg-accent/10 text-accent text-[10px] rounded-full">
                    {plugin.tools_count} tools
                  </span>
                )}

                {plugin.installed ? (
                  <button
                    onClick={() => handleUninstall(plugin.id)}
                    disabled={acting[plugin.id] === 'uninstalling'}
                    className="flex items-center gap-1 px-3 py-1.5 bg-red-500/20 text-red-400 rounded-lg text-xs font-medium hover:bg-red-500/30 transition-all disabled:opacity-50"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {acting[plugin.id] === 'uninstalling' ? '...' : 'Удалить'}
                  </button>
                ) : (
                  <button
                    onClick={() => handleInstall(plugin.id)}
                    disabled={acting[plugin.id] === 'installing'}
                    className="flex items-center gap-1 px-3 py-1.5 bg-green-500/20 text-green-400 rounded-lg text-xs font-medium hover:bg-green-500/30 transition-all disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {acting[plugin.id] === 'installing' ? '...' : 'Установить'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
