import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigation } from './components/Navigation';
import { useTheme } from './hooks/useTheme';
import { useWebSocket } from './hooks/useWebSocket';
import { Feed } from './pages/Feed';
import { ProductDetail } from './pages/ProductDetail';
import { Categories } from './pages/Categories';
import { Alerts } from './pages/Alerts';
import { Favorites } from './pages/Favorites';
import { Profile } from './pages/Profile';
import { Chat } from './pages/Chat';
import { Arbitrage } from './pages/Arbitrage';
import { Landing } from './pages/Landing';
import { Compare } from './pages/Compare';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
    },
  },
});

const AppContent: React.FC = () => {
  useTheme();
  useWebSocket();
  return (
    <Routes>
      <Route path="/landing" element={<Landing />} />
      <Route
        path="*"
        element={
          <div className="min-h-screen bg-tg-bg animate-fade-in">
            <Routes>
              <Route path="/" element={<Feed />} />
              <Route path="/product/:id" element={<ProductDetail />} />
              <Route path="/categories" element={<Categories />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/favorites" element={<Favorites />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/arbitrage" element={<Arbitrage />} />
              <Route path="/compare" element={<Compare />} />
            </Routes>
            <Navigation />
          </div>
        }
      />
    </Routes>
  );
};

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
