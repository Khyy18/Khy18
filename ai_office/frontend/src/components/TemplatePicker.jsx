import { useState, useEffect } from 'react'
import { X, Code, Bug, Palette, Shield, Rocket, Search, Calculator, ClipboardList } from 'lucide-react'

const ICON_MAP = {
  code: Code,
  bug: Bug,
  palette: Palette,
  shield: Shield,
  rocket: Rocket,
  search: Search,
  calculator: Calculator,
  clipboard: ClipboardList,
}

/**
 * Модальное окно выбора шаблона задачи
 */
export default function TemplatePicker({ onClose, onTaskCreated }) {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(null)

  useEffect(() => {
    fetchTemplates()
  }, [])

  const fetchTemplates = async () => {
    try {
      const res = await fetch('/api/templates')
      if (res.ok) {
        const data = await res.json()
        setTemplates(data)
      }
    } catch (err) {
      console.error('Failed to fetch templates:', err)
    } finally {
      setLoading(false)
    }
  }

  const createFromTemplate = async (templateId) => {
    setCreating(templateId)
    try {
      const res = await fetch(`/api/tasks/from-template/${templateId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      if (res.ok) {
        onTaskCreated?.()
        onClose?.()
      }
    } catch (err) {
      console.error('Failed to create task from template:', err)
    } finally {
      setCreating(null)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card/95 backdrop-blur-xl border border-white/10 rounded-2xl p-4 w-full max-w-md max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-medium">Создать задачу</h3>
          <button
            onClick={onClose}
            className="text-white/40 hover:text-white/70 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Template grid */}
        {loading ? (
          <div className="text-white/40 text-sm text-center py-8 animate-pulse">
            Загрузка шаблонов...
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {templates.map((tmpl) => {
              const IconComponent = ICON_MAP[tmpl.icon] || ClipboardList
              return (
                <button
                  key={tmpl.id}
                  onClick={() => createFromTemplate(tmpl.id)}
                  disabled={creating === tmpl.id}
                  className="flex flex-col items-center gap-2 p-4 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl hover:bg-white/10 hover:border-accent/30 transition-all disabled:opacity-50"
                >
                  <IconComponent size={24} className="text-accent" />
                  <span className="text-white/80 text-xs text-center leading-tight">
                    {tmpl.name}
                  </span>
                  <span className="text-white/30 text-[10px]">
                    {tmpl.category}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
