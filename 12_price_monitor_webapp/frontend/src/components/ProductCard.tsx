import React from 'react';
import { useNavigate } from 'react-router-dom';
import { DiscountBadge } from './DiscountBadge';
import { SparklineChart } from './SparklineChart';
import { formatPrice } from '../api/client';
import type { Product } from '../types';

interface ProductCardProps {
  product: Product;
}

export const ProductCard: React.FC<ProductCardProps> = ({ product }) => {
  const navigate = useNavigate();

  return (
    <div
      onClick={() => navigate(`/product/${product.id}`)}
      className="bg-tg-secondary-bg rounded-xl p-3 cursor-pointer active:scale-[0.98] transition-transform"
    >
      <div className="relative">
        <img
          src={product.image_url}
          alt={product.title}
          className="w-full h-40 object-cover rounded-lg"
          loading="lazy"
        />
        {product.discount_percent > 0 && (
          <div className="absolute top-2 left-2">
            <DiscountBadge percent={product.discount_percent} />
          </div>
        )}
        <div className="absolute top-2 right-2 bg-white/80 rounded px-1.5 py-0.5 text-xs font-medium">
          {product.marketplace === 'wb' ? 'WB' : 'Ozon'}
        </div>
      </div>
      <div className="mt-2">
        <p className="text-sm text-tg-text line-clamp-2 leading-tight">{product.title}</p>
        <div className="flex items-center justify-between mt-2">
          <div>
            <span className="text-base font-bold text-accent">
              {formatPrice(product.current_price)}
            </span>
            {product.original_price > product.current_price && (
              <span className="text-xs text-tg-hint line-through ml-1.5">
                {formatPrice(product.original_price)}
              </span>
            )}
          </div>
        </div>
        {product.price_history.length > 1 && (
          <div className="mt-2 h-8">
            <SparklineChart points={product.price_history} />
          </div>
        )}
      </div>
    </div>
  );
};
