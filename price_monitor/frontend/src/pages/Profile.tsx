import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useProfile, useBadges } from '../hooks/useApi';

export const Profile: React.FC = () => {
  const navigate = useNavigate();
  const { data: profile, isLoading } = useProfile();
  const { data: badges } = useBadges();

  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <div className="h-24 bg-tg-secondary-bg rounded-xl animate-pulse" />
        <div className="h-32 bg-tg-secondary-bg rounded-xl animate-pulse" />
      </div>
    );
  }

  const subscriptionLabel = {
    free: 'Бесплатный',
    pro: 'Pro',
    vip: 'VIP',
  };

  return (
    <div className="pb-16 px-4 pt-4">
      <h1 className="text-xl font-bold text-tg-text mb-4">Профиль</h1>

      <div className="bg-tg-secondary-bg rounded-xl p-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-accent/20 rounded-full flex items-center justify-center text-xl">
            👤
          </div>
          <div>
            <p className="font-medium text-tg-text">{profile?.first_name}</p>
            {profile?.username && (
              <p className="text-sm text-tg-hint">@{profile.username}</p>
            )}
          </div>
        </div>
      </div>

      <div className="bg-tg-secondary-bg rounded-xl p-4 mb-4">
        <h2 className="font-medium text-tg-text mb-2">Подписка</h2>
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-bold text-accent">
              {profile ? subscriptionLabel[profile.subscription] : ''}
            </span>
            {profile?.subscription_expires && (
              <p className="text-xs text-tg-hint mt-0.5">
                до {new Date(profile.subscription_expires).toLocaleDateString('ru-RU')}
              </p>
            )}
          </div>
          {profile?.subscription === 'free' && (
            <button className="px-4 py-2 bg-accent text-white text-sm font-medium rounded-lg">
              Улучшить
            </button>
          )}
        </div>
      </div>

      <div className="bg-tg-secondary-bg rounded-xl p-4 mb-4">
        <h2 className="font-medium text-tg-text mb-3">Статистика</h2>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center">
            <p className="text-2xl font-bold text-accent">{profile?.alerts_count || 0}</p>
            <p className="text-xs text-tg-hint">Оповещений</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-accent">{profile?.favorites_count || 0}</p>
            <p className="text-xs text-tg-hint">Избранное</p>
          </div>
        </div>
      </div>

      {badges && badges.length > 0 && (
        <div className="bg-tg-secondary-bg rounded-xl p-4 mb-4">
          <h2 className="font-medium text-tg-text mb-3">Достижения</h2>
          <div className="grid grid-cols-2 gap-2">
            {badges.map((badge) => (
              <div
                key={badge.id}
                className="flex items-center gap-2 p-2 bg-tg-bg rounded-lg"
              >
                <span className="text-2xl">{badge.icon}</span>
                <div className="min-w-0">
                  <p className="text-xs font-medium text-tg-text truncate">
                    {badge.title}
                  </p>
                  <p className="text-[10px] text-tg-hint truncate">
                    {badge.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <button
          onClick={() => navigate('/alerts')}
          className="w-full bg-tg-secondary-bg rounded-xl p-3 text-left text-sm text-tg-text flex items-center justify-between"
        >
          <span>🔔 Оповещения</span>
          <span className="text-tg-hint">&rarr;</span>
        </button>
        <button
          onClick={() => navigate('/chat')}
          className="w-full bg-tg-secondary-bg rounded-xl p-3 text-left text-sm text-tg-text flex items-center justify-between"
        >
          <span>💬 AI Помощник</span>
          <span className="text-tg-hint">&rarr;</span>
        </button>
        <button
          onClick={() => navigate('/arbitrage')}
          className="w-full bg-tg-secondary-bg rounded-xl p-3 text-left text-sm text-tg-text flex items-center justify-between"
        >
          <span>📊 Арбитраж цен</span>
          <span className="text-tg-hint">&rarr;</span>
        </button>
      </div>
    </div>
  );
};
