import WebApp from '@twa-dev/sdk';

const BASE_URL = import.meta.env.VITE_API_URL || '/api';

let accessToken: string | null = null;

function getInitData(): string {
  try {
    return WebApp.initData || '';
  } catch {
    return '';
  }
}

async function authenticate(): Promise<string | null> {
  if (accessToken) return accessToken;

  const initData = getInitData();
  if (!initData) return null;

  try {
    const response = await fetch(`${BASE_URL}/auth/telegram`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: initData }),
    });

    if (!response.ok) return null;

    const data = await response.json();
    accessToken = data.access_token;
    return accessToken;
  } catch {
    return null;
  }
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await authenticate();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> || {}),
  };

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Token expired, reset and retry once
    accessToken = null;
    const newToken = await authenticate();
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`;
      const retryResponse = await fetch(`${BASE_URL}${endpoint}`, {
        ...options,
        headers,
      });
      if (!retryResponse.ok) {
        const error = await retryResponse.json().catch(() => ({ detail: 'Network error' }));
        throw new Error(error.detail || `HTTP ${retryResponse.status}`);
      }
      return retryResponse.json();
    }
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Network error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function getAccessToken(): Promise<string | null> {
  return authenticate();
}

export function formatPrice(price: number): string {
  return price.toLocaleString('ru-RU').replace(/,/g, ' ') + ' \u0440';
}
