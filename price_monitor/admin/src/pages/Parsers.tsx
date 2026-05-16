import { useState, useEffect } from 'react';
import { fetchParsers, type ParserResponse } from '../api/client';

interface ParserStatus {
  name: string;
  lastRun: string;
  productsCount: number;
  status: 'active' | 'warning' | 'error';
}

function mapParser(p: ParserResponse): ParserStatus {
  const statusMap: Record<string, 'active' | 'warning' | 'error'> = {
    active: 'active',
    warning: 'warning',
    error: 'error',
  };
  return {
    name: p.name,
    lastRun: p.last_run || 'Нет данных',
    productsCount: p.products_count,
    status: statusMap[p.status] || 'active',
  };
}

function statusBadge(status: ParserStatus['status']) {
  const styles = {
    active: 'bg-green-100 text-green-700',
    warning: 'bg-yellow-100 text-yellow-700',
    error: 'bg-red-100 text-red-700',
  };
  const labels = { active: 'Работает', warning: 'Внимание', error: 'Ошибка' };
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

export default function Parsers() {
  const [parsers, setParsers] = useState<ParserStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchParsers()
      .then((data) => setParsers(data.map(mapParser)))
      .catch(() => setParsers([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div>
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Статус парсеров</h2>
        <p className="text-gray-500">Загрузка...</p>
      </div>
    );
  }

  if (parsers.length === 0) {
    return (
      <div>
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Статус парсеров</h2>
        <p className="text-gray-500">Нет данных о парсерах</p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Статус парсеров</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {parsers.map((p) => (
          <div key={p.name} className="bg-white rounded-xl p-6 border border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-gray-900 text-sm">{p.name}</h3>
              {statusBadge(p.status)}
            </div>
            <div className="space-y-2 text-sm text-gray-600">
              <div className="flex justify-between">
                <span>Последний запуск</span>
                <span className="font-medium text-gray-900">{p.lastRun}</span>
              </div>
              <div className="flex justify-between">
                <span>Товаров обработано</span>
                <span className="font-medium text-gray-900">{p.productsCount.toLocaleString('ru-RU')}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
