import { useState, useEffect } from 'react';
import StatCard from '../components/StatCard';
import Chart from '../components/Chart';
import { fetchStats, fetchAnalytics, type StatsResponse, type AnalyticsResponse } from '../api/client';

function formatNumber(n: number): string {
  return n.toLocaleString('ru-RU');
}

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function buildTrendData(analytics: AnalyticsResponse | null) {
  const labels = analytics && analytics.clicks_by_day.length > 0
    ? analytics.clicks_by_day.map((d) => {
        const date = new Date(d.date);
        return WEEKDAYS[date.getDay() === 0 ? 6 : date.getDay() - 1] || d.date;
      })
    : WEEKDAYS;

  const clicks = analytics
    ? analytics.clicks_by_day.map((d) => d.clicks)
    : Array(7).fill(0);

  const conversions = analytics
    ? analytics.clicks_by_day.map((d) => d.conversions)
    : Array(7).fill(0);

  return {
    labels,
    datasets: [
      {
        label: 'Клики',
        data: clicks,
        borderColor: '#FF6B35',
        backgroundColor: 'rgba(255, 107, 53, 0.1)',
        fill: true,
        tension: 0.4,
      },
      {
        label: 'Конверсии',
        data: conversions,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99, 102, 241, 0.1)',
        fill: true,
        tension: 0.4,
      },
    ],
  };
}

function buildRevenueData(analytics: AnalyticsResponse | null) {
  const defaultLabels = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн'];

  const labels = analytics && analytics.revenue_by_month.length > 0
    ? analytics.revenue_by_month.map((m) => m.month)
    : defaultLabels;

  const revenue = analytics
    ? analytics.revenue_by_month.map((m) => m.revenue / 1000)
    : Array(6).fill(0);

  return {
    labels,
    datasets: [
      {
        label: 'Выручка, тыс. \u20BD',
        data: revenue,
        backgroundColor: '#FF6B35',
        borderRadius: 6,
      },
    ],
  };
}

export default function Dashboard() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchStats().catch(() => null),
      fetchAnalytics().catch(() => null),
    ]).then(([statsData, analyticsData]) => {
      setStats(statsData);
      setAnalytics(analyticsData);
      setLoading(false);
    });
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
        <Chart type="line" data={buildTrendData(analytics)} title="Клики и конверсии за неделю" />
        <Chart type="bar" data={buildRevenueData(analytics)} title="Выручка по месяцам" />
      </div>
    </div>
  );
}
