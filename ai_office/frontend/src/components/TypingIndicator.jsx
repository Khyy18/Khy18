/**
 * Three dots typing indicator with sequential pulse animation
 */
export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-2 py-1">
      <span className="w-1.5 h-1.5 rounded-full bg-accent animate-typing-dot-1" />
      <span className="w-1.5 h-1.5 rounded-full bg-accent animate-typing-dot-2" />
      <span className="w-1.5 h-1.5 rounded-full bg-accent animate-typing-dot-3" />
    </div>
  )
}
