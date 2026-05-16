import { useState, useEffect } from 'react'
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react'

// Module-level toast state (simple pub/sub)
let toastListeners = []
let toastId = 0

export function showToast(message, type = 'info') {
  const toast = { id: ++toastId, message, type, visible: true }
  toastListeners.forEach(listener => listener(toast))
}

export function ToastContainer() {
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    const listener = (toast) => {
      setToasts(prev => [...prev, toast])
      // Auto-dismiss after 3 seconds
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== toast.id))
      }, 3000)
    }
    toastListeners.push(listener)
    return () => {
      toastListeners = toastListeners.filter(l => l !== listener)
    }
  }, [])

  const icons = {
    success: CheckCircle,
    error: AlertCircle,
    info: Info,
  }

  return (
    <div className="fixed bottom-16 left-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map(toast => {
        const Icon = icons[toast.type] || icons.info
        return (
          <div
            key={toast.id}
            className="pointer-events-auto bg-white/10 backdrop-blur-xl border border-white/20 rounded-xl px-4 py-3 flex items-center gap-3 animate-toast-in"
          >
            <Icon className="w-4 h-4 text-accent shrink-0" />
            <span className="text-white/90 text-sm flex-1">{toast.message}</span>
          </div>
        )
      })}
    </div>
  )
}
