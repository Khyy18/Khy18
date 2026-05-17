import { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Mail, Bell, Users } from 'lucide-react'
import { Toggle } from '../components/ui/Input'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import { useApi } from '../hooks/useApi'
import { useToast } from '../components/ui/Toast'

export default function Settings() {
  const [smtp, setSmtp] = useState({ host: '', port: '587', user: '', password: '' })
  const [notifications, setNotifications] = useState({ email: true, telegram: false, slack: false })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const { get, post } = useApi()
  const toast = useToast()

  useEffect(() => {
    const load = async () => {
      try {
        const settings = await get('/api/settings').catch(() => null)
        if (settings?.smtp) {
          setSmtp(settings.smtp)
        }
        if (settings?.notifications) {
          setNotifications(settings.notifications)
        }
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [get])

  const handleSaveSmtp = async () => {
    setSaving(true)
    try {
      await post('/api/settings/smtp', smtp)
      toast('SMTP settings saved', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleTestSmtp = async () => {
    setTesting(true)
    try {
      await post('/api/settings/smtp/test', smtp)
      toast('Test email sent successfully', 'success')
    } catch (err) {
      toast(err.message || 'Test failed', 'error')
    } finally {
      setTesting(false)
    }
  }

  const handleSaveNotifications = async () => {
    try {
      await post('/api/settings/notifications', notifications)
      toast('Notification preferences saved', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  if (loading) return <LoadingSkeleton rows={4} />

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-white/50 text-sm mt-1">Configure your account preferences</p>
      </div>

      {/* SMTP Configuration */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-4">
          <Mail className="w-4 h-4 text-accent" />
          <h3 className="text-sm font-medium text-white/70">SMTP Configuration</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-white/70 mb-1">Host</label>
            <input
              value={smtp.host}
              onChange={e => setSmtp(s => ({ ...s, host: e.target.value }))}
              placeholder="smtp.gmail.com"
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Port</label>
            <input
              type="number"
              value={smtp.port}
              onChange={e => setSmtp(s => ({ ...s, port: e.target.value }))}
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">User</label>
            <input
              value={smtp.user}
              onChange={e => setSmtp(s => ({ ...s, user: e.target.value }))}
              placeholder="user@gmail.com"
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Password</label>
            <input
              type="password"
              value={smtp.password}
              onChange={e => setSmtp(s => ({ ...s, password: e.target.value }))}
              placeholder="App password"
              className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50"
            />
          </div>
        </div>
        <div className="flex gap-3 mt-4">
          <button
            onClick={handleSaveSmtp}
            disabled={saving}
            className="px-4 py-2 bg-accent hover:bg-accent/80 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
          <button
            onClick={handleTestSmtp}
            disabled={testing}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {testing ? 'Testing...' : 'Send Test Email'}
          </button>
        </div>
      </div>

      {/* Notifications */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-4">
          <Bell className="w-4 h-4 text-secondary" />
          <h3 className="text-sm font-medium text-white/70">Notification Preferences</h3>
        </div>
        <div className="space-y-4">
          <Toggle
            label="Email notifications"
            checked={notifications.email}
            onChange={(e) => setNotifications(n => ({ ...n, email: e.target.checked }))}
          />
          <Toggle
            label="Telegram notifications"
            checked={notifications.telegram}
            onChange={(e) => setNotifications(n => ({ ...n, telegram: e.target.checked }))}
          />
          <Toggle
            label="Slack notifications"
            checked={notifications.slack}
            onChange={(e) => setNotifications(n => ({ ...n, slack: e.target.checked }))}
          />
        </div>
        <button
          onClick={handleSaveNotifications}
          className="mt-4 px-4 py-2 bg-accent hover:bg-accent/80 text-white rounded-lg text-sm font-medium transition-colors"
        >
          Save Preferences
        </button>
      </div>

      {/* Team (placeholder) */}
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-4">
          <Users className="w-4 h-4 text-white/50" />
          <h3 className="text-sm font-medium text-white/70">Team Management</h3>
        </div>
        <div className="text-center py-8">
          <p className="text-white/30 text-sm">Team management coming soon</p>
        </div>
      </div>
    </div>
  )
}
