import React from 'react';

export const SkeletonCard: React.FC = () => {
  return (
    <div className="bg-tg-secondary-bg rounded-xl p-3">
      <div className="w-full h-40 rounded-lg animate-shimmer" />
      <div className="mt-2 space-y-2">
        <div className="h-3 w-full rounded animate-shimmer" />
        <div className="h-3 w-3/4 rounded animate-shimmer" />
        <div className="flex items-center gap-2 mt-2">
          <div className="h-4 w-16 rounded animate-shimmer" />
          <div className="h-3 w-12 rounded animate-shimmer" />
        </div>
      </div>
    </div>
  );
};
