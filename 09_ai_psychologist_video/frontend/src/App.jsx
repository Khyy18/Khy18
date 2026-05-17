import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import CallScreen from './components/CallScreen';
import TopUp from './components/TopUp';

/**
 * Обертка приложения.
 * SDKProvider из @telegram-apps/sdk-react подключается только если приложение
 * запущено внутри Telegram (есть window.Telegram.WebApp). В dev-режиме работает без него.
 */
function TelegramWrapper({ children }) {
  const [SdkProvider, setSdkProvider] = React.useState(null);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    // Пытаемся загрузить SDK - если Telegram контекст недоступен, работаем без него
    import('@telegram-apps/sdk-react')
      .then((mod) => {
        if (mod.SDKProvider) {
          setSdkProvider(() => mod.SDKProvider);
        }
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
      });
  }, []);

  if (!loaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--tg-theme-bg-color)]">
        <div className="animate-spin w-8 h-8 border-4 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (SdkProvider) {
    return <SdkProvider acceptCustomStyles>{children}</SdkProvider>;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <TelegramWrapper>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/call/:sessionId" element={<CallScreen />} />
        <Route path="/topup" element={<TopUp />} />
      </Routes>
    </TelegramWrapper>
  );
}
