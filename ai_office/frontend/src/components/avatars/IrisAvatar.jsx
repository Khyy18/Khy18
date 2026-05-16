export default function IrisAvatar() {
  return (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="iris-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#f97316" />
          <stop offset="100%" stopColor="#ef4444" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#iris-grad)" />
      <path
        d="M16 28V14l14-4v14"
        fill="none"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.9"
      />
      <path
        d="M26 24l4-2-4-2v4z"
        fill="white"
        opacity="0.9"
      />
      <circle cx="16" cy="28" r="3" fill="white" opacity="0.7" />
    </svg>
  )
}
