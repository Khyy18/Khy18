import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useProduct, useToggleFavorite } from '../hooks/useApi';
import { useTelegram } from '../hooks/useTelegram';
import { PriceChart } from '../components/PriceChart';
import { DiscountBadge } from '../components/DiscountBadge';
import { formatPrice } from '../api/client';

export const ProductDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showBackButton, onBackButtonClick, hideBackButton, hapticFeedback } = useTelegram();
  const { data: product, isLoading } = useProduct(id || '');
  const toggleFavorite = useToggleFavorite();

  useEffect(() => {
    showBackButton();
    onBackButtonClick(() => {
      navigate(-1);
      hideBackButton();
    });
    return () => hideBackButton();
  }, []);

  if (isLoading || !product) {
    return (
      <div className="p-4 space-y-4">
        <div className="h-64 bg-tg-secondary-bg rounded-xl animate-pulse" />
        <div className="h-6 bg-tg-secondary-bg rounded w-3/4 animate-pulse" />
        <div className="h-48 bg-tg-secondary-bg rounded-xl animate-pulse" />
      </div>
    );
  }

  const handleFavorite = () => {
    hapticFeedback('impact');
    toggleFavorite.mutate(product.id);
  };

  const handleBuy = () => {
    window.open(product.url, '_blank');
  };

  return (
    <div className="pb-20">
      <div className="relative">
        <img
          src={product.image_url}
          alt={product.title}
          className="w-full h-64 object-cover"
        />
        {product.discount_percent > 0 && (
          <div className="absolute top-4 left-4">
            <DiscountBadge percent={product.discount_percent} />
          </div>
        )}
        <button
          onClick={handleFavorite}
          className="absolute top-4 right-4 w-10 h-10 bg-white/80 rounded-full flex items-center justify-center"
        >
          {product.is_favorite ? '❤️' : '🤍'}
        </button>
      </div>

      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="bg-tg-secondary-bg px-2 py-0.5 rounded text-xs font-medium">
            {product.marketplace === 'wb' ? 'Wildberries' : 'Ozon'}
          </span>
          <span className="text-xs text-tg-hint">{product.category_name}</span>
        </div>

        <h1 className="text-lg font-semibold text-tg-text leading-tight">{product.title}</h1>

        <div className="mt-3 flex items-baseline gap-3">
          <span className="text-2xl font-bold text-accent">
            {formatPrice(product.current_price)}
          </span>
          {product.original_price > product.current_price && (
            <span className="text-base text-tg-hint line-through">
              {formatPrice(product.original_price)}
            </span>
          )}
        </div>

        <div className="mt-6">
          <h2 className="text-base font-semibold text-tg-text mb-3">История цены</h2>
          <PriceChart points={product.price_history} />
        </div>

        <button
          onClick={handleBuy}
          className="mt-6 w-full py-3 bg-accent text-white font-semibold rounded-xl text-center active:bg-accent-dark transition-colors"
        >
          Купить на {product.marketplace === 'wb' ? 'Wildberries' : 'Ozon'}
        </button>
      </div>
    </div>
  );
};
