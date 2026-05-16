import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Products from './pages/Products';
import Users from './pages/Users';
import Posts from './pages/Posts';
import Analytics from './pages/Analytics';
import Parsers from './pages/Parsers';
import Settings from './pages/Settings';

const navItems = [
  { path: '/', label: 'Дашборд', icon: '📊' },
  { path: '/products', label: 'Товары', icon: '📦' },
  { path: '/users', label: 'Пользователи', icon: '👥' },
  { path: '/posts', label: 'Публикации', icon: '📝' },
  { path: '/analytics', label: 'Аналитика', icon: '📈' },
  { path: '/parsers', label: 'Парсеры', icon: '🔄' },
  { path: '/settings', label: 'Настройки', icon: '⚙️' },
];

export default function App() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6 border-b border-gray-200">
          <h1 className="text-xl font-bold text-gray-900">Монитор Цен</h1>
          <p className="text-sm text-gray-500">Админ панель</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-accent text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`
              }
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="flex-1 p-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/users" element={<Users />} />
          <Route path="/posts" element={<Posts />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/parsers" element={<Parsers />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
