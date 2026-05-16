export default function NovaAvatar() {
  return (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="nova-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#nova-grad)" />
      <rect x="11" y="12" width="18" height="5" rx="1.5" fill="white" opacity="0.9" />
      <rect x="11" y="19" width="18" height="5" rx="1.5" fill="white" opacity="0.7" />
      <rect x="11" y="26" width="18" height="5" rx="1.5" fill="white" opacity="0.5" />
      <circle cx="14" cy="14.5" r="1" fill="url(#nova-grad)" />
      <circle cx="14" cy="21.5" r="1" fill="url(#nova-grad)" />
      <circle cx="14" cy="28.5" r="1" fill="url(#nova-grad)" />
    </svg>
  )
}
