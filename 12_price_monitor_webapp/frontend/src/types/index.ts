export interface Product {
  id: string;
  title: string;
  image_url: string;
  current_price: number;
  original_price: number;
  discount_percent: number;
  marketplace: 'wb' | 'ozon';
  category_id: string;
  category_name: string;
  url: string;
  price_history: PricePoint[];
  is_favorite: boolean;
  created_at: string;
}

export interface PricePoint {
  date: string;
  price: number;
}

export interface Alert {
  id: string;
  keyword: string;
  max_price: number | null;
  category_id: string | null;
  category_name: string | null;
  marketplace: 'wb' | 'ozon' | 'all';
  is_active: boolean;
  created_at: string;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  product_count: number;
}

export interface ArbitrageItem {
  id: string;
  title: string;
  image_url: string;
  wb_price: number;
  ozon_price: number;
  diff_percent: number;
  cheaper_on: 'wb' | 'ozon';
  wb_url: string;
  ozon_url: string;
}

export interface UserProfile {
  id: string;
  telegram_id: number;
  username: string;
  first_name: string;
  subscription: 'free' | 'pro' | 'vip';
  subscription_expires: string | null;
  alerts_count: number;
  favorites_count: number;
}

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  has_next: boolean;
}
