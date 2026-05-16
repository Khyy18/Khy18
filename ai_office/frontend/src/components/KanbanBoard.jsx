import { useState } from 'react'
import {
  DndContext,
  closestCorners,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  DragOverlay,
} from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { useDroppable } from '@dnd-kit/core'
import { Plus } from 'lucide-react'
import KanbanCard from './KanbanCard'
import TemplatePicker from './TemplatePicker'

/**
 * Колонка Kanban-доски
 */
function KanbanColumn({ id, title, tasks, isViewer }) {
  const { setNodeRef, isOver } = useDroppable({ id })

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col min-h-[200px] transition-colors ${
        isOver ? 'bg-accent/5 rounded-xl' : ''
      }`}
    >
      {/* Заголовок колонки */}
      <div className="flex items-center gap-2 mb-2 px-1">
        <span className="text-white/60 text-xs uppercase tracking-wider font-medium">
          {title}
        </span>
        <span className="bg-white/10 rounded-full px-2 text-white/50 text-[10px]">
          {tasks.length}
        </span>
      </div>

      {/* Список карточек */}
      <SortableContext
        items={tasks.map((t) => t.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-col gap-2 flex-1">
          {tasks.length > 0 ? (
            tasks.map((task) => (
              <KanbanCard key={task.id} task={task} disabled={isViewer} />
            ))
          ) : (
            <div className="flex-1 flex items-center justify-center border border-dashed border-white/10 rounded-xl min-h-[80px]">
              <span className="text-white/20 text-xs">Нет задач</span>
            </div>
          )}
        </div>
      </SortableContext>
    </div>
  )
}

/**
 * Kanban-доска с тремя колонками и drag-and-drop
 * Перетаскивание между колонками вызывает PATCH /api/tasks/{id}
 */
export default function KanbanBoard({ tasks, isViewer = false }) {
  const [activeTask, setActiveTask] = useState(null)
  const [showTemplatePicker, setShowTemplatePicker] = useState(false)

  const columns = [
    { id: 'open', title: 'Открытые' },
    { id: 'in_progress', title: 'В работе' },
    { id: 'done', title: 'Готово' },
  ]

  // Извлекаем массив задач из пагинированного ответа если нужно
  const taskList = Array.isArray(tasks) ? tasks : (tasks?.items || [])

  // Группировка задач по статусу
  const getColumnTasks = (columnId) => {
    return taskList.filter((t) => t.status === columnId)
  }

  // Сенсоры для drag-and-drop
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 200, tolerance: 5 },
    })
  )

  // Находим задачу по id
  const findTask = (taskId) => {
    return taskList.find((t) => t.id === taskId)
  }

  // Находим колонку, содержащую задачу
  const findColumn = (taskId) => {
    const task = findTask(taskId)
    return task ? task.status : null
  }

  const handleDragStart = (event) => {
    const task = findTask(event.active.id)
    setActiveTask(task)
  }

  const handleDragEnd = (event) => {
    const { active, over } = event
    setActiveTask(null)

    if (!over) return

    const activeId = active.id
    const overId = over.id

    // Определяем целевую колонку
    let targetColumn = null

    // Если перетащили на колонку напрямую
    if (columns.some((c) => c.id === overId)) {
      targetColumn = overId
    } else {
      // Перетащили на другую карточку - определяем её колонку
      targetColumn = findColumn(overId)
    }

    if (!targetColumn) return

    const sourceColumn = findColumn(activeId)

    // Если задача переместилась в другую колонку - обновляем статус
    if (sourceColumn && targetColumn !== sourceColumn) {
      updateTaskStatus(activeId, targetColumn)
    }
  }

  // PATCH запрос для обновления статуса задачи
  const updateTaskStatus = async (taskId, newStatus) => {
    try {
      const response = await fetch(`/api/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      if (!response.ok) {
        console.error('Failed to update task status:', response.status)
      }
    } catch (err) {
      console.error('Error updating task status:', err)
    }
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="relative">
        <div className="grid grid-cols-3 gap-3">
          {columns.map((column) => (
            <KanbanColumn
              key={column.id}
              id={column.id}
              title={column.title}
              tasks={getColumnTasks(column.id)}
              isViewer={isViewer}
            />
          ))}
        </div>

        {/* FAB button for creating tasks from template */}
        {!isViewer && (
          <button
            onClick={() => setShowTemplatePicker(true)}
            className="absolute bottom-4 right-4 w-10 h-10 bg-accent rounded-full flex items-center justify-center shadow-lg hover:bg-accent/80 transition-colors"
          >
            <Plus size={20} className="text-white" />
          </button>
        )}
      </div>

      {/* Drag overlay */}
      <DragOverlay>
        {activeTask ? (
          <div className="kanban-dragging">
            <KanbanCard task={activeTask} disabled />
          </div>
        ) : null}
      </DragOverlay>

      {/* Template picker modal */}
      {showTemplatePicker && (
        <TemplatePicker
          onClose={() => setShowTemplatePicker(false)}
          onTaskCreated={() => setShowTemplatePicker(false)}
        />
      )}
    </DndContext>
  )
}
