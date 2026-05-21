import React from 'react';
import { SkeletonCard } from './SkeletonCard';

export const SkeletonList: React.FC = () => {
  return (
    <div className="px-4 grid grid-cols-2 gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
};
