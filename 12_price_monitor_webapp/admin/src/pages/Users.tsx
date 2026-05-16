import { useState, useEffect } from 'react';
import DataTable from '../components/DataTable';
import { fetchUsers, type UserResponse } from '../api/client';

interface UserRow {
  [key: string]: unknown;
  id: number;
  telegram_id: number;
  username: string;
  is_vip: string;
  created_at: string;
}

const columns = [
  { key: 'id' as const, label: 'ID' },
  { key: 'telegram_id' as const, label: 'Telegram ID' },
  { key: 'username' as const, label: 'Username' },
  { key: 'created_at' as const, label: 'Регистрация' },
  {
    key: 'is_vip' as const,
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
];

function mapUser(u: UserResponse): UserRow {
  return {
    id: u.id,
    telegram_id: u.telegram_id,
    username: u.username || '-',
    is_vip: u.is_vip ? 'Premium' : 'Free',
    created_at: u.created_at.split('T')[0],
  };
}

export default function Users() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUsers()
      .then((data) => setUsers(data.map(mapUser)))
      .catch(() => setUsers([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Пользователи</h2>
      {loading ? (
        <p className="text-gray-500">Загрузка...</p>
      ) : users.length === 0 ? (
        <p className="text-gray-500">Нет данных</p>
      ) : (
        <DataTable columns={columns} data={users} pageSize={10} />
      )}
    </div>
  );
}
