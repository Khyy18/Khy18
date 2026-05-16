import WebApp from '@twa-dev/sdk';

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

function getInitData(): string {
  try {
    return WebApp.initData || '';
  } catch {
    return '';
  }
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const initData = getInitData();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(initData ? { Authorization: `tma ${initData}` } : {}),
    ...(options.headers as Record<string, string> || {}),
  };

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Network error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export function formatPrice(price: number): string {
  return price.toLocaleString('ru-RU').replace(/,/g, ' ') + ' \u0440';
}
