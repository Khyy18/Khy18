export default function AliceAvatar() {
  return (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="alice-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#9333ea" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#alice-grad)" />
      <path
        d="M14 12h12v2H14v-2zm2 4h8v2h-8v-2zm0 4h8v2h-8v-2zm0 4h5v2h-5v-2zm-2 4h12v2H14v-2z"
        fill="white"
        opacity="0.9"
      />
    </svg>
  )
}
