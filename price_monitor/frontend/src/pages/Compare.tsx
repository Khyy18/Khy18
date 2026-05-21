import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useCompare } from '../hooks/useApi';
import { formatPrice } from '../api/client';
import type { CompareProduct } from '../types';

const CompareColumn: React.FC<{ product: CompareProduct }> = ({ product }) => (
  <div className="flex-1 min-w-0">
    <div className="aspect-square bg-tg-secondary-bg rounded-lg overflow-hidden mb-2">
      {product.image_url ? (
        <img
          src={product.image_url}
          alt={product.title}
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-3xl">
          📦
        </div>
      )}
    </div>
    <h3 className="text-sm font-medium text-tg-text line-clamp-2 mb-1">
      {product.title}
    </h3>
    <p className="text-lg font-bold text-accent">
      {formatPrice(product.current_price)}
    </p>
    {product.original_price > product.current_price && (
      <p className="text-xs text-tg-hint line-through">
        {formatPrice(product.original_price)}
      </p>
    )}
    {product.discount_percent > 0 && (
      <span className="inline-block mt-1 px-2 py-0.5 bg-red-500/10 text-red-500 text-xs font-medium rounded">
        -{product.discount_percent}%
      </span>
    )}
    <div className="mt-2 space-y-1">
      <div className="flex items-center gap-1 text-xs text-tg-hint">
        <span>⭐</span>
        <span>{product.rating.toFixed(1)}</span>
      </div>
      <div className="text-xs text-tg-hint uppercase">
        {product.marketplace === 'wb' ? 'Wildberries' : 'Ozon'}
      </div>
    </div>
  </div>
);

export const Compare: React.FC = () => {
  const [searchParams] = useSearchParams();
  const idsParam = searchParams.get('ids') || '';
  const ids = idsParam.split(',').filter(Boolean);

  const { data, isLoading, error } = useCompare(ids);

  if (ids.length < 2) {
    return (
      <div className="p-4 text-center">
        <p className="text-tg-hint">
          Выберите минимум 2 товара для сравнения
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <div className="h-8 bg-tg-secondary-bg rounded animate-pulse" />
        <div className="flex gap-4">
          <div className="flex-1 h-64 bg-tg-secondary-bg rounded-xl animate-pulse" />
          <div className="flex-1 h-64 bg-tg-secondary-bg rounded-xl animate-pulse" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 text-center">
        <p className="text-red-500">Ошибка загрузки данных</p>
      </div>
    );
  }

  const products = data.products;

  return (
    <div className="pb-16 px-4 pt-4">
      <h1 className="text-xl font-bold text-tg-text mb-4">Сравнение товаров</h1>

      <div className="flex gap-4 mb-6">
        {products.map((product) => (
          <CompareColumn key={product.id} product={product} />
        ))}
      </div>

      {/* Comparison table */}
      <div className="bg-tg-secondary-bg rounded-xl p-4">
        <h2 className="font-medium text-tg-text mb-3">Характеристики</h2>
        <table className="w-full text-sm">
          <tbody>
            <tr className="border-b border-tg-bg">
              <td className="py-2 text-tg-hint">Цена</td>
              {products.map((p) => (
                <td key={p.id} className="py-2 text-tg-text font-medium text-right">
                  {formatPrice(p.current_price)}
                </td>
              ))}
            </tr>
            <tr className="border-b border-tg-bg">
              <td className="py-2 text-tg-hint">Скидка</td>
              {products.map((p) => (
                <td key={p.id} className="py-2 text-tg-text text-right">
                  {p.discount_percent > 0 ? `-${p.discount_percent}%` : '-'}
                </td>
              ))}
            </tr>
            <tr className="border-b border-tg-bg">
              <td className="py-2 text-tg-hint">Рейтинг</td>
              {products.map((p) => (
                <td key={p.id} className="py-2 text-tg-text text-right">
                  ⭐ {p.rating.toFixed(1)}
                </td>
              ))}
            </tr>
            <tr>
              <td className="py-2 text-tg-hint">Маркетплейс</td>
              {products.map((p) => (
                <td key={p.id} className="py-2 text-tg-text text-right">
                  {p.marketplace === 'wb' ? 'WB' : 'Ozon'}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Price history */}
      <div className="mt-4 bg-tg-secondary-bg rounded-xl p-4">
        <h2 className="font-medium text-tg-text mb-3">История цен</h2>
        {products.map((p) => (
          <div key={p.id} className="mb-3 last:mb-0">
            <p className="text-xs text-tg-hint mb-1 line-clamp-1">{p.title}</p>
            <div className="flex gap-1 items-end h-12">
              {p.price_history.slice(-14).map((point, i) => {
                const prices = p.price_history.map((ph) => ph.price);
                const max = Math.max(...prices);
                const min = Math.min(...prices);
                const range = max - min || 1;
                const height = ((point.price - min) / range) * 100;
                return (
                  <div
                    key={i}
                    className="flex-1 bg-accent/60 rounded-t"
                    style={{ height: `${Math.max(height, 5)}%` }}
                    title={`${point.date}: ${point.price}`}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
