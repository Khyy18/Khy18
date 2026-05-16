export default function OscarAvatar() {
  return (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="oscar-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#22c55e" />
          <stop offset="100%" stopColor="#10b981" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#oscar-grad)" />
      <circle cx="20" cy="20" r="8" fill="none" stroke="white" strokeWidth="2" opacity="0.9" />
      <text x="20" y="24" textAnchor="middle" fill="white" fontSize="10" fontWeight="bold" opacity="0.9">$</text>
    </svg>
  )
}
