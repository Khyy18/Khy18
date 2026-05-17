import { Inbox } from 'lucide-react'

export default function EmptyState({ icon: Icon = Inbox, title = 'No data', message = '', action, onAction }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-white/30" />
      </div>
      <h3 className="text-lg font-medium text-white/70 mb-1">{title}</h3>
      {message && <p className="text-sm text-white/40 max-w-sm">{message}</p>}
      {action && onAction && (
        <button
          onClick={onAction}
          className="mt-4 px-4 py-2 bg-accent hover:bg-accent/80 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {action}
        </button>
      )}
    </div>
  )
}
