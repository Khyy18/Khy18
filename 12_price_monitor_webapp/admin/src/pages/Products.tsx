import { useState, useEffect } from 'react';
import DataTable from '../components/DataTable';
import { adminApiClient } from '../api/client';

interface ProductRow {
  [key: string]: unknown;
  id: number;
  name: string;
  marketplace: string;
  category: string;
  rating: number;
}

interface ProductResponse {
  id: string;
  title: string;
  marketplace: string;
  category_name: string;
  current_price: number;
  discount_percent: number;
  image_url: string;
  rating: number;
}

interface ProductListResponse {
  items: ProductResponse[];
  total: number;
  page: number;
  has_next: boolean;
}

const columns = [
  { key: 'id' as const, label: 'ID' },
  { key: 'name' as const, label: 'Название' },
  { key: 'marketplace' as const, label: 'Маркетплейс' },
  { key: 'category' as const, label: 'Категория' },
  { key: 'rating' as const, label: 'Рейтинг' },
];

export default function Products() {
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminApiClient<ProductListResponse>('/deals?limit=50')
      .then((data) => {
        setProducts(
          data.items.map((p) => ({
            id: Number(p.id),
            name: p.title,
            marketplace: p.marketplace,
            category: p.category_name || '-',
            rating: p.rating || 0,
          }))
        );
      })
      .catch(() => setProducts([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = products.filter((p) => {
    const matchSearch = p.name.toLowerCase().includes(search.toLowerCase());
    const matchFilter = filter === 'all' || p.marketplace.toLowerCase() === filter;
    return matchSearch && matchFilter;
  });

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Товары</h2>

      <div className="flex gap-4 mb-6">
        <input
          type="text"
          placeholder="Поиск товаров..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 max-w-sm px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
        />
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
        >
          <option value="all">Все маркетплейсы</option>
          <option value="wb">Wildberries</option>
          <option value="ozon">Ozon</option>
        </select>
      </div>

      {loading ? (
        <p className="text-gray-500">Загрузка...</p>
      ) : filtered.length === 0 ? (
        <p className="text-gray-500">Нет данных</p>
      ) : (
        <DataTable columns={columns} data={filtered} pageSize={10} />
      )}
    </div>
  );
}
