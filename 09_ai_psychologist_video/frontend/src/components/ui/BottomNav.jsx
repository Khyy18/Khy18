import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';

/**
 * Нижняя навигационная панель.
 * 2 таба: Dashboard (главная) и Settings (настройки).
 * Скрывается на /call/* и /onboarding маршрутах.
 */
export default function BottomNav() {
  const location = useLocation();

  // Скрыть на call и onboarding
  if (location.pathname.startsWith('/call') || location.pathname === '/onboarding') {
    return null;
  }

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-[var(--tg-theme-secondary-bg-color)] border-t border-[var(--tg-theme-hint-color)]/20 z-40">
      <div className="flex justify-around items-center h-14">
        <NavLink
          to="/"
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 px-4 py-1 ${
              isActive ? 'text-[var(--tg-theme-button-color)]' : 'text-[var(--tg-theme-hint-color)]'
            }`
          }
        >
          {/* Home icon */}
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
          </svg>
          <span className="text-xs">Главная</span>
        </NavLink>

        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 px-4 py-1 ${
              isActive ? 'text-[var(--tg-theme-button-color)]' : 'text-[var(--tg-theme-hint-color)]'
            }`
          }
        >
          {/* Gear icon */}
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span className="text-xs">Настройки</span>
        </NavLink>
      </div>
    </nav>
  );
}
