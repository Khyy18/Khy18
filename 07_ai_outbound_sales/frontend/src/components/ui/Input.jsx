export function Input({ label, error, className = '', ...props }) {
  return (
    <div className={className}>
      {label && <label className="block text-sm font-medium text-white/70 mb-1">{label}</label>}
      <input
        className={`w-full px-3 py-2 bg-white/5 border ${error ? 'border-red-500/50' : 'border-white/10'} rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors`}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}

export function Select({ label, options = [], error, className = '', ...props }) {
  return (
    <div className={className}>
      {label && <label className="block text-sm font-medium text-white/70 mb-1">{label}</label>}
      <select
        className={`w-full px-3 py-2 bg-white/5 border ${error ? 'border-red-500/50' : 'border-white/10'} rounded-lg text-white focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors`}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-card text-white">
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}

export function Textarea({ label, error, className = '', ...props }) {
  return (
    <div className={className}>
      {label && <label className="block text-sm font-medium text-white/70 mb-1">{label}</label>}
      <textarea
        className={`w-full px-3 py-2 bg-white/5 border ${error ? 'border-red-500/50' : 'border-white/10'} rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors resize-none`}
        rows={4}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}

export function Toggle({ label, checked, onChange, className = '' }) {
  return (
    <label className={`flex items-center gap-3 cursor-pointer ${className}`}>
      <div className="relative">
        <input type="checkbox" checked={checked} onChange={onChange} className="sr-only" />
        <div className={`w-10 h-5 rounded-full transition-colors ${checked ? 'bg-accent' : 'bg-white/10'}`} />
        <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : ''}`} />
      </div>
      {label && <span className="text-sm text-white/70">{label}</span>}
    </label>
  )
}
