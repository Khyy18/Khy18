import React from 'react';
import { formatPrice } from '../api/client';
import type { ArbitrageItem } from '../types';

interface ArbitrageCardProps {
  item: ArbitrageItem;
}

export const ArbitrageCard: React.FC<ArbitrageCardProps> = ({ item }) => {
  return (
    <div className="bg-tg-secondary-bg rounded-xl p-3">
      <div className="flex gap-3">
        <img
          src={item.image_url}
          alt={item.title}
          className="w-20 h-20 object-cover rounded-lg flex-shrink-0"
          loading="lazy"
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-tg-text line-clamp-2 leading-tight">{item.title}</p>
          <div className="mt-2 flex items-center gap-2">
            <span className="bg-green-100 text-green-700 text-xs font-bold px-2 py-0.5 rounded-full">
              -{item.diff_percent}%
            </span>
            <span className="text-xs text-tg-hint">
              дешевле на {item.cheaper_on === 'wb' ? 'WB' : 'Ozon'}
            </span>
          </div>
          <div className="mt-2 flex gap-4 text-xs">
            <div>
              <span className="text-tg-hint">WB: </span>
              <span className={item.cheaper_on === 'wb' ? 'font-bold text-green-600' : 'text-tg-text'}>
                {formatPrice(item.wb_price)}
              </span>
            </div>
            <div>
              <span className="text-tg-hint">Ozon: </span>
              <span className={item.cheaper_on === 'ozon' ? 'font-bold text-green-600' : 'text-tg-text'}>
                {formatPrice(item.ozon_price)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
