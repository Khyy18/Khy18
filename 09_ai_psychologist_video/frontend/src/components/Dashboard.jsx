import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTelegramAuth } from '../hooks/useTelegramAuth';
import { getProfile, getSessions, createSession, getReferralLink } from '../utils/api';

/**
 * Главный экран приложения.
 * Показывает баланс, кнопку старта сессии, историю сессий.
 */
export default function Dashboard() {
  const navigate = useNavigate();
  const { loading: authLoading } = useTelegramAuth();

  const [profile, setProfile] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [referralLink, setReferralLink] = useState('');

  const RATE_PER_MINUTE = profile?.rate_per_minute ? Number(profile.rate_per_minute) : 5;

  useEffect(() => {
    if (authLoading) return;

    async function loadData() {
      try {
        const [profileData, sessionsData] = await Promise.all([
          getProfile().catch(() => null),
          getSessions().catch(() => []),
        ]);
        if (profileData) setProfile(profileData);
        if (Array.isArray(sessionsData)) setSessions(sessionsData);
        // Load referral link
        getReferralLink()
          .then((data) => setReferralLink(data.link || ''))
          .catch(() => {});
      } catch {
        // В dev-режиме API может быть недоступен
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [authLoading]);

  async function handleStartSession() {
    setStarting(true);
    try {
      const session = await createSession();
      navigate(`/call/${session.id}`);
    } catch {
      alert('Не удалось начать сессию');
    } finally {
      setStarting(false);
    }
  }

  // Форматирование длительности в MM:SS
  function formatDuration(seconds) {
    if (!seconds) return '00:00';
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }

  // Форматирование даты
  function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  const balance = profile?.balance ?? 0;
  const canStart = balance >= RATE_PER_MINUTE;

  if (loading || authLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--tg-theme-bg-color)]">
        <div className="animate-spin w-8 h-8 border-4 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] p-4 pb-20">
      {/* Заголовок */}
      <header className="text-center mb-6">
        <h1 className="text-2xl font-bold">AI Психолог</h1>
        <p className="text-[var(--tg-theme-hint-color)] text-sm mt-1">
          Видеоконсультация с AI-психологом
        </p>
      </header>

      {/* Карточка баланса */}
      <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-2xl p-6 mb-6 text-center">
        <p className="text-[var(--tg-theme-hint-color)] text-sm mb-1">Ваш баланс</p>
        <p className="text-4xl font-bold">
          {balance} <span className="text-2xl">&#8381;</span>
        </p>
        <p className="text-[var(--tg-theme-hint-color)] text-xs mt-2">
          {RATE_PER_MINUTE} &#8381; / мин
        </p>
        {profile?.subscription_plan && profile.subscription_plan !== 'free' && (
          <span className="inline-block mt-2 text-xs bg-[var(--tg-theme-button-color)] text-white px-3 py-1 rounded-full">
            {profile.subscription_plan}
          </span>
        )}
      </div>

      {/* Кнопка начала сессии */}
      <div className="mb-6">
        <button
          onClick={handleStartSession}
          disabled={!canStart || starting}
          className={`w-full py-4 rounded-xl text-white font-semibold text-lg transition-all ${
            canStart
              ? 'bg-[var(--tg-theme-button-color)] hover:opacity-90 active:scale-[0.98]'
              : 'bg-gray-400 cursor-not-allowed'
          }`}
        >
          {starting ? 'Подключение...' : 'Начать сессию'}
        </button>
        {!canStart && (
          <p className="text-center text-red-500 text-sm mt-2">
            Пополните баланс для начала сессии
          </p>
        )}
      </div>

      {/* Кнопка пополнения */}
      <button
        onClick={() => navigate('/topup')}
        className="w-full py-3 rounded-xl border-2 border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-medium mb-6 hover:bg-[var(--tg-theme-button-color)] hover:text-white transition-colors"
      >
        Пополнить баланс
      </button>

      {/* Реферальная секция */}
      {referralLink && (
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 mb-6">
          <p className="font-semibold mb-2">Пригласить друга</p>
          <p className="text-[var(--tg-theme-hint-color)] text-xs mb-2">
            Поделитесь ссылкой и получите бонус
          </p>
          <div className="bg-[var(--tg-theme-bg-color)] rounded-lg p-2 text-xs break-all text-[var(--tg-theme-hint-color)]">
            {referralLink}
          </div>
        </div>
      )}

      {/* История сессий */}
      {sessions.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">История сессий</h2>
          <div className="space-y-3">
            {sessions.map((session, idx) => (
              <div
                key={session.id || idx}
                className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 flex justify-between items-center"
              >
                <div>
                  <p className="font-medium">{formatDate(session.started_at)}</p>
                  <p className="text-[var(--tg-theme-hint-color)] text-sm">
                    {formatDuration(session.duration)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-semibold">
                    -{session.total_cost || 0} &#8381;
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
