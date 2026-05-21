import React from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
} from 'chart.js';
import type { PricePoint } from '../types';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement);

interface SparklineChartProps {
  points: PricePoint[];
}

export const SparklineChart: React.FC<SparklineChartProps> = ({ points }) => {
  const prices = points.map((p) => p.price);
  const isDown = prices[prices.length - 1] < prices[0];

  const data = {
    labels: points.map((_, i) => i.toString()),
    datasets: [
      {
        data: prices,
        borderColor: isDown ? '#22c55e' : '#ef4444',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { enabled: false } },
    scales: {
      x: { display: false },
      y: { display: false },
    },
  };

  return <Line data={data} options={options} />;
};
