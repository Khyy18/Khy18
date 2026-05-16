import {Product, Category, Alert, UserProfile} from '../types';
import {
  mockProducts,
  mockCategories,
  mockAlerts,
  mockUserProfile,
} from './mockData';

const delay = (ms?: number): Promise<void> =>
  new Promise(resolve =>
    setTimeout(resolve, ms ?? Math.floor(Math.random() * 200) + 300),
  );

let favorites: string[] = [];

export const getDeals = async (
  page: number = 1,
  limit: number = 10,
  category?: string,
): Promise<{products: Product[]; total: number; hasMore: boolean}> => {
  await delay();
  let filtered = mockProducts;
  if (category) {
    filtered = mockProducts.filter(p => p.category === category);
  }
  const start = (page - 1) * limit;
  const end = start + limit;
  const products = filtered.slice(start, end);
  return {
    products,
    total: filtered.length,
    hasMore: end < filtered.length,
  };
};

export const getDealById = async (id: string): Promise<Product | undefined> => {
  await delay();
  return mockProducts.find(p => p.id === id);
};

export const getCategories = async (): Promise<Category[]> => {
  await delay();
  return mockCategories;
};

export const getAlerts = async (): Promise<Alert[]> => {
  await delay();
  return [...mockAlerts];
};

export const createAlert = async (
  data: Omit<Alert, 'id' | 'createdAt'>,
): Promise<Alert> => {
  await delay();
  const newAlert: Alert = {
    ...data,
    id: `alert-${Date.now()}`,
    createdAt: new Date().toISOString(),
  };
  mockAlerts.push(newAlert);
  return newAlert;
};

export const getFavorites = async (): Promise<Product[]> => {
  await delay();
  return mockProducts.filter(p => favorites.includes(p.id));
};

export const addFavorite = async (id: string): Promise<void> => {
  await delay(100);
  if (!favorites.includes(id)) {
    favorites.push(id);
  }
};

export const removeFavorite = async (id: string): Promise<void> => {
  await delay(100);
  favorites = favorites.filter(fid => fid !== id);
};

export const getProfile = async (): Promise<UserProfile> => {
  await delay();
  return {...mockUserProfile};
};
