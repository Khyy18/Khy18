import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';
import type { ChartData, ChartOptions } from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface ChartProps {
  type: 'line' | 'bar';
  data: ChartData<'line'> | ChartData<'bar'>;
  options?: ChartOptions<'line'> | ChartOptions<'bar'>;
  title?: string;
}

export default function Chart({ type, data, options, title }: ChartProps) {
  const defaultOptions = {
    responsive: true,
    plugins: {
      legend: { display: true },
      title: { display: !!title, text: title },
    },
  };

  const mergedOptions = { ...defaultOptions, ...options };

  return (
    <div className="bg-white rounded-xl p-6 border border-gray-200">
      {type === 'line' ? (
        <Line data={data as ChartData<'line'>} options={mergedOptions as ChartOptions<'line'>} />
      ) : (
        <Bar data={data as ChartData<'bar'>} options={mergedOptions as ChartOptions<'bar'>} />
      )}
    </div>
  );
}
