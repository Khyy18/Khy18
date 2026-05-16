import { useState } from 'react';
import DataTable from '../components/DataTable';

interface Product {
  [key: string]: unknown;
  id: number;
  name: string;
  marketplace: string;
  price: string;
  oldPrice: string;
  discount: string;
  clicks: number;
  status: string;
}

const mockProducts: Product[] = [
  { id: 1, name: 'Наушники Sony WH-1000XM5', marketplace: 'Wildberries', price: '24 990 ₽', oldPrice: '34 990 ₽', discount: '-29%', clicks: 842, status: 'Активен' },
  { id: 2, name: 'Кроссовки Nike Air Max 90', marketplace: 'Ozon', price: '8 490 ₽', oldPrice: '12 990 ₽', discount: '-35%', clicks: 567, status: 'Активен' },
  { id: 3, name: 'Робот-пылесос Xiaomi', marketplace: 'Wildberries', price: '18 900 ₽', oldPrice: '29 900 ₽', discount: '-37%', clicks: 1203, status: 'Активен' },
  { id: 4, name: 'iPhone 15 128GB', marketplace: 'Ozon', price: '69 990 ₽', oldPrice: '84 990 ₽', discount: '-18%', clicks: 2341, status: 'Активен' },
  { id: 5, name: 'Куртка зимняя Columbia', marketplace: 'Wildberries', price: '12 450 ₽', oldPrice: '19 990 ₽', discount: '-38%', clicks: 398, status: 'Приостановлен' },
  { id: 6, name: 'Планшет Samsung Tab S9', marketplace: 'Ozon', price: '44 990 ₽', oldPrice: '59 990 ₽', discount: '-25%', clicks: 612, status: 'Активен' },
  { id: 7, name: 'Кофемашина DeLonghi', marketplace: 'Wildberries', price: '32 990 ₽', oldPrice: '49 990 ₽', discount: '-34%', clicks: 284, status: 'Активен' },
  { id: 8, name: 'Умные часы Apple Watch SE', marketplace: 'Ozon', price: '21 990 ₽', oldPrice: '29 990 ₽', discount: '-27%', clicks: 891, status: 'Активен' },
  { id: 9, name: 'Фен Dyson Supersonic', marketplace: 'Wildberries', price: '39 990 ₽', oldPrice: '49 990 ₽', discount: '-20%', clicks: 156, status: 'Приостановлен' },
  { id: 10, name: 'PS5 Digital Edition', marketplace: 'Ozon', price: '42 990 ₽', oldPrice: '54 990 ₽', discount: '-22%', clicks: 1567, status: 'Активен' },
  { id: 11, name: 'Мультиварка Redmond', marketplace: 'Wildberries', price: '5 990 ₽', oldPrice: '9 990 ₽', discount: '-40%', clicks: 423, status: 'Активен' },
  { id: 12, name: 'Телевизор LG OLED 55"', marketplace: 'Ozon', price: '89 990 ₽', oldPrice: '129 990 ₽', discount: '-31%', clicks: 312, status: 'Активен' },
];

const columns = [
  { key: 'id' as const, label: 'ID' },
  { key: 'name' as const, label: 'Название' },
  { key: 'marketplace' as const, label: 'Маркетплейс' },
  { key: 'price' as const, label: 'Цена' },
  { key: 'discount' as const, label: 'Скидка' },
  { key: 'clicks' as const, label: 'Клики' },
  {
    key: 'status' as const,
    label: 'Статус',
    render: (value: unknown) => (
      <span
        className={`px-2 py-1 rounded-full text-xs font-medium ${
          value === 'Активен' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
        }`}
      >
        {String(value)}
      </span>
    ),
  },
];

export default function Products() {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');

  const filtered = mockProducts.filter((p) => {
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
          <option value="wildberries">Wildberries</option>
          <option value="ozon">Ozon</option>
        </select>
      </div>

      <DataTable columns={columns} data={filtered} pageSize={10} />
    </div>
  );
}
