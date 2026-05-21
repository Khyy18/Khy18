import React, { useState, useEffect } from 'react';
import { getAdminStats, getAdminSessions, getAdminUsers } from '../utils/api';

/**
 * Админ-панель.
 * Ключ доступа вводится через поле ввода и сохраняется в sessionStorage.
 */
export default function Admin() {
  const [adminKey, setAdminKey] = useState(() => sessionStorage.getItem('admin_key') || '');
  const [keyInput, setKeyInput] = useState('');
  const [stats, setStats] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('stats'); // stats | sessions | users

  useEffect(() => {
    if (adminKey) {
      loadData();
    }
  }, [adminKey]);

  function handleKeySubmit(e) {
    e.preventDefault();
    if (!keyInput.trim()) return;
    sessionStorage.setItem('admin_key', keyInput.trim());
    setAdminKey(keyInput.trim());
  }

  function handleLogout() {
    sessionStorage.removeItem('admin_key');
    setAdminKey('');
    setKeyInput('');
    setStats(null);
    setSessions([]);
    setUsers([]);
  }

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [statsData, sessionsData, usersData] = await Promise.all([
        getAdminStats(adminKey),
        getAdminSessions(adminKey, 1),
        getAdminUsers(adminKey, 1),
      ]);
      setStats(statsData);
      setSessions(sessionsData.items || sessionsData || []);
      setUsers(usersData.items || usersData || []);
    } catch (err) {
      setError('Ошибка загрузки данных. Проверьте ключ доступа.');
      sessionStorage.removeItem('admin_key');
      setAdminKey('');
    } finally {
      setLoading(false);
    }
  }

  // Форма ввода ключа, если ключ не задан
  if (!adminKey) {
    return (
      <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] flex items-center justify-center p-4">
        <form onSubmit={handleKeySubmit} className="w-full max-w-sm space-y-4">
          <h1 className="text-xl font-bold text-center">Админ-панель</h1>
          <p className="text-[var(--tg-theme-hint-color)] text-sm text-center">
            Введите ключ доступа для входа
          </p>
          <input
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="Ключ доступа"
            className="w-full px-4 py-3 rounded-xl bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)] border-none outline-none"
            autoFocus
          />
          {error && <p className="text-red-500 text-sm text-center">{error}</p>}
          <button
            type="submit"
            className="w-full py-3 rounded-xl bg-[var(--tg-theme-button-color)] text-white font-medium"
          >
            Войти
          </button>
        </form>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--tg-theme-bg-color)]">
        <div className="animate-spin w-8 h-8 border-4 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] flex items-center justify-center p-4">
        <p className="text-red-500">{error}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Админ-панель</h1>
        <button
          onClick={handleLogout}
          className="text-sm text-[var(--tg-theme-hint-color)] underline"
        >
          Выйти
        </button>
      </div>

      {/* Карточки статистики */}
      {stats && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-3 text-center">
            <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Пользователи</p>
            <p className="font-bold text-lg">{stats.total_users || 0}</p>
          </div>
          <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-3 text-center">
            <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Сессии</p>
            <p className="font-bold text-lg">{stats.total_sessions || 0}</p>
          </div>
          <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-3 text-center">
            <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Доход</p>
            <p className="font-bold text-lg">{stats.total_revenue || 0} &#8381;</p>
          </div>
        </div>
      )}

      {/* Табы */}
      <div className="flex gap-2 mb-4">
        {['stats', 'sessions', 'users'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t
                ? 'bg-[var(--tg-theme-button-color)] text-white'
                : 'bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]'
            }`}
          >
            {t === 'stats' ? 'Обзор' : t === 'sessions' ? 'Сессии' : 'Пользователи'}
          </button>
        ))}
      </div>

      {/* Контент таба: Сессии */}
      {tab === 'sessions' && (
        <div className="space-y-3">
          {sessions.length === 0 && (
            <p className="text-[var(--tg-theme-hint-color)] text-center">Нет данных</p>
          )}
          {sessions.map((session, idx) => (
            <div
              key={session.id || idx}
              className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4"
            >
              <div className="flex justify-between items-center">
                <p className="font-medium text-sm">ID: {session.id}</p>
                <p className="text-[var(--tg-theme-hint-color)] text-xs">
                  {session.duration ? `${Math.floor(session.duration / 60)} мин` : '-'}
                </p>
              </div>
              <p className="text-[var(--tg-theme-hint-color)] text-xs mt-1">
                User: {session.user_id} | Cost: {session.total_cost || 0} &#8381;
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Контент таба: Пользователи */}
      {tab === 'users' && (
        <div className="space-y-3">
          {users.length === 0 && (
            <p className="text-[var(--tg-theme-hint-color)] text-center">Нет данных</p>
          )}
          {users.map((user, idx) => (
            <div
              key={user.id || idx}
              className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 flex justify-between items-center"
            >
              <div>
                <p className="font-medium text-sm">{user.name || `User #${user.id}`}</p>
                <p className="text-[var(--tg-theme-hint-color)] text-xs">
                  TG: {user.telegram_id || '-'}
                </p>
              </div>
              <p className="font-bold">{user.balance || 0} &#8381;</p>
            </div>
          ))}
        </div>
      )}

      {/* Контент таба: Обзор (stats already shown in cards) */}
      {tab === 'stats' && stats && (
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4">
          <p className="text-sm text-[var(--tg-theme-hint-color)]">
            Подробная статистика отображается в карточках выше.
          </p>
        </div>
      )}
    </div>
  );
}
