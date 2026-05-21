import React from 'react';
import { NavLink } from 'react-router-dom';

const tabs = [
  { path: '/', label: 'Лента', icon: '🔥' },
  { path: '/categories', label: 'Категории', icon: '📂' },
  { path: '/favorites', label: 'Избранное', icon: '❤️' },
  { path: '/profile', label: 'Профиль', icon: '👤' },
];

export const Navigation: React.FC = () => {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-tg-bg border-t border-gray-200 z-50">
      <div className="flex justify-around items-center h-14 max-w-lg mx-auto">
        {tabs.map((tab) => (
          <NavLink
            key={tab.path}
            to={tab.path}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center w-full h-full text-xs transition-colors ${
                isActive ? 'text-accent' : 'text-tg-hint'
              }`
            }
          >
            <span className="text-lg mb-0.5">{tab.icon}</span>
            <span>{tab.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
};
