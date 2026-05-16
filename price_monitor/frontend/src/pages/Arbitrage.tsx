import React, { useState } from 'react';
import { useArbitrage } from '../hooks/useApi';
import { ArbitrageCard } from '../components/ArbitrageCard';

export const Arbitrage: React.FC = () => {
  const [minDiff, setMinDiff] = useState<number | undefined>(10);
  const [marketplace, setMarketplace] = useState<string | undefined>();
  const { data: items, isLoading } = useArbitrage(minDiff, marketplace);

  return (
    <div className="pb-16 px-4 pt-4">
      <h1 className="text-xl font-bold text-tg-text mb-2">Арбитраж цен</h1>
      <p className="text-sm text-tg-hint mb-4">
        Сравнение цен между Wildberries и Ozon
      </p>

      <div className="flex gap-2 mb-4 overflow-x-auto scrollbar-hide">
        <button
          onClick={() => setMinDiff(undefined)}
          className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap ${
            minDiff === undefined ? 'bg-accent text-white' : 'bg-tg-secondary-bg text-tg-text'
          }`}
        >
          Все
        </button>
        {[5, 10, 20, 30].map((val) => (
          <button
            key={val}
            onClick={() => setMinDiff(val)}
            className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap ${
              minDiff === val ? 'bg-accent text-white' : 'bg-tg-secondary-bg text-tg-text'
            }`}
          >
            от {val}%
          </button>
        ))}
      </div>

      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setMarketplace(undefined)}
          className={`px-3 py-1.5 rounded-full text-sm ${
            !marketplace ? 'bg-accent text-white' : 'bg-tg-secondary-bg text-tg-text'
          }`}
        >
          Все
        </button>
        <button
          onClick={() => setMarketplace('wb')}
          className={`px-3 py-1.5 rounded-full text-sm ${
            marketplace === 'wb' ? 'bg-accent text-white' : 'bg-tg-secondary-bg text-tg-text'
          }`}
        >
          Дешевле на WB
        </button>
        <button
          onClick={() => setMarketplace('ozon')}
          className={`px-3 py-1.5 rounded-full text-sm ${
            marketplace === 'ozon' ? 'bg-accent text-white' : 'bg-tg-secondary-bg text-tg-text'
          }`}
        >
          Дешевле на Ozon
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 bg-tg-secondary-bg rounded-xl animate-pulse" />
          ))}
        </div>
      ) : items && items.length > 0 ? (
        <div className="space-y-3">
          {items.map((item) => (
            <ArbitrageCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <p className="text-4xl mb-3">📊</p>
          <p className="text-tg-hint text-sm">
            Нет товаров с такой разницей в цене
          </p>
        </div>
      )}
    </div>
  );
};
