import { useState, useEffect } from 'react'
import { Palette, Save, Eye } from 'lucide-react'

/**
 * Панель настройки брендинга
 * Настройка: название, лого, цвет, имена агентов, welcome message, custom CSS
 */
export default function BrandingPanel() {
  const [config, setConfig] = useState({
    company_name: '',
    logo_url: '',
    accent_color: '#6366f1',
    agent_names: {},
    enabled_agents: [],
    welcome_message: '',
    custom_css: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  useEffect(() => {
    fetch('/api/branding')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data) setConfig(prev => ({ ...prev, ...data }))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetch('/api/branding', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
    } catch (e) { /* ignore */ }
    setSaving(false)
  }

  const handleAgentNameChange = (key, value) => {
    setConfig(prev => ({
      ...prev,
      agent_names: { ...prev.agent_names, [key]: value },
    }))
  }

  const handleToggleAgent = (agentName) => {
    setConfig(prev => {
      const enabled = prev.enabled_agents || []
      if (enabled.includes(agentName)) {
        return { ...prev, enabled_agents: enabled.filter(a => a !== agentName) }
      }
      return { ...prev, enabled_agents: [...enabled, agentName] }
    })
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
          <Palette className="w-4 h-4" />
          Брендинг
        </h3>
        <div className="text-white/30 text-sm text-center py-6">Загрузка...</div>
      </div>
    )
  }

  const allAgents = ['Alice', 'Sam', 'Max', 'Eva', 'Leo', 'Nova', 'Iris', 'Oscar']

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white/70 text-sm font-medium flex items-center gap-2">
          <Palette className="w-4 h-4" />
          Брендинг
        </h3>
        <button
          onClick={() => setShowPreview(!showPreview)}
          className="flex items-center gap-1 px-2 py-1 bg-white/5 text-white/60 rounded-lg text-[10px] hover:bg-white/10 transition-all"
        >
          <Eye className="w-3 h-3" />
          {showPreview ? 'Скрыть' : 'Превью'}
        </button>
      </div>

      {/* Live Preview */}
      {showPreview && (
        <div
          className="border border-white/10 rounded-2xl p-4 space-y-2"
          style={{ backgroundColor: 'rgba(255,255,255,0.03)' }}
        >
          <div className="flex items-center gap-3">
            {config.logo_url && (
              <img
                src={config.logo_url}
                alt="Logo"
                className="w-8 h-8 rounded-lg object-cover"
                onError={(e) => { e.target.style.display = 'none' }}
              />
            )}
            <span className="text-white font-semibold" style={{ color: config.accent_color }}>
              {config.company_name || 'AI Office'}
            </span>
          </div>
          {config.welcome_message && (
            <p className="text-white/50 text-xs">{config.welcome_message}</p>
          )}
        </div>
      )}

      {/* Form */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-4">
        {/* Company Name */}
        <div>
          <label className="text-white text-sm block mb-1">Название компании</label>
          <input
            type="text"
            value={config.company_name}
            onChange={(e) => setConfig(prev => ({ ...prev, company_name: e.target.value }))}
            placeholder="AI Office"
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-accent/50"
          />
        </div>

        {/* Logo URL */}
        <div>
          <label className="text-white text-sm block mb-1">URL логотипа</label>
          <input
            type="text"
            value={config.logo_url}
            onChange={(e) => setConfig(prev => ({ ...prev, logo_url: e.target.value }))}
            placeholder="https://example.com/logo.png"
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-accent/50"
          />
          {config.logo_url && (
            <img
              src={config.logo_url}
              alt="Preview"
              className="mt-2 w-12 h-12 rounded-lg object-cover"
              onError={(e) => { e.target.style.display = 'none' }}
            />
          )}
        </div>

        {/* Accent Color */}
        <div>
          <label className="text-white text-sm block mb-1">Акцентный цвет</label>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={config.accent_color}
              onChange={(e) => setConfig(prev => ({ ...prev, accent_color: e.target.value }))}
              className="w-10 h-10 rounded-lg border border-white/10 cursor-pointer"
            />
            <span className="text-white/50 text-xs">{config.accent_color}</span>
          </div>
        </div>

        {/* Agent Names */}
        <div>
          <label className="text-white text-sm block mb-2">Имена агентов</label>
          <div className="space-y-2">
            {allAgents.map((agent) => (
              <div key={agent} className="flex items-center gap-2">
                <span className="text-white/50 text-xs w-14">{agent}</span>
                <input
                  type="text"
                  value={config.agent_names?.[agent] || ''}
                  onChange={(e) => handleAgentNameChange(agent, e.target.value)}
                  placeholder={agent}
                  className="flex-1 bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-white text-xs focus:outline-none focus:border-accent/50"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Enabled Agents */}
        <div>
          <label className="text-white text-sm block mb-2">Активные агенты</label>
          <div className="flex flex-wrap gap-2">
            {allAgents.map((agent) => (
              <label key={agent} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(config.enabled_agents || []).includes(agent)}
                  onChange={() => handleToggleAgent(agent)}
                  className="w-3.5 h-3.5 rounded border-white/20 bg-white/5 text-accent focus:ring-accent/50"
                />
                <span className="text-white/60 text-xs">{agent}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Welcome Message */}
        <div>
          <label className="text-white text-sm block mb-1">Приветственное сообщение</label>
          <textarea
            value={config.welcome_message}
            onChange={(e) => setConfig(prev => ({ ...prev, welcome_message: e.target.value }))}
            placeholder="Добро пожаловать в AI Office!"
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm resize-y min-h-[60px] focus:outline-none focus:border-accent/50"
          />
        </div>

        {/* Custom CSS */}
        <div>
          <label className="text-white text-sm block mb-1">Custom CSS</label>
          <textarea
            value={config.custom_css}
            onChange={(e) => setConfig(prev => ({ ...prev, custom_css: e.target.value }))}
            placeholder=":root { --accent: #6366f1; }"
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-xs resize-y min-h-[80px] focus:outline-none focus:border-accent/50 font-mono"
          />
        </div>
      </div>

      {/* Save Button */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-1.5 px-4 py-2 bg-accent/20 text-accent rounded-xl text-sm font-medium hover:bg-accent/30 transition-all disabled:opacity-50"
      >
        <Save className="w-4 h-4" />
        {saving ? 'Сохранение...' : 'Сохранить'}
      </button>
    </div>
  )
}
