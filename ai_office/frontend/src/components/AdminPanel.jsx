import { useState, useEffect, useCallback } from 'react'
import { Bot, Settings, Link, Puzzle, BarChart3, Save, RefreshCw, TestTube } from 'lucide-react'

/**
 * Панель администратора AI Office
 * Доступна только для владельца (owner)
 * Табы: Агенты, Настройки, Интеграции, Плагины, Расходы
 */
export default function AdminPanel() {
  const [activeTab, setActiveTab] = useState('agents')

  const tabs = [
    { id: 'agents', label: 'Агенты', icon: Bot },
    { id: 'settings', label: 'Настройки', icon: Settings },
    { id: 'integrations', label: 'Интеграции', icon: Link },
    { id: 'plugins', label: 'Плагины', icon: Puzzle },
    { id: 'usage', label: 'Расходы', icon: BarChart3 },
  ]

  return (
    <div className="space-y-4">
      {/* Табы админ-панели */}
      <div className="flex gap-1 overflow-x-auto pb-2">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium whitespace-nowrap transition-all ${
                activeTab === tab.id
                  ? 'bg-accent/20 text-accent'
                  : 'bg-white/5 text-white/40 hover:text-white/60'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Контент табов */}
      <div className="animate-tab-transition">
        {activeTab === 'agents' && <AgentsTab />}
        {activeTab === 'settings' && <SettingsTab />}
        {activeTab === 'integrations' && <IntegrationsTab />}
        {activeTab === 'plugins' && <PluginsTab />}
        {activeTab === 'usage' && <UsageTab />}
      </div>
    </div>
  )
}

function AgentsTab() {
  const [agents, setAgents] = useState([])
  const [saving, setSaving] = useState({})

  useEffect(() => {
    fetch('/api/agents')
      .then(res => res.ok ? res.json() : [])
      .then(data => setAgents(data))
      .catch(() => {})
  }, [])

  const handlePromptChange = (idx, value) => {
    setAgents(prev => prev.map((a, i) => i === idx ? { ...a, system_prompt: value } : a))
  }

  const handleSave = async (agent) => {
    setSaving(prev => ({ ...prev, [agent.name]: true }))
    try {
      await fetch(`/api/admin/agents/${agent.name}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_prompt: agent.system_prompt }),
      })
    } catch (e) { /* ignore */ }
    setSaving(prev => ({ ...prev, [agent.name]: false }))
  }

  return (
    <div className="space-y-3">
      <h3 className="text-white/70 text-sm font-medium">Управление агентами</h3>
      {agents.map((agent, idx) => (
        <div key={agent.name || idx} className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-white text-sm font-medium">{agent.name}</span>
            <span className="text-white/40 text-xs">{agent.role}</span>
          </div>
          <textarea
            value={agent.system_prompt || ''}
            onChange={(e) => handlePromptChange(idx, e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-xl p-3 text-white/80 text-xs resize-y min-h-[80px] focus:outline-none focus:border-accent/50"
            placeholder="Системный промпт агента..."
          />
          <button
            onClick={() => handleSave(agent)}
            disabled={saving[agent.name]}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/20 text-accent rounded-lg text-xs font-medium hover:bg-accent/30 transition-all disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5" />
            {saving[agent.name] ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      ))}
    </div>
  )
}

function SettingsTab() {
  const [settings, setSettings] = useState({
    proactive_enabled: 'true',
    daily_budget_usd: '10.0',
    llm_priority: 'balanced',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch('/api/admin/settings')
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        if (Array.isArray(data)) {
          const map = {}
          data.forEach(s => { map[s.key] = s.value })
          setSettings(prev => ({ ...prev, ...map }))
        }
      })
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetch('/api/admin/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      })
    } catch (e) { /* ignore */ }
    setSaving(false)
  }

  return (
    <div className="space-y-4">
      <h3 className="text-white/70 text-sm font-medium">Системные настройки</h3>

      <div className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-4">
        {/* Proactive */}
        <div className="flex items-center justify-between">
          <div>
            <span className="text-white text-sm">Проактивное поведение</span>
            <p className="text-white/40 text-xs">Агенты предлагают задачи самостоятельно</p>
          </div>
          <button
            onClick={() => setSettings(prev => ({
              ...prev,
              proactive_enabled: prev.proactive_enabled === 'true' ? 'false' : 'true'
            }))}
            className={`w-10 h-5 rounded-full transition-all ${
              settings.proactive_enabled === 'true' ? 'bg-accent' : 'bg-white/20'
            }`}
          >
            <div className={`w-4 h-4 bg-white rounded-full transition-all ${
              settings.proactive_enabled === 'true' ? 'translate-x-5' : 'translate-x-0.5'
            }`} />
          </button>
        </div>

        {/* Daily Budget */}
        <div>
          <label className="text-white text-sm block mb-1">Дневной бюджет (USD)</label>
          <input
            type="number"
            step="0.5"
            value={settings.daily_budget_usd}
            onChange={(e) => setSettings(prev => ({ ...prev, daily_budget_usd: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-accent/50"
          />
        </div>

        {/* LLM Priority */}
        <div>
          <label className="text-white text-sm block mb-1">Приоритет LLM</label>
          <select
            value={settings.llm_priority}
            onChange={(e) => setSettings(prev => ({ ...prev, llm_priority: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-accent/50"
          >
            <option value="speed">Скорость</option>
            <option value="balanced">Баланс</option>
            <option value="quality">Качество</option>
          </select>
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-1.5 px-4 py-2 bg-accent/20 text-accent rounded-xl text-sm font-medium hover:bg-accent/30 transition-all disabled:opacity-50"
      >
        <Save className="w-4 h-4" />
        {saving ? 'Сохранение...' : 'Сохранить настройки'}
      </button>
    </div>
  )
}

function IntegrationsTab() {
  const [linearKey, setLinearKey] = useState('')
  const [notionKey, setNotionKey] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)

  const handleTest = async (type, key) => {
    setTesting(true)
    setTestResult(null)
    try {
      const resp = await fetch('/api/admin/integrations/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ integration_type: type, api_key: key }),
      })
      const data = await resp.json()
      setTestResult(data)
    } catch (e) {
      setTestResult({ success: false, message: 'Ошибка сети' })
    }
    setTesting(false)
  }

  return (
    <div className="space-y-4">
      <h3 className="text-white/70 text-sm font-medium">Внешние интеграции</h3>

      {/* Linear */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-3">
        <span className="text-white text-sm font-medium">Linear</span>
        <input
          type="password"
          value={linearKey}
          onChange={(e) => setLinearKey(e.target.value)}
          placeholder="LINEAR_API_KEY"
          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-accent/50"
        />
        <button
          onClick={() => handleTest('linear', linearKey)}
          disabled={testing || !linearKey}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/20 text-blue-400 rounded-lg text-xs font-medium hover:bg-blue-500/30 transition-all disabled:opacity-50"
        >
          <TestTube className="w-3.5 h-3.5" />
          {testing ? 'Проверка...' : 'Проверить подключение'}
        </button>
      </div>

      {/* Notion */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-3">
        <span className="text-white text-sm font-medium">Notion</span>
        <input
          type="password"
          value={notionKey}
          onChange={(e) => setNotionKey(e.target.value)}
          placeholder="NOTION_API_KEY"
          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-accent/50"
        />
        <button
          onClick={() => handleTest('notion', notionKey)}
          disabled={testing || !notionKey}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/20 text-blue-400 rounded-lg text-xs font-medium hover:bg-blue-500/30 transition-all disabled:opacity-50"
        >
          <TestTube className="w-3.5 h-3.5" />
          {testing ? 'Проверка...' : 'Проверить подключение'}
        </button>
      </div>

      {/* Результат теста */}
      {testResult && (
        <div className={`p-3 rounded-xl text-xs ${
          testResult.success
            ? 'bg-green-500/10 border border-green-500/20 text-green-400'
            : 'bg-red-500/10 border border-red-500/20 text-red-400'
        }`}>
          {testResult.message}
        </div>
      )}
    </div>
  )
}

function PluginsTab() {
  const [plugins, setPlugins] = useState([])
  const [reloading, setReloading] = useState(false)

  useEffect(() => {
    fetch('/api/plugins')
      .then(res => res.ok ? res.json() : [])
      .then(data => setPlugins(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  const handleReload = async () => {
    setReloading(true)
    try {
      await fetch('/api/plugins/reload', { method: 'POST' })
      const resp = await fetch('/api/plugins')
      const data = await resp.json()
      setPlugins(Array.isArray(data) ? data : [])
    } catch (e) { /* ignore */ }
    setReloading(false)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white/70 text-sm font-medium">Загруженные плагины</h3>
        <button
          onClick={handleReload}
          disabled={reloading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 text-white/60 rounded-lg text-xs font-medium hover:bg-white/10 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${reloading ? 'animate-spin' : ''}`} />
          Перезагрузить
        </button>
      </div>

      {plugins.length === 0 ? (
        <div className="text-white/30 text-sm text-center py-6">
          Плагины не загружены
        </div>
      ) : (
        <div className="space-y-2">
          {plugins.map((plugin, idx) => (
            <div key={idx} className="bg-white/5 border border-white/10 rounded-2xl p-3 flex items-center justify-between">
              <div>
                <span className="text-white text-sm">{plugin.display_name || plugin.name}</span>
                <p className="text-white/40 text-xs">{plugin.role || ''}</p>
              </div>
              <div className="flex gap-1">
                {(plugin.tools || []).map((tool, ti) => (
                  <span key={ti} className="px-2 py-0.5 bg-accent/10 text-accent text-[10px] rounded-full">
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function UsageTab() {
  const [usage, setUsage] = useState([])

  useEffect(() => {
    fetch('/api/usage?limit=50')
      .then(res => res.ok ? res.json() : { items: [] })
      .then(data => setUsage(data.items || []))
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-4">
      <h3 className="text-white/70 text-sm font-medium">Использование токенов</h3>

      {usage.length === 0 ? (
        <div className="text-white/30 text-sm text-center py-6">
          Нет данных об использовании
        </div>
      ) : (
        <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left text-white/50 px-3 py-2">Агент</th>
                <th className="text-left text-white/50 px-3 py-2">Модель</th>
                <th className="text-right text-white/50 px-3 py-2">Токены</th>
                <th className="text-right text-white/50 px-3 py-2">Стоимость</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((row, idx) => (
                <tr key={idx} className="border-b border-white/5">
                  <td className="px-3 py-2 text-white">{row.agent_name}</td>
                  <td className="px-3 py-2 text-white/60">{row.model}</td>
                  <td className="px-3 py-2 text-right text-white/60">
                    {(row.prompt_tokens || 0) + (row.completion_tokens || 0)}
                  </td>
                  <td className="px-3 py-2 text-right text-accent">
                    ${(row.estimated_cost_usd || 0).toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
