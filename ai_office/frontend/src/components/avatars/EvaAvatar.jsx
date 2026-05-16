export default function EvaAvatar() {
  return (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="eva-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#14b8a6" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#eva-grad)" />
      <rect x="10" y="24" width="4" height="6" rx="1" fill="white" opacity="0.9" />
      <rect x="16" y="18" width="4" height="12" rx="1" fill="white" opacity="0.9" />
      <rect x="22" y="14" width="4" height="16" rx="1" fill="white" opacity="0.9" />
      <rect x="28" y="20" width="4" height="10" rx="1" fill="white" opacity="0.9" />
    </svg>
  )
}
