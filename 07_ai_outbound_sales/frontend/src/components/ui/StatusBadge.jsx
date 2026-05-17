const STATUS_COLORS = {
  active: 'bg-green-500/20 text-green-400 border-green-500/30',
  running: 'bg-green-500/20 text-green-400 border-green-500/30',
  completed: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  paused: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  draft: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  error: 'bg-red-500/20 text-red-400 border-red-500/30',
  cancelled: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  replied: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  contacted: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  qualified: 'bg-green-500/20 text-green-400 border-green-500/30',
  new: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
}

export default function StatusBadge({ status }) {
  const colorClass = STATUS_COLORS[status?.toLowerCase()] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colorClass}`}>
      {status}
    </span>
  )
}
