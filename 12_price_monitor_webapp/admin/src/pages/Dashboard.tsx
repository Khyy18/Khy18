import StatCard from '../components/StatCard';
import Chart from '../components/Chart';

const stats = [
  { title: 'Всего пользователей', value: '12 847', icon: '👥', trend: { value: 5.2, positive: true } },
  { title: 'Кликов сегодня', value: '3 421', icon: '👆', trend: { value: 12.1, positive: true } },
  { title: 'Конверсия', value: '4.8%', icon: '🎯', trend: { value: -0.3, positive: false } },
  { title: 'Выручка', value: '156 200 ₽', icon: '💰', trend: { value: 8.7, positive: true } },
];

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
      label: 'Выручка, тыс. ₽',
      data: [89, 102, 118, 134, 142, 156],
      backgroundColor: '#FF6B35',
      borderRadius: 6,
    },
  ],
};

export default function Dashboard() {
  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Дашборд</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((s) => (
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
