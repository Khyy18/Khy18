const BASE_URL = import.meta.env.VITE_API_URL || '/api';

let adminToken: string | null = null;

export function setAdminToken(token: string) {
  adminToken = token;
  localStorage.setItem('admin_token', token);
}

export function getAdminToken(): string | null {
  if (adminToken) return adminToken;
  adminToken = localStorage.getItem('admin_token');
  return adminToken;
}

export async function adminApiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAdminToken();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

export interface StatsResponse {
  total_users: number;
  vip_users: number;
  total_products: number;
  total_alerts: number;
  total_clicks: number;
  total_revenue: number;
}

export interface UserResponse {
  id: number;
  telegram_id: number;
  username: string | null;
  is_vip: boolean;
  created_at: string;
}

export interface PostResponse {
  id: number;
  product_id: number;
  channel_id: number;
  text: string;
  variant: string | null;
  impressions: number;
  clicks: number;
  ctr: number;
  published_at: string;
}

export interface ParserResponse {
  name: string;
  status: string;
  last_run: string | null;
  products_count: number;
}

export async function fetchStats(): Promise<StatsResponse> {
  return adminApiClient<StatsResponse>('/admin/stats');
}

export async function fetchUsers(page = 1, limit = 20): Promise<UserResponse[]> {
  return adminApiClient<UserResponse[]>(`/admin/users?page=${page}&limit=${limit}`);
}

export async function fetchPosts(limit = 20): Promise<PostResponse[]> {
  return adminApiClient<PostResponse[]>(`/admin/posts?limit=${limit}`);
}

export async function fetchParsers(): Promise<ParserResponse[]> {
  return adminApiClient<ParserResponse[]>('/admin/parsers');
}
