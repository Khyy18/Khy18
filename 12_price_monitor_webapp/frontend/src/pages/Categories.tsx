import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCategories } from '../hooks/useApi';

export const Categories: React.FC = () => {
  const navigate = useNavigate();
  const { data: categories, isLoading } = useCategories();

  return (
    <div className="pb-16 px-4 pt-4">
      <h1 className="text-xl font-bold text-tg-text mb-4">Категории</h1>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-24 bg-tg-secondary-bg rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {categories?.map((category) => (
            <button
              key={category.id}
              onClick={() => navigate(`/?category=${category.id}`)}
              className="bg-tg-secondary-bg rounded-xl p-4 text-left active:scale-[0.97] transition-transform"
            >
              <span className="text-2xl">{category.icon}</span>
              <p className="mt-2 text-sm font-medium text-tg-text">{category.name}</p>
              <p className="text-xs text-tg-hint mt-0.5">
                {category.product_count} товаров
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
