import { X } from 'lucide-react'

export default function Drawer({ isOpen, onClose, title, children }) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-md h-full bg-card border-l border-white/10 shadow-2xl overflow-y-auto">
        <div className="sticky top-0 flex items-center justify-between p-4 border-b border-white/10 bg-card/80 backdrop-blur-xl">
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/10 transition-colors">
            <X className="w-5 h-5 text-white/50" />
          </button>
        </div>
        <div className="p-4">
          {children}
        </div>
      </div>
    </div>
  )
}
