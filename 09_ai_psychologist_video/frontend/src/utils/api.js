// Базовый URL - пустой для проксированных запросов через Vite, или из env для production
const BASE_URL = import.meta.env.VITE_API_URL || '';

export function getToken() {
  return localStorage.getItem('auth_token');
}

export function setToken(token) {
  localStorage.setItem('auth_token', token);
}

export function clearToken() {
  localStorage.removeItem('auth_token');
}

/**
 * Базовый fetch-обертка с JWT-авторизацией
 */
async function request(path, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    try {
      error.data = await response.json();
    } catch {
      // ответ без JSON-тела
    }
    throw error;
  }

  return response.json();
}

/**
 * Авторизация через Telegram initDataRaw
 */
export async function authTelegram(initDataRaw) {
  const data = await request('/api/auth/telegram', {
    method: 'POST',
    body: JSON.stringify({ init_data_raw: initDataRaw }),
  });
  if (data.token) {
    setToken(data.token);
  }
  return data;
}

/**
 * Получить профиль текущего пользователя
 */
export async function getProfile() {
  return request('/api/profile');
}

/**
 * Список сессий пользователя
 */
export async function getSessions() {
  return request('/api/sessions');
}

/**
 * Создать новую сессию (начать звонок)
 */
export async function createSession() {
  return request('/api/sessions', { method: 'POST' });
}

/**
 * Пополнить баланс
 */
export async function topUp(amount, source) {
  return request('/api/billing/topup', {
    method: 'POST',
    body: JSON.stringify({ amount, source }),
  });
}

/**
 * Получить итоги сессии
 */
export async function getSessionSummary(sessionId) {
  return request(`/api/sessions/${sessionId}/summary`);
}

/**
 * Получить список планов подписки
 */
export async function getSubscriptionPlans() {
  return request('/api/subscriptions/plans');
}

/**
 * Оформить подписку
 */
export async function subscribe(plan) {
  return request('/api/subscriptions/subscribe', {
    method: 'POST',
    body: JSON.stringify({ plan }),
  });
}

/**
 * Применить промокод
 */
export async function applyPromo(code) {
  return request('/api/billing/apply-promo', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

/**
 * Получить статистику рефералов
 */
export async function getReferralStats() {
  return request('/api/referral/stats');
}

/**
 * Получить реферальную ссылку
 */
export async function getReferralLink() {
  return request('/api/referral/link');
}

/**
 * Админ: получить статистику
 */
export async function getAdminStats(adminKey) {
  return request('/api/admin/stats', {
    headers: { 'X-Admin-Key': adminKey },
  });
}

/**
 * Админ: получить список сессий
 */
export async function getAdminSessions(adminKey, page = 1) {
  return request(`/api/admin/sessions?page=${page}`, {
    headers: { 'X-Admin-Key': adminKey },
  });
}

/**
 * Админ: получить список пользователей
 */
export async function getAdminUsers(adminKey, page = 1) {
  return request(`/api/admin/users?page=${page}`, {
    headers: { 'X-Admin-Key': adminKey },
  });
}
