import { useState, useEffect } from 'react'
import { Copy, Share2, Users, CheckCircle } from 'lucide-react'

/**
 * Секция приглашений - реферальная ссылка, статистика, кнопка поделиться
 */
export default function InviteSection() {
  const [referralCode, setReferralCode] = useState(null)
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    // Загружаем реферальный код
    fetch('/api/referral/code')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => setReferralCode(data.code || data.referral_code))
      .catch(err => setError(err.message))

    // Загружаем статистику рефералов
    fetch('/api/referral/stats')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => setStats(data))
      .catch(err => setError(err.message))
  }, [])

  const referralLink = referralCode
    ? `https://t.me/ai_office_bot?start=ref_${referralCode}`
    : ''

  const handleCopy = async () => {
    if (!referralLink) return
    try {
      await navigator.clipboard.writeText(referralLink)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback
      const input = document.createElement('input')
      input.value = referralLink
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleShare = () => {
    const text = encodeURIComponent('Присоединяйся к AI Office - твоя карманная компания с ИИ-агентами!')
    const url = encodeURIComponent(referralLink)
    window.open(`https://t.me/share/url?url=${url}&text=${text}`, '_blank')
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-4">
        <p className="text-red-400 text-sm">Ошибка загрузки: {error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Заголовок */}
      <div className="text-center">
        <h2 className="text-white text-lg font-semibold">Пригласить друзей</h2>
        <p className="text-white/50 text-sm mt-1">
          Получайте бонусы за каждого приглашенного
        </p>
      </div>

      {/* Реферальная ссылка */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
        <label className="text-white/60 text-xs block mb-2">Ваша реферальная ссылка</label>
        <div className="flex items-center gap-2">
          <div className="flex-1 bg-white/5 rounded-xl px-3 py-2 overflow-hidden">
            <p className="text-white/80 text-sm truncate">
              {referralLink || 'Загрузка...'}
            </p>
          </div>
          <button
            onClick={handleCopy}
            disabled={!referralLink}
            className="p-2 bg-accent/20 hover:bg-accent/30 rounded-xl transition-colors disabled:opacity-50"
          >
            {copied ? (
              <CheckCircle className="w-5 h-5 text-green-400" />
            ) : (
              <Copy className="w-5 h-5 text-accent" />
            )}
          </button>
        </div>
        {copied && (
          <p className="text-green-400 text-xs mt-2">Скопировано!</p>
        )}
      </div>

      {/* Кнопка поделиться */}
      <button
        onClick={handleShare}
        disabled={!referralLink}
        className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white font-medium py-3 px-4 rounded-2xl transition-all disabled:opacity-50"
      >
        <Share2 className="w-5 h-5" />
        Поделиться
      </button>

      {/* Статистика рефералов */}
      {stats && (
        <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
          <h3 className="text-white font-medium text-sm mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-accent" />
            Статистика рефералов
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white/5 rounded-xl p-3 text-center">
              <p className="text-white text-lg font-semibold">{stats.direct_referrals ?? 0}</p>
              <p className="text-white/50 text-xs">Уровень 1</p>
            </div>
            <div className="bg-white/5 rounded-xl p-3 text-center">
              <p className="text-white text-lg font-semibold">{stats.level_2 ?? 0}</p>
              <p className="text-white/50 text-xs">Уровень 2</p>
            </div>
            <div className="bg-white/5 rounded-xl p-3 text-center">
              <p className="text-white text-lg font-semibold">{stats.level_3 ?? 0}</p>
              <p className="text-white/50 text-xs">Уровень 3</p>
            </div>
            <div className="bg-white/5 rounded-xl p-3 text-center">
              <p className="text-accent text-lg font-semibold">{stats.total_bonus ?? 0}</p>
              <p className="text-white/50 text-xs">Бонус</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
