import React from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Filler,
} from 'chart.js';
import type { PricePoint } from '../types';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Filler);

interface PriceChartProps {
  points: PricePoint[];
  forecast?: PricePoint[];
}

export const PriceChart: React.FC<PriceChartProps> = ({ points, forecast }) => {
  const allPoints = forecast ? [...points, ...forecast] : points;

  const data = {
    labels: allPoints.map((p) => {
      const d = new Date(p.date);
      return `${d.getDate()}.${d.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: 'Цена',
        data: points.map((p) => p.price),
        borderColor: '#FF6B35',
        backgroundColor: 'rgba(255, 107, 53, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 2,
      },
      ...(forecast
        ? [
            {
              label: 'Прогноз',
              data: [
                ...Array(points.length - 1).fill(null),
                points[points.length - 1]?.price,
                ...forecast.map((p) => p.price),
              ],
              borderColor: '#FF6B35',
              borderDash: [5, 5],
              backgroundColor: 'rgba(255, 107, 53, 0.05)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
            },
          ]
        : []),
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      tooltip: {
        callbacks: {
          title: (items: { dataIndex: number }[]) => {
            if (!items.length) return '';
            const idx = items[0].dataIndex;
            const point = allPoints[idx];
            if (!point) return '';
            const d = new Date(point.date);
            const day = String(d.getDate()).padStart(2, '0');
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const year = d.getFullYear();
            return `${day}.${month}.${year}`;
          },
          label: (ctx: { parsed: { y: number | null } }) => {
            const val = ctx.parsed.y;
            if (val == null) return '';
            return `${val.toLocaleString('ru-RU')} \u0440`;
          },
          afterLabel: (ctx: { dataIndex: number; parsed: { y: number | null } }) => {
            const val = ctx.parsed.y;
            const idx = ctx.dataIndex;
            if (val == null || idx === 0) return '';
            const prevPoint = allPoints[idx - 1];
            if (!prevPoint || prevPoint.price === 0) return '';
            const change = ((val - prevPoint.price) / prevPoint.price) * 100;
            const sign = change >= 0 ? '+' : '';
            return `${sign}${change.toFixed(1)}% vs prev`;
          },
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
      },
      y: {
        ticks: {
          callback: (value: unknown) =>
            typeof value === 'number' ? `${(value / 1000).toFixed(0)}k` : String(value),
        },
      },
    },
  };

  return (
    <div className="h-48">
      <Line data={data} options={options} />
    </div>
  );
};
