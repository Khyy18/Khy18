import React from 'react';

/**
 * Анимированный аватар AI-психолога.
 * @param {{ speaking?: boolean, size?: 'sm' | 'md' | 'lg' }} props
 */
export default function Avatar({ speaking = false, size = 'lg' }) {
  const sizeClasses = {
    sm: 'w-16 h-16',
    md: 'w-24 h-24',
    lg: 'w-32 h-32',
  };

  return (
    <div className="relative flex items-center justify-center">
      {/* Пульсирующее кольцо при говорении */}
      {speaking && (
        <span
          className={`absolute ${sizeClasses[size]} rounded-full bg-purple-400/30`}
          style={{ animation: 'avatarPulse 1.5s ease-in-out infinite' }}
        />
      )}
      {speaking && (
        <span
          className={`absolute ${sizeClasses[size]} rounded-full bg-purple-400/20`}
          style={{ animation: 'avatarPulse 1.5s ease-in-out infinite 0.3s' }}
        />
      )}

      {/* Основной круг с градиентом */}
      <div
        className={`relative ${sizeClasses[size]} rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center shadow-lg ${
          speaking ? 'scale-105' : ''
        } transition-transform duration-300`}
      >
        {/* Иконка мозга/головы */}
        <svg
          className="w-1/2 h-1/2 text-white"
          fill="currentColor"
          viewBox="0 0 24 24"
        >
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
        </svg>
      </div>

      <style>{`
        @keyframes avatarPulse {
          0% { transform: scale(1); opacity: 0.6; }
          50% { transform: scale(1.3); opacity: 0; }
          100% { transform: scale(1); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
