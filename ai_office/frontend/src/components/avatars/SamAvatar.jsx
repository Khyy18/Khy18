export default function SamAvatar() {
  return (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="sam-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#sam-grad)" />
      <path
        d="M12 18l4-6h2l-4 6 4 6h-2l-4-6zm16 0l-4-6h-2l4 6-4 6h2l4-6z"
        fill="white"
        opacity="0.9"
      />
      <rect x="17" y="17" width="6" height="2" rx="1" fill="white" opacity="0.7" />
    </svg>
  )
}
