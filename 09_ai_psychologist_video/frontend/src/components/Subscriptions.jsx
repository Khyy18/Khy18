import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getSubscriptionPlans, subscribe } from '../utils/api';

/**
 * Экран подписок.
 * Показывает доступные планы, текущий план, кнопку подписки.
 */
export default function Subscriptions() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [currentPlan, setCurrentPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadPlans();
  }, []);

  async function loadPlans() {
    setLoading(true);
    setError(null);
    try {
      const data = await getSubscriptionPlans();
      setPlans(data.plans || []);
      setCurrentPlan(data.current_plan || null);
    } catch (err) {
      setError('Не удалось загрузить планы');
    } finally {
      setLoading(false);
    }
  }

  async function handleSubscribe(plan) {
    setSubscribing(plan);
    setError(null);
    try {
      await subscribe(plan);
      setCurrentPlan(plan);
    } catch (err) {
      setError('Ошибка при оформлении подписки');
    } finally {
      setSubscribing(null);
    }
  }

  const planColors = {
    free: 'border-gray-400',
    basic: 'border-blue-500',
    premium: 'border-purple-500',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--tg-theme-bg-color)]">
        <div className="animate-spin w-8 h-8 border-4 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] p-4 pb-20">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1 text-[var(--tg-theme-button-color)] mb-4"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Назад
      </button>

      <h1 className="text-2xl font-bold mb-6">Подписки</h1>

      {error && (
        <p className="text-red-500 text-sm text-center mb-4">{error}</p>
      )}

      <div className="space-y-4">
        {plans.map((plan) => (
          <div
            key={plan.id || plan.name}
            className={`relative bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-5 border-2 ${
              planColors[plan.name] || 'border-transparent'
            } ${currentPlan === plan.name ? 'ring-2 ring-[var(--tg-theme-button-color)]' : ''}`}
          >
            {/* Бейдж текущего плана */}
            {currentPlan === plan.name && (
              <span className="absolute top-3 right-3 text-xs bg-[var(--tg-theme-button-color)] text-white px-2 py-0.5 rounded-full">
                Текущий
              </span>
            )}

            <h3 className="font-bold text-lg capitalize mb-1">{plan.title || plan.name}</h3>
            <p className="text-2xl font-bold mb-2">
              {plan.price > 0 ? `${plan.price} \u20BD/мес` : 'Бесплатно'}
            </p>

            {/* Список фич */}
            {plan.features && (
              <ul className="text-sm text-[var(--tg-theme-hint-color)] space-y-1 mb-4">
                {plan.features.map((f, idx) => (
                  <li key={idx} className="flex items-center gap-2">
                    <span className="text-green-500">&#10003;</span>
                    {f}
                  </li>
                ))}
              </ul>
            )}

            {currentPlan !== plan.name && (
              <button
                onClick={() => handleSubscribe(plan.name)}
                disabled={subscribing === plan.name}
                className="w-full py-3 rounded-xl bg-[var(--tg-theme-button-color)] text-white font-medium hover:opacity-90 active:scale-[0.98] transition-all"
              >
                {subscribing === plan.name ? 'Оформление...' : 'Подписаться'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
