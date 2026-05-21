import { useState } from 'react';

interface SettingsState {
  parserInterval: string;
  priceDropThreshold: string;
  notifyOnDrop: boolean;
  notifyOnError: boolean;
  apiKeyWb: string;
  apiKeyOzon: string;
  maxPostsPerDay: string;
  abTestEnabled: boolean;
}

export default function Settings() {
  const [settings, setSettings] = useState<SettingsState>({
    parserInterval: '30',
    priceDropThreshold: '10',
    notifyOnDrop: true,
    notifyOnError: true,
    apiKeyWb: 'wb_api_****_hidden',
    apiKeyOzon: 'ozon_api_****_hidden',
    maxPostsPerDay: '50',
    abTestEnabled: true,
  });

  const update = (key: keyof SettingsState, value: string | boolean) => {
    setSettings((s) => ({ ...s, [key]: value }));
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Настройки</h2>

      <div className="max-w-2xl space-y-6">
        <section className="bg-white rounded-xl p-6 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Парсеры</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Интервал парсинга (минуты)
              </label>
              <input
                type="number"
                value={settings.parserInterval}
                onChange={(e) => update('parserInterval', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Порог снижения цены для уведомления (%)
              </label>
              <input
                type="number"
                value={settings.priceDropThreshold}
                onChange={(e) => update('priceDropThreshold', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
              />
            </div>
          </div>
        </section>

        <section className="bg-white rounded-xl p-6 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Уведомления</h3>
          <div className="space-y-3">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.notifyOnDrop}
                onChange={(e) => update('notifyOnDrop', e.target.checked)}
                className="w-4 h-4 accent-accent"
              />
              <span className="text-sm text-gray-700">Уведомлять о снижении цены</span>
            </label>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.notifyOnError}
                onChange={(e) => update('notifyOnError', e.target.checked)}
                className="w-4 h-4 accent-accent"
              />
              <span className="text-sm text-gray-700">Уведомлять об ошибках парсеров</span>
            </label>
          </div>
        </section>

        <section className="bg-white rounded-xl p-6 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">API ключи</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Wildberries API Key
              </label>
              <input
                type="password"
                value={settings.apiKeyWb}
                onChange={(e) => update('apiKeyWb', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Ozon API Key
              </label>
              <input
                type="password"
                value={settings.apiKeyOzon}
                onChange={(e) => update('apiKeyOzon', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
              />
            </div>
          </div>
        </section>

        <section className="bg-white rounded-xl p-6 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Публикации</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Максимум публикаций в день
              </label>
              <input
                type="number"
                value={settings.maxPostsPerDay}
                onChange={(e) => update('maxPostsPerDay', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
              />
            </div>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.abTestEnabled}
                onChange={(e) => update('abTestEnabled', e.target.checked)}
                className="w-4 h-4 accent-accent"
              />
              <span className="text-sm text-gray-700">Включить A/B тестирование заголовков</span>
            </label>
          </div>
        </section>

        <button className="px-6 py-2.5 bg-accent text-white font-medium rounded-lg hover:bg-accent-dark transition-colors">
          Сохранить настройки
        </button>
      </div>
    </div>
  );
}
