import React from 'react';

interface DiscountBadgeProps {
  percent: number;
}

export const DiscountBadge: React.FC<DiscountBadgeProps> = ({ percent }) => {
  const getColor = () => {
    if (percent >= 50) return 'bg-red-500';
    if (percent >= 30) return 'bg-accent';
    return 'bg-yellow-500';
  };

  return (
    <span className={`${getColor()} text-white text-xs font-bold px-2 py-0.5 rounded-full`}>
      -{percent}%
    </span>
  );
};
