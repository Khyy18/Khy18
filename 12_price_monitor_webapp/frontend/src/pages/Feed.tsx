import React, { useEffect, useRef, useState } from 'react';
import { useInfiniteProducts, useCategories } from '../hooks/useApi';
import { ProductCard } from '../components/ProductCard';

export const Feed: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>();
  const { data: categories } = useCategories();
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteProducts(selectedCategory);

  const observerTarget = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 }
    );

    if (observerTarget.current) {
      observer.observe(observerTarget.current);
    }

    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const products = data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="pb-16">
      <div className="sticky top-0 z-10 bg-tg-bg px-4 py-3">
        <h1 className="text-xl font-bold text-tg-text mb-3">Лучшие скидки</h1>
        <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-2">
          <button
            onClick={() => setSelectedCategory(undefined)}
            className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap flex-shrink-0 ${
              !selectedCategory
                ? 'bg-accent text-white'
                : 'bg-tg-secondary-bg text-tg-text'
            }`}
          >
            Все
          </button>
          {categories?.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap flex-shrink-0 ${
                selectedCategory === cat.id
                  ? 'bg-accent text-white'
                  : 'bg-tg-secondary-bg text-tg-text'
              }`}
            >
              {cat.icon} {cat.name}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 grid grid-cols-2 gap-3">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="bg-tg-secondary-bg rounded-xl h-56 animate-pulse"
              />
            ))
          : products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
      </div>

      {isFetchingNextPage && (
        <div className="flex justify-center py-4">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      <div ref={observerTarget} className="h-4" />
    </div>
  );
};
