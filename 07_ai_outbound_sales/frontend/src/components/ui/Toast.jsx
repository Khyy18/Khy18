import { useState, useCallback, createContext, useContext } from 'react'
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react'

const ToastContext = createContext(null)

const ICONS = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
}

const COLORS = {
  success: 'border-green-500/30 text-green-400',
  error: 'border-red-500/30 text-red-400',
  info: 'border-blue-500/30 text-blue-400',
  warning: 'border-yellow-500/30 text-yellow-400',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      <div className="fixed top-4 right-4 z-[100] space-y-2 max-w-sm">
        {toasts.map((toast) => {
          const Icon = ICONS[toast.type] || Info
          return (
            <div
              key={toast.id}
              className={`flex items-center gap-3 px-4 py-3 bg-card/95 backdrop-blur-xl border rounded-xl shadow-lg animate-toast-in ${COLORS[toast.type] || COLORS.info}`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className="text-sm text-white/90 flex-1">{toast.message}</span>
              <button onClick={() => removeToast(toast.id)} className="p-0.5 hover:bg-white/10 rounded">
                <X className="w-3 h-3 text-white/50" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
