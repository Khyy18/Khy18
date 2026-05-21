import React from 'react';
import { useFavorites } from '../hooks/useApi';
import { ProductCard } from '../components/ProductCard';

export const Favorites: React.FC = () => {
  const { data: favorites, isLoading } = useFavorites();

  return (
    <div className="pb-16 px-4 pt-4">
      <h1 className="text-xl font-bold text-tg-text mb-4">Избранное</h1>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-56 bg-tg-secondary-bg rounded-xl animate-pulse" />
          ))}
        </div>
      ) : favorites && favorites.length > 0 ? (
        <div className="grid grid-cols-2 gap-3">
          {favorites.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <p className="text-4xl mb-3">❤️</p>
          <p className="text-tg-hint text-sm">
            Здесь будут товары, которые вы добавите в избранное
          </p>
        </div>
      )}
    </div>
  );
};
