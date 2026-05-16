import { useState, useEffect } from 'react';
import DataTable from '../components/DataTable';
import { fetchPosts, type PostResponse } from '../api/client';

interface PostRow {
  [key: string]: unknown;
  id: number;
  text: string;
  channel_id: number;
  published_at: string;
  impressions: number;
  ctr: string;
  variant: string;
}

const columns = [
  { key: 'id' as const, label: 'ID' },
  { key: 'text' as const, label: 'Текст' },
  { key: 'channel_id' as const, label: 'Канал' },
  { key: 'published_at' as const, label: 'Дата' },
  { key: 'impressions' as const, label: 'Показы' },
  { key: 'ctr' as const, label: 'CTR' },
  {
    key: 'variant' as const,
    label: 'Вариант',
    render: (value: unknown) => (
      <span className="px-2 py-1 bg-gray-100 rounded text-xs font-mono">{String(value || '-')}</span>
    ),
  },
];

function mapPost(p: PostResponse): PostRow {
  return {
    id: p.id,
    text: p.text.length > 40 ? p.text.slice(0, 40) + '...' : p.text,
    channel_id: p.channel_id,
    published_at: p.published_at.split('T')[0],
    impressions: p.impressions,
    ctr: `${p.ctr.toFixed(1)}%`,
    variant: p.variant || '-',
  };
}

export default function Posts() {
  const [posts, setPosts] = useState<PostRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPosts()
      .then((data) => setPosts(data.map(mapPost)))
      .catch(() => setPosts([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Публикации</h2>
      <p className="text-gray-500 mb-4">A/B тестирование заголовков и контента публикаций</p>
      {loading ? (
        <p className="text-gray-500">Загрузка...</p>
      ) : posts.length === 0 ? (
        <p className="text-gray-500">Нет данных</p>
      ) : (
        <DataTable columns={columns} data={posts} pageSize={10} />
      )}
    </div>
  );
}
