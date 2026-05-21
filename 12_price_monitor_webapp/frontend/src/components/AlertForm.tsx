import React, { useState } from 'react';
import { useCreateAlert } from '../hooks/useApi';
import { useCategories } from '../hooks/useApi';

interface AlertFormProps {
  onSuccess?: () => void;
}

export const AlertForm: React.FC<AlertFormProps> = ({ onSuccess }) => {
  const [keyword, setKeyword] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [marketplace, setMarketplace] = useState<'all' | 'wb' | 'ozon'>('all');

  const { data: categories } = useCategories();
  const createAlert = useCreateAlert();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyword.trim()) return;

    createAlert.mutate(
      {
        keyword: keyword.trim(),
        max_price: maxPrice ? Number(maxPrice) : null,
        category_id: categoryId || null,
        marketplace,
      },
      {
        onSuccess: () => {
          setKeyword('');
          setMaxPrice('');
          setCategoryId('');
          setMarketplace('all');
          onSuccess?.();
        },
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="text-sm text-tg-hint block mb-1">Ключевое слово</label>
        <input
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="Например: iPhone 15"
          className="w-full px-3 py-2 rounded-lg bg-tg-secondary-bg text-tg-text border-none outline-none focus:ring-2 focus:ring-accent"
        />
      </div>
      <div>
        <label className="text-sm text-tg-hint block mb-1">Максимальная цена</label>
        <input
          type="number"
          value={maxPrice}
          onChange={(e) => setMaxPrice(e.target.value)}
          placeholder="Не обязательно"
          className="w-full px-3 py-2 rounded-lg bg-tg-secondary-bg text-tg-text border-none outline-none focus:ring-2 focus:ring-accent"
        />
      </div>
      <div>
        <label className="text-sm text-tg-hint block mb-1">Категория</label>
        <select
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          className="w-full px-3 py-2 rounded-lg bg-tg-secondary-bg text-tg-text border-none outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="">Все категории</option>
          {categories?.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="text-sm text-tg-hint block mb-1">Маркетплейс</label>
        <select
          value={marketplace}
          onChange={(e) => setMarketplace(e.target.value as 'all' | 'wb' | 'ozon')}
          className="w-full px-3 py-2 rounded-lg bg-tg-secondary-bg text-tg-text border-none outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="all">Все</option>
          <option value="wb">Wildberries</option>
          <option value="ozon">Ozon</option>
        </select>
      </div>
      <button
        type="submit"
        disabled={!keyword.trim() || createAlert.isPending}
        className="w-full py-2.5 bg-accent text-white font-medium rounded-lg disabled:opacity-50 active:bg-accent-dark transition-colors"
      >
        {createAlert.isPending ? 'Создание...' : 'Создать оповещение'}
      </button>
    </form>
  );
};
