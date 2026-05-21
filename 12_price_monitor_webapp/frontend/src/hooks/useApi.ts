import { useQuery, useMutation, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { Product, Alert, Category, ArbitrageItem, UserProfile, ChatMessage, PaginatedResponse } from '../types';

interface ArbitrageApiResult {
  id: number;
  product_name: string;
  brand: string | null;
  price_wb: number;
  price_ozon: number;
  diff_percent: number;
  match_score: number;
  found_at: string;
}

interface ArbitrageResponse {
  results: ArbitrageApiResult[];
  total: number;
}

export function useProducts(page = 1, category?: string) {
  return useQuery({
    queryKey: ['products', page, category],
    queryFn: () =>
      apiClient<PaginatedResponse<Product>>(
        `/deals?page=${page}${category ? `&category=${category}` : ''}`
      ),
  });
}

export function useInfiniteProducts(category?: string) {
  return useInfiniteQuery({
    queryKey: ['products', 'infinite', category],
    queryFn: ({ pageParam = 1 }) =>
      apiClient<PaginatedResponse<Product>>(
        `/deals?page=${pageParam}${category ? `&category=${category}` : ''}`
      ),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.has_next ? lastPage.page + 1 : undefined,
  });
}

export function useProduct(id: string) {
  return useQuery({
    queryKey: ['product', id],
    queryFn: () => apiClient<Product>(`/deals/${id}`),
    enabled: !!id,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: () => apiClient<Category[]>('/categories'),
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: () => apiClient<Alert[]>('/alerts'),
  });
}

export function useCreateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<Alert, 'id' | 'is_active' | 'created_at' | 'category_name'>) =>
      apiClient<Alert>('/alerts', { method: 'POST', body: JSON.stringify(data) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useDeleteAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient<void>(`/alerts/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useFavorites() {
  return useQuery({
    queryKey: ['favorites'],
    queryFn: () => apiClient<Product[]>('/favorites'),
  });
}

export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productId: string) =>
      apiClient<{ is_favorite: boolean }>(`/favorites/${productId}`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
  });
}

export function useProfile() {
  return useQuery({
    queryKey: ['profile'],
    queryFn: () => apiClient<UserProfile>('/profile'),
  });
}

export function useArbitrage(minDiff?: number, marketplace?: string) {
  return useQuery({
    queryKey: ['arbitrage', minDiff, marketplace],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (minDiff) params.set('min_diff', String(minDiff));
      const qs = params.toString();
      const response = await apiClient<ArbitrageResponse>(
        `/arbitrage${qs ? `?${qs}` : ''}`
      );
      return response.results.map((r): ArbitrageItem => ({
        id: String(r.id),
        title: r.product_name,
        image_url: '',
        wb_price: r.price_wb,
        ozon_price: r.price_ozon,
        diff_percent: Math.round(r.diff_percent * 10) / 10,
        cheaper_on: r.price_wb < r.price_ozon ? 'wb' : 'ozon',
        wb_url: '',
        ozon_url: '',
      }));
    },
  });
}

export function useChatMessages() {
  return useQuery({
    queryKey: ['chat'],
    queryFn: () => apiClient<ChatMessage[]>('/chat/history'),
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (message: string) =>
      apiClient<{ reply: string; product_ids: number[] }>('/chat', {
        method: 'POST',
        body: JSON.stringify({ message }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat'] });
    },
  });
}
