import React, { useEffect, useRef, useState } from 'react';
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
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={cardRef}
      onClick={() => navigate(`/product/${product.id}`)}
      className={`bg-tg-secondary-bg rounded-xl p-3 cursor-pointer active:scale-[0.97] transition-all duration-300 ${
        isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
      }`}
    >
      <div className="relative">
        {!imageLoaded && !imageError && (
          <div className="w-full h-40 rounded-lg bg-gradient-to-br from-gray-200 to-gray-300" />
        )}
        {imageError && (
          <div className="w-full h-40 rounded-lg bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center">
            <svg
              className="w-10 h-10 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
              />
            </svg>
          </div>
        )}
        <img
          src={product.image_url}
          alt={product.title}
          className={`w-full h-40 object-cover rounded-lg ${
            imageLoaded && !imageError ? 'block' : 'hidden'
          }`}
          loading="lazy"
          onLoad={() => setImageLoaded(true)}
          onError={() => setImageError(true)}
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
