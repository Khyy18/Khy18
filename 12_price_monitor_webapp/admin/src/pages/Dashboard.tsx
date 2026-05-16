import { useState, useEffect } from 'react';
import StatCard from '../components/StatCard';
import Chart from '../components/Chart';
import { fetchStats, type StatsResponse } from '../api/client';

const trendData = {
  labels: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'],
  datasets: [
    {
      label: 'Клики',
      data: [2100, 2500, 2300, 3100, 2800, 3400, 3421],
      borderColor: '#FF6B35',
      backgroundColor: 'rgba(255, 107, 53, 0.1)',
      fill: true,
      tension: 0.4,
    },
    {
      label: 'Конверсии',
      data: [98, 120, 105, 145, 130, 158, 164],
      borderColor: '#6366f1',
      backgroundColor: 'rgba(99, 102, 241, 0.1)',
      fill: true,
      tension: 0.4,
    },
  ],
};

const revenueData = {
  labels: ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн'],
  datasets: [
    {
      label: 'Выручка, тыс. \u20BD',
      data: [89, 102, 118, 134, 142, 156],
      backgroundColor: '#FF6B35',
      borderRadius: 6,
    },
  ],
};

function formatNumber(n: number): string {
  return n.toLocaleString('ru-RU');
}

export default function Dashboard() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  const statCards = stats
    ? [
        { title: 'Всего пользователей', value: formatNumber(stats.total_users), icon: '\uD83D\uDC65', trend: { value: 0, positive: true } },
        { title: 'Кликов всего', value: formatNumber(stats.total_clicks), icon: '\uD83D\uDC46', trend: { value: 0, positive: true } },
        { title: 'VIP пользователей', value: formatNumber(stats.vip_users), icon: '\uD83C\uDFAF', trend: { value: 0, positive: true } },
        { title: 'Выручка', value: `${formatNumber(stats.total_revenue)} \u20BD`, icon: '\uD83D\uDCB0', trend: { value: 0, positive: true } },
      ]
    : [
        { title: 'Всего пользователей', value: loading ? '...' : '0', icon: '\uD83D\uDC65', trend: { value: 0, positive: true } },
        { title: 'Кликов всего', value: loading ? '...' : '0', icon: '\uD83D\uDC46', trend: { value: 0, positive: true } },
        { title: 'VIP пользователей', value: loading ? '...' : '0', icon: '\uD83C\uDFAF', trend: { value: 0, positive: true } },
        { title: 'Выручка', value: loading ? '...' : '0 \u20BD', icon: '\uD83D\uDCB0', trend: { value: 0, positive: true } },
      ];

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Дашборд</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map((s) => (
          <StatCard key={s.title} {...s} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Chart type="line" data={trendData} title="Клики и конверсии за неделю" />
        <Chart type="bar" data={revenueData} title="Выручка по месяцам" />
      </div>
    </div>
  );
}
