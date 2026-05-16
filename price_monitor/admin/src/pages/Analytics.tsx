import Chart from '../components/Chart';

const ctrData = {
  labels: ['1 июн', '2 июн', '3 июн', '4 июн', '5 июн', '6 июн', '7 июн'],
  datasets: [
    {
      label: 'CTR Wildberries',
      data: [5.2, 5.8, 6.1, 5.9, 6.5, 6.8, 7.2],
      borderColor: '#FF6B35',
      backgroundColor: 'rgba(255, 107, 53, 0.1)',
      fill: true,
      tension: 0.4,
    },
    {
      label: 'CTR Ozon',
      data: [4.8, 5.1, 5.4, 5.6, 5.9, 6.2, 6.5],
      borderColor: '#6366f1',
      backgroundColor: 'rgba(99, 102, 241, 0.1)',
      fill: true,
      tension: 0.4,
    },
  ],
};

const funnelData = {
  labels: ['Показы', 'Клики', 'Переходы', 'Покупки'],
  datasets: [
    {
      label: 'Конверсионная воронка',
      data: [45000, 3200, 1800, 420],
      backgroundColor: ['#FF6B35', '#FF8F66', '#6366f1', '#22c55e'],
      borderRadius: 6,
    },
  ],
};

const revenueBySourceData = {
  labels: ['Wildberries', 'Ozon', 'Яндекс Маркет', 'Мегамаркет', 'Прочие'],
  datasets: [
    {
      label: 'Выручка, тыс. ₽',
      data: [78, 52, 15, 8, 3],
      backgroundColor: ['#FF6B35', '#6366f1', '#f59e0b', '#22c55e', '#94a3b8'],
      borderRadius: 6,
    },
  ],
};

export default function Analytics() {
  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Аналитика</h2>

      <div className="space-y-6">
        <Chart type="line" data={ctrData} title="CTR по дням" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Chart type="bar" data={funnelData} title="Конверсионная воронка" />
          <Chart type="bar" data={revenueBySourceData} title="Выручка по источникам" />
        </div>
      </div>
    </div>
  );
}
