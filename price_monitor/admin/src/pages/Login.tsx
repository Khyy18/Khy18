import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { setAdminToken } from '../api/client';

const BASE_URL = import.meta.env.VITE_API_URL || '/api';

export default function Login() {
  const [telegramId, setTelegramId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const initData = `user=${encodeURIComponent(JSON.stringify({ id: Number(telegramId) }))}`;

      const response = await fetch(`${BASE_URL}/auth/telegram`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({ detail: 'Ошибка сети' }));
        throw new Error(data.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();
      setAdminToken(data.access_token);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка авторизации');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-md bg-white rounded-xl shadow-lg p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Монитор Цен</h1>
          <p className="text-sm text-gray-500 mt-1">Вход в админ панель</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label htmlFor="telegramId" className="block text-sm font-medium text-gray-700 mb-1">
              Telegram ID
            </label>
            <input
              id="telegramId"
              type="text"
              value={telegramId}
              onChange={(e) => setTelegramId(e.target.value)}
              placeholder="Введите ваш Telegram ID"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-accent outline-none transition-colors"
              required
            />
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 px-4 py-2 rounded-lg">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !telegramId.trim()}
            className="w-full py-2.5 bg-accent text-white rounded-lg font-medium hover:bg-orange-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Вход...' : 'Войти'}
          </button>
        </form>

        <p className="text-xs text-gray-400 text-center mt-6">
          Доступ только для администраторов
        </p>
      </div>
    </div>
  );
}
