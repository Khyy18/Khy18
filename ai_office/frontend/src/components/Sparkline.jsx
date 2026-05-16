/**
 * Компонент спарклайн-графика (чистый SVG)
 * Отображает массив чисел как линию с градиентной заливкой
 */
export default function Sparkline({ data = [], color = '#3b82f6', width = 80, height = 24 }) {
  if (!data || data.length === 0) {
    // Пустые данные - плоская линия
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke={color} strokeWidth="1.5" opacity="0.3" />
      </svg>
    )
  }

  if (data.length === 1) {
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke={color} strokeWidth="1.5" opacity="0.5" />
      </svg>
    )
  }

  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const padding = 2

  const points = data.map((value, i) => {
    const x = (i / (data.length - 1)) * width
    const y = padding + ((max - value) / range) * (height - padding * 2)
    return `${x},${y}`
  })

  const polylinePoints = points.join(' ')

  // Area path (line + bottom fill)
  const firstX = 0
  const lastX = width
  const areaPath = `M${points[0]} ${points.slice(1).map(p => `L${p}`).join(' ')} L${lastX},${height} L${firstX},${height} Z`

  const gradientId = `sparkline-fill-${Math.random().toString(36).slice(2, 8)}`

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <polyline
        points={polylinePoints}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
