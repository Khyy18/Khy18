/**
 * StreamingMessage - renders streaming LLM text with a blinking cursor.
 * Props:
 *   text - accumulated text string
 *   isComplete - whether the stream has finished
 */
export default function StreamingMessage({ text, isComplete }) {
  // Detect code blocks for monospace rendering
  const hasCodeBlock = text.includes('```')

  return (
    <div className="mt-2 bg-white/5 rounded-xl px-3 py-2">
      <pre
        className={`text-white/80 text-xs whitespace-pre-wrap break-words ${
          hasCodeBlock ? 'font-mono' : 'font-sans'
        }`}
      >
        {text}
        {!isComplete && (
          <span className="inline-block w-1.5 h-3 bg-accent ml-0.5 align-middle animate-cursor-blink" />
        )}
      </pre>
    </div>
  )
}
