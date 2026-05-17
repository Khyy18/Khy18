export default function LoadingSkeleton({ rows = 3, className = '' }) {
  return (
    <div className={`space-y-4 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="bg-white/5 rounded-xl p-4 animate-skeleton">
          <div className="h-4 bg-white/10 rounded w-3/4 mb-3" />
          <div className="h-3 bg-white/5 rounded w-1/2" />
        </div>
      ))}
    </div>
  )
}
