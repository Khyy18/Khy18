import React, { useState } from 'react';
import { useAlerts, useDeleteAlert } from '../hooks/useApi';
import { AlertForm } from '../components/AlertForm';
import { formatPrice } from '../api/client';

export const Alerts: React.FC = () => {
  const [showForm, setShowForm] = useState(false);
  const { data: alerts, isLoading } = useAlerts();
  const deleteAlert = useDeleteAlert();

  return (
    <div className="pb-16 px-4 pt-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-tg-text">Оповещения</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-3 py-1.5 bg-accent text-white text-sm rounded-lg"
        >
          {showForm ? 'Закрыть' : '+ Новое'}
        </button>
      </div>

      {showForm && (
        <div className="mb-4 bg-tg-secondary-bg rounded-xl p-4">
          <AlertForm onSuccess={() => setShowForm(false)} />
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 bg-tg-secondary-bg rounded-xl animate-pulse" />
          ))}
        </div>
      ) : alerts && alerts.length > 0 ? (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="bg-tg-secondary-bg rounded-xl p-3 flex items-center justify-between"
            >
              <div>
                <p className="text-sm font-medium text-tg-text">{alert.keyword}</p>
                <div className="flex gap-2 mt-1 text-xs text-tg-hint">
                  {alert.max_price && <span>до {formatPrice(alert.max_price)}</span>}
                  {alert.category_name && <span>{alert.category_name}</span>}
                  <span>
                    {alert.marketplace === 'all'
                      ? 'Все'
                      : alert.marketplace === 'wb'
                      ? 'WB'
                      : 'Ozon'}
                  </span>
                </div>
              </div>
              <button
                onClick={() => deleteAlert.mutate(alert.id)}
                className="text-red-500 text-sm px-2 py-1"
              >
                Удалить
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <p className="text-4xl mb-3">🔔</p>
          <p className="text-tg-hint text-sm">
            У вас пока нет оповещений.<br />
            Создайте первое, чтобы получать уведомления о скидках.
          </p>
        </div>
      )}
    </div>
  );
};
