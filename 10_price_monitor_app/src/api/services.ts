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

export const toggleAlert = async (
  id: string,
  active: boolean,
): Promise<Alert> => {
  await delay(100);
  const alert = mockAlerts.find(a => a.id === id);
  if (alert) {
    alert.active = active;
  }
  return alert ?? {id, keyword: '', maxPrice: 0, category: '', active, createdAt: ''};
};

export const deleteAlert = async (id: string): Promise<void> => {
  await delay(100);
  const index = mockAlerts.findIndex(a => a.id === id);
  if (index !== -1) {
    mockAlerts.splice(index, 1);
  }
};

export const getProfile = async (): Promise<UserProfile> => {
  await delay();
  return {...mockUserProfile};
};
