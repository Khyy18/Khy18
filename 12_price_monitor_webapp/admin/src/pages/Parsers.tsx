interface ParserStatus {
  name: string;
  lastRun: string;
  nextRun: string;
  successRate: number;
  itemsParsed: number;
  avgDuration: string;
  status: 'active' | 'warning' | 'error';
}

const parsers: ParserStatus[] = [
  { name: 'Wildberries - Электроника', lastRun: '5 мин назад', nextRun: 'через 25 мин', successRate: 99.2, itemsParsed: 12480, avgDuration: '2m 34s', status: 'active' },
  { name: 'Wildberries - Одежда', lastRun: '12 мин назад', nextRun: 'через 18 мин', successRate: 97.8, itemsParsed: 8920, avgDuration: '1m 45s', status: 'active' },
  { name: 'Ozon - Электроника', lastRun: '8 мин назад', nextRun: 'через 22 мин', successRate: 98.5, itemsParsed: 15200, avgDuration: '3m 12s', status: 'active' },
  { name: 'Ozon - Бытовая техника', lastRun: '2 часа назад', nextRun: 'через 5 мин', successRate: 85.3, itemsParsed: 6100, avgDuration: '4m 01s', status: 'warning' },
  { name: 'Яндекс Маркет', lastRun: '4 часа назад', nextRun: 'вручную', successRate: 72.1, itemsParsed: 3200, avgDuration: '5m 22s', status: 'error' },
  { name: 'Мегамаркет', lastRun: '15 мин назад', nextRun: 'через 15 мин', successRate: 96.4, itemsParsed: 4500, avgDuration: '2m 08s', status: 'active' },
];

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
                <span>Следующий запуск</span>
                <span className="font-medium text-gray-900">{p.nextRun}</span>
              </div>
              <div className="flex justify-between">
                <span>Успешность</span>
                <span className={`font-medium ${p.successRate >= 95 ? 'text-green-600' : p.successRate >= 85 ? 'text-yellow-600' : 'text-red-600'}`}>
                  {p.successRate}%
                </span>
              </div>
              <div className="flex justify-between">
                <span>Товаров обработано</span>
                <span className="font-medium text-gray-900">{p.itemsParsed.toLocaleString('ru-RU')}</span>
              </div>
              <div className="flex justify-between">
                <span>Среднее время</span>
                <span className="font-medium text-gray-900">{p.avgDuration}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
