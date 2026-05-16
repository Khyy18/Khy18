import DataTable from '../components/DataTable';

interface Post {
  [key: string]: unknown;
  id: number;
  title: string;
  channel: string;
  published: string;
  impressions: number;
  ctr: string;
  variant: string;
  status: string;
}

const mockPosts: Post[] = [
  { id: 1, title: 'Sony WH-1000XM5 за 24 990 ₽', channel: '@deals_wb', published: '2024-06-01', impressions: 12450, ctr: '6.8%', variant: 'A', status: 'Опубликован' },
  { id: 2, title: 'Sony WH-1000XM5 - скидка 29%!', channel: '@deals_wb', published: '2024-06-01', impressions: 11890, ctr: '7.2%', variant: 'B', status: 'Опубликован' },
  { id: 3, title: 'Nike Air Max 90 от 8 490 ₽', channel: '@deals_ozon', published: '2024-06-02', impressions: 8900, ctr: '5.4%', variant: 'A', status: 'Опубликован' },
  { id: 4, title: 'Робот-пылесос Xiaomi -37%', channel: '@deals_wb', published: '2024-06-03', impressions: 15200, ctr: '7.9%', variant: 'A', status: 'Опубликован' },
  { id: 5, title: 'iPhone 15 дешевле на 15 000 ₽', channel: '@deals_ozon', published: '2024-06-03', impressions: 21300, ctr: '11.0%', variant: 'B', status: 'Опубликован' },
  { id: 6, title: 'Куртка Columbia -38%', channel: '@deals_wb', published: '2024-06-04', impressions: 6780, ctr: '4.2%', variant: 'A', status: 'На модерации' },
  { id: 7, title: 'Samsung Tab S9 за 44 990 ₽', channel: '@deals_ozon', published: '2024-06-04', impressions: 9100, ctr: '5.8%', variant: 'A', status: 'Опубликован' },
  { id: 8, title: 'DeLonghi кофемашина -34%', channel: '@deals_wb', published: '2024-06-05', impressions: 7200, ctr: '3.9%', variant: 'B', status: 'На модерации' },
  { id: 9, title: 'Apple Watch SE за 21 990 ₽', channel: '@deals_ozon', published: '2024-06-05', impressions: 13400, ctr: '6.6%', variant: 'A', status: 'Опубликован' },
  { id: 10, title: 'PS5 Digital за 42 990 ₽', channel: '@deals_ozon', published: '2024-06-06', impressions: 18700, ctr: '8.4%', variant: 'A', status: 'Опубликован' },
];

const columns = [
  { key: 'id' as const, label: 'ID' },
  { key: 'title' as const, label: 'Заголовок' },
  { key: 'channel' as const, label: 'Канал' },
  { key: 'published' as const, label: 'Дата' },
  { key: 'impressions' as const, label: 'Показы' },
  { key: 'ctr' as const, label: 'CTR' },
  {
    key: 'variant' as const,
    label: 'Вариант',
    render: (value: unknown) => (
      <span className="px-2 py-1 bg-gray-100 rounded text-xs font-mono">{String(value)}</span>
    ),
  },
  {
    key: 'status' as const,
    label: 'Статус',
    render: (value: unknown) => (
      <span
        className={`px-2 py-1 rounded-full text-xs font-medium ${
          value === 'Опубликован' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
        }`}
      >
        {String(value)}
      </span>
    ),
  },
];

export default function Posts() {
  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Публикации</h2>
      <p className="text-gray-500 mb-4">A/B тестирование заголовков и контента публикаций</p>
      <DataTable columns={columns} data={mockPosts} pageSize={10} />
    </div>
  );
}
