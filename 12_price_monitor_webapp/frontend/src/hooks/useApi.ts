import { useQuery, useMutation, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { Product, Alert, Category, ArbitrageItem, UserProfile, ChatMessage, PaginatedResponse } from '../types';

export function useProducts(page = 1, category?: string) {
  return useQuery({
    queryKey: ['products', page, category],
    queryFn: () =>
      apiClient<PaginatedResponse<Product>>(
        `/products?page=${page}${category ? `&category=${category}` : ''}`
      ),
  });
}

export function useInfiniteProducts(category?: string) {
  return useInfiniteQuery({
    queryKey: ['products', 'infinite', category],
    queryFn: ({ pageParam = 1 }) =>
      apiClient<PaginatedResponse<Product>>(
        `/products?page=${pageParam}${category ? `&category=${category}` : ''}`
      ),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.has_next ? lastPage.page + 1 : undefined,
  });
}

export function useProduct(id: string) {
  return useQuery({
    queryKey: ['product', id],
    queryFn: () => apiClient<Product>(`/products/${id}`),
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
    queryFn: () =>
      apiClient<ArbitrageItem[]>(
        `/arbitrage?${minDiff ? `min_diff=${minDiff}` : ''}${marketplace ? `&marketplace=${marketplace}` : ''}`
      ),
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
      apiClient<ChatMessage>('/chat/send', {
        method: 'POST',
        body: JSON.stringify({ message }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat'] });
    },
  });
}
