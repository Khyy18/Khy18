/**
 * Skeleton плейсхолдер для загрузки
 * Поддерживает типы: card (AgentCard), metric (Dashboard), kanban (KanbanCard)
 */
export default function Skeleton({ type = 'card', count = 1 }) {
  const items = Array.from({ length: count }, (_, i) => i)

  const shapes = {
    card: 'h-20 rounded-2xl',
    metric: 'h-24 rounded-xl',
    kanban: 'h-16 rounded-xl',
  }

  const shape = shapes[type] || shapes.card

  return (
    <>
      {items.map((i) => (
        <div
          key={i}
          className={`bg-white/5 animate-pulse ${shape}`}
        />
      ))}
    </>
  )
}
