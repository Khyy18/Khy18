import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

/**
 * Kanban-карточка задачи с поддержкой drag-and-drop
 * Приоритет отображается цветной полоской слева
 */
export default function KanbanCard({ task, disabled = false }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: task.id,
    disabled,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  // Цвет левой полоски по приоритету
  const priorityBorder = {
    high: 'border-l-red-500',
    medium: 'border-l-yellow-500',
    low: 'border-l-green-500',
  }

  const borderColor = priorityBorder[task.priority] || priorityBorder.low

  // Расчет времени с момента создания
  const getTimeAgo = (timestamp) => {
    if (!timestamp) return ''
    const diff = Date.now() - new Date(timestamp).getTime()
    const minutes = Math.floor(diff / 60000)
    if (minutes < 60) return `${minutes}m`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h`
    return `${Math.floor(hours / 24)}d`
  }

  // Инициалы агента
  const getInitials = (name) => {
    if (!name) return '?'
    return name
      .split(' ')
      .map((w) => w[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  const assignee = task.assigned_to || task.executor_id

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={`bg-white/5 backdrop-blur-xl border border-white/10 rounded-xl p-3 border-l-4 ${borderColor} cursor-grab active:cursor-grabbing hover:shadow-lg hover:shadow-accent/10 transition-all ${
        isDragging ? 'kanban-dragging' : ''
      }`}
    >
      {/* Заголовок задачи */}
      <p className="text-white/90 text-sm line-clamp-2 leading-snug">
        {task.description}
      </p>

      {/* Нижняя строка: время слева, аватар справа */}
      <div className="flex items-center justify-between mt-2">
        <span className="text-white/30 text-[10px]">
          {getTimeAgo(task.created_at)}
        </span>

        {assignee && (
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-accent to-secondary flex items-center justify-center text-[10px] text-white font-medium">
            {getInitials(assignee)}
          </div>
        )}
      </div>
    </div>
  )
}
