import DataTable from '../components/DataTable';

interface User {
  [key: string]: unknown;
  id: number;
  name: string;
  telegram: string;
  registered: string;
  vip: string;
  clicks: number;
  status: string;
}

const mockUsers: User[] = [
  { id: 1, name: 'Алексей Иванов', telegram: '@alexey_iv', registered: '2024-01-15', vip: 'Premium', clicks: 342, status: 'Активен' },
  { id: 2, name: 'Мария Петрова', telegram: '@maria_p', registered: '2024-02-03', vip: 'Free', clicks: 87, status: 'Активен' },
  { id: 3, name: 'Дмитрий Козлов', telegram: '@dmitry_k', registered: '2024-01-22', vip: 'Premium', clicks: 521, status: 'Активен' },
  { id: 4, name: 'Анна Сидорова', telegram: '@anna_s', registered: '2024-03-10', vip: 'Free', clicks: 45, status: 'Заблокирован' },
  { id: 5, name: 'Сергей Волков', telegram: '@sergey_v', registered: '2024-02-28', vip: 'Premium', clicks: 678, status: 'Активен' },
  { id: 6, name: 'Елена Новикова', telegram: '@elena_n', registered: '2024-03-15', vip: 'Free', clicks: 123, status: 'Активен' },
  { id: 7, name: 'Павел Морозов', telegram: '@pavel_m', registered: '2024-01-08', vip: 'Premium', clicks: 891, status: 'Активен' },
  { id: 8, name: 'Ольга Кузнецова', telegram: '@olga_k', registered: '2024-04-01', vip: 'Free', clicks: 56, status: 'Активен' },
  { id: 9, name: 'Игорь Попов', telegram: '@igor_p', registered: '2024-02-14', vip: 'Free', clicks: 234, status: 'Активен' },
  { id: 10, name: 'Наталья Соколова', telegram: '@natalia_s', registered: '2024-03-22', vip: 'Premium', clicks: 445, status: 'Активен' },
  { id: 11, name: 'Андрей Лебедев', telegram: '@andrey_l', registered: '2024-04-05', vip: 'Free', clicks: 12, status: 'Заблокирован' },
];

const columns = [
  { key: 'id' as const, label: 'ID' },
  { key: 'name' as const, label: 'Имя' },
  { key: 'telegram' as const, label: 'Telegram' },
  { key: 'registered' as const, label: 'Регистрация' },
  {
    key: 'vip' as const,
    label: 'Тариф',
    render: (value: unknown) => (
      <span
        className={`px-2 py-1 rounded-full text-xs font-medium ${
          value === 'Premium' ? 'bg-accent/10 text-accent-dark' : 'bg-gray-100 text-gray-600'
        }`}
      >
        {String(value)}
      </span>
    ),
  },
  { key: 'clicks' as const, label: 'Клики' },
  {
    key: 'status' as const,
    label: 'Статус',
    render: (value: unknown) => (
      <span
        className={`px-2 py-1 rounded-full text-xs font-medium ${
          value === 'Активен' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
        }`}
      >
        {String(value)}
      </span>
    ),
  },
];

export default function Users() {
  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Пользователи</h2>
      <DataTable columns={columns} data={mockUsers} pageSize={10} />
    </div>
  );
}
