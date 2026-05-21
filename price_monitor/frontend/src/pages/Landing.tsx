import React from 'react';

export const Landing: React.FC = () => {
  return (
    <div className="min-h-screen bg-white">
      {/* Hero Section */}
      <header className="bg-gradient-to-br from-accent to-accent-dark text-white">
        <nav className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <span className="text-xl font-bold">🔥 Монитор Цен</span>
          <a
            href="https://t.me/price_monitor_bot"
            className="bg-white text-accent px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-100 transition-colors"
          >
            Открыть в Telegram
          </a>
        </nav>
        <div className="max-w-5xl mx-auto px-4 py-16 text-center">
          <h1 className="text-3xl md:text-5xl font-bold leading-tight mb-4">
            Находите лучшие скидки<br />на Wildberries и Ozon
          </h1>
          <p className="text-lg md:text-xl opacity-90 mb-8 max-w-2xl mx-auto">
            Автоматический мониторинг цен, уведомления о скидках и AI-помощник
            для умных покупок
          </p>
          <a
            href="https://t.me/price_monitor_bot"
            className="inline-block bg-white text-accent px-8 py-3.5 rounded-xl text-lg font-semibold hover:bg-gray-100 transition-colors shadow-lg"
          >
            Начать бесплатно
          </a>
          <p className="mt-4 text-sm opacity-75">Бесплатно в Telegram. Без регистрации.</p>
        </div>
      </header>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-4 py-16">
        <h2 className="text-2xl md:text-3xl font-bold text-center text-gray-900 mb-12">
          Как это работает
        </h2>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="text-center">
            <div className="w-16 h-16 bg-accent/10 rounded-2xl flex items-center justify-center mx-auto mb-4 text-3xl">
              🔍
            </div>
            <h3 className="font-semibold text-gray-900 mb-2">Мониторинг</h3>
            <p className="text-gray-600 text-sm">
              Отслеживаем цены на миллионы товаров на Wildberries и Ozon каждый час
            </p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 bg-accent/10 rounded-2xl flex items-center justify-center mx-auto mb-4 text-3xl">
              🔔
            </div>
            <h3 className="font-semibold text-gray-900 mb-2">Оповещения</h3>
            <p className="text-gray-600 text-sm">
              Настройте оповещения по ключевым словам и получайте уведомления мгновенно
            </p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 bg-accent/10 rounded-2xl flex items-center justify-center mx-auto mb-4 text-3xl">
              📊
            </div>
            <h3 className="font-semibold text-gray-900 mb-2">Арбитраж</h3>
            <p className="text-gray-600 text-sm">
              Сравнивайте цены между маркетплейсами и находите самые выгодные предложения
            </p>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="bg-gray-50 py-16">
        <div className="max-w-5xl mx-auto px-4">
          <div className="grid grid-cols-3 gap-8 text-center">
            <div>
              <p className="text-3xl md:text-4xl font-bold text-accent">10M+</p>
              <p className="text-sm text-gray-600 mt-1">Товаров отслеживаем</p>
            </div>
            <div>
              <p className="text-3xl md:text-4xl font-bold text-accent">24/7</p>
              <p className="text-sm text-gray-600 mt-1">Мониторинг цен</p>
            </div>
            <div>
              <p className="text-3xl md:text-4xl font-bold text-accent">50K+</p>
              <p className="text-sm text-gray-600 mt-1">Пользователей</p>
            </div>
          </div>
        </div>
      </section>

      {/* AI Section */}
      <section className="max-w-5xl mx-auto px-4 py-16">
        <div className="bg-gradient-to-r from-accent/5 to-accent/10 rounded-2xl p-8 md:p-12 text-center">
          <h2 className="text-2xl md:text-3xl font-bold text-gray-900 mb-4">
            🤖 AI-помощник для покупок
          </h2>
          <p className="text-gray-600 mb-6 max-w-xl mx-auto">
            Спросите &laquo;Где дешевле iPhone 15?&raquo; или &laquo;Когда лучше купить ноутбук?&raquo; -
            наш AI проанализирует историю цен и подскажет оптимальное время покупки.
          </p>
          <a
            href="https://t.me/price_monitor_bot"
            className="inline-block bg-accent text-white px-6 py-3 rounded-xl font-medium hover:bg-accent-dark transition-colors"
          >
            Попробовать бесплатно
          </a>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-accent text-white py-16">
        <div className="max-w-5xl mx-auto px-4 text-center">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            Начните экономить уже сегодня
          </h2>
          <p className="opacity-90 mb-8 max-w-lg mx-auto">
            Откройте бота в Telegram и настройте первое оповещение за 30 секунд.
            Это бесплатно.
          </p>
          <a
            href="https://t.me/price_monitor_bot"
            className="inline-block bg-white text-accent px-8 py-3.5 rounded-xl text-lg font-semibold hover:bg-gray-100 transition-colors"
          >
            Открыть в Telegram
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-8">
        <div className="max-w-5xl mx-auto px-4 text-center text-sm">
          <p>&copy; 2024 Монитор Цен. Все права защищены.</p>
        </div>
      </footer>
    </div>
  );
};
