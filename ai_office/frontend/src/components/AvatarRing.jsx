/**
 * Обертка аватара со статусным кольцом
 * idle: статичная тонкая рамка
 * working/typing: вращающееся кольцо с conic-gradient
 * offline: полупрозрачный, пунктирная рамка
 */
export default function AvatarRing({ children, status = 'idle', size = 48 }) {
  const isActive = status === 'working' || status === 'typing'
  const isOffline = status === 'offline'

  const wrapperStyle = { width: size + 4, height: size + 4 }
  const innerStyle = { width: size, height: size }

  if (isActive) {
    return (
      <div className="relative shrink-0" style={wrapperStyle}>
        {/* Rotating gradient ring */}
        <div
          className="absolute inset-0 rounded-full animate-avatar-ring"
          style={{
            background: 'conic-gradient(from 0deg, #3b82f6, #a855f7, #3b82f6)',
            padding: '2px',
          }}
        >
          <div className="w-full h-full rounded-full bg-background" />
        </div>
        {/* Avatar content */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="rounded-full overflow-hidden" style={innerStyle}>
            {children}
          </div>
        </div>
      </div>
    )
  }

  if (isOffline) {
    return (
      <div
        className="shrink-0 rounded-full border-2 border-dashed border-white/20 opacity-50 flex items-center justify-center"
        style={wrapperStyle}
      >
        <div className="rounded-full overflow-hidden" style={innerStyle}>
          {children}
        </div>
      </div>
    )
  }

  // idle - static subtle border
  return (
    <div
      className="shrink-0 rounded-full border-2 border-white/20 flex items-center justify-center"
      style={wrapperStyle}
    >
      <div className="rounded-full overflow-hidden" style={innerStyle}>
        {children}
      </div>
    </div>
  )
}
