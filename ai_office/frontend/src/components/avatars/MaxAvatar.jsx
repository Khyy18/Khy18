export default function MaxAvatar() {
  return (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="max-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ec4899" />
          <stop offset="100%" stopColor="#f43f5e" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#max-grad)" />
      <circle cx="16" cy="24" r="5" fill="white" opacity="0.9" />
      <circle cx="16" cy="24" r="3" fill="url(#max-grad)" opacity="0.6" />
      <path
        d="M24 12v14M24 12l4 4M24 12l-4 4"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.9"
      />
    </svg>
  )
}
