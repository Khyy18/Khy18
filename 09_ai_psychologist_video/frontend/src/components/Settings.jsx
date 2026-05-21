import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getProfile, getSessions } from '../utils/api';

/**
 * Экран настроек.
 * Показывает информацию о пользователе, статистику, ссылку на поддержку.
 */
export default function Settings() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [stats, setStats] = useState({ totalSessions: 0, totalTime: 0, totalSpent: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [profileData, sessionsData] = await Promise.all([
          getProfile().catch(() => null),
          getSessions().catch(() => []),
        ]);
        if (profileData) setProfile(profileData);
        if (Array.isArray(sessionsData)) {
          const totalSessions = sessionsData.length;
          const totalTime = sessionsData.reduce((acc, s) => acc + (s.duration || 0), 0);
          const totalSpent = sessionsData.reduce((acc, s) => acc + (s.total_cost || 0), 0);
          setStats({ totalSessions, totalTime, totalSpent });
        }
      } catch {
        // silently handle
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  function formatTime(seconds) {
    if (!seconds) return '0 мин';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h} ч ${m} мин`;
    return `${m} мин`;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--tg-theme-bg-color)]">
        <div className="animate-spin w-8 h-8 border-4 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] p-4 pb-20">
      {/* Заголовок */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1 text-[var(--tg-theme-button-color)] mb-4"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Назад
      </button>

      <h1 className="text-2xl font-bold mb-6">Настройки</h1>

      {/* Информация о пользователе */}
      <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 mb-6">
        <p className="font-semibold text-lg">{profile?.name || 'Пользователь'}</p>
        <p className="text-[var(--tg-theme-hint-color)] text-sm">
          {profile?.telegram_id ? `ID: ${profile.telegram_id}` : ''}
        </p>
      </div>

      {/* Статистика */}
      <h2 className="font-semibold text-lg mb-3">Статистика</h2>
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-3 text-center">
          <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Сессии</p>
          <p className="font-bold text-lg">{stats.totalSessions}</p>
        </div>
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-3 text-center">
          <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Время</p>
          <p className="font-bold text-lg">{formatTime(stats.totalTime)}</p>
        </div>
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-3 text-center">
          <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Потрачено</p>
          <p className="font-bold text-lg">{stats.totalSpent} &#8381;</p>
        </div>
      </div>

      {/* Язык (заглушка) */}
      <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 mb-4 flex justify-between items-center opacity-50">
        <div>
          <p className="font-medium">Язык</p>
          <p className="text-[var(--tg-theme-hint-color)] text-sm">Русский</p>
        </div>
        <span className="text-[var(--tg-theme-hint-color)] text-xs">Скоро</span>
      </div>

      {/* Поддержка */}
      <a
        href="https://t.me/support"
        target="_blank"
        rel="noopener noreferrer"
        className="block w-full py-4 rounded-xl border-2 border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-medium text-center hover:bg-[var(--tg-theme-button-color)] hover:text-white transition-colors"
      >
        Связаться с поддержкой
      </a>
    </div>
  );
}
