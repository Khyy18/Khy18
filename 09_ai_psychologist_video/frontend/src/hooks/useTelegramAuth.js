import { useState, useEffect } from 'react';
import { authTelegram, getToken, setToken } from '../utils/api';

/**
 * Хук авторизации через Telegram Mini App SDK.
 * Пытается получить initDataRaw из SDK, если доступен.
 * В dev-режиме (без Telegram) работает с fallback - используем существующий токен.
 */
export function useTelegramAuth() {
  const [user, setUser] = useState(null);
  const [token, setAuthToken] = useState(getToken());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function authenticate() {
      try {
        // Пытаемся получить initDataRaw из Telegram SDK
        let initDataRaw = null;

        try {
          const sdk = await import('@telegram-apps/sdk-react');
          if (sdk.retrieveLaunchParams) {
            const params = sdk.retrieveLaunchParams();
            initDataRaw = params?.initDataRaw;
          }
        } catch {
          // SDK недоступен - dev-режим
        }

        // Fallback: пробуем из window.Telegram.WebApp
        if (!initDataRaw && window.Telegram?.WebApp?.initData) {
          initDataRaw = window.Telegram.WebApp.initData;
        }

        if (initDataRaw) {
          const data = await authTelegram(initDataRaw);
          setAuthToken(data.token);
          setToken(data.token);
          setUser(data.user);
        } else if (getToken()) {
          // В dev-режиме используем сохраненный токен
          setAuthToken(getToken());
        }
      } catch (err) {
        setError(err.message || 'Ошибка авторизации');
      } finally {
        setLoading(false);
      }
    }

    authenticate();
  }, []);

  return { user, token, loading, error };
}
