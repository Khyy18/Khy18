import { useState } from 'react'

/**
 * Registration page with email, password, company name
 * Dark themed card matching existing design
 */
export default function RegisterPage({ onRegister, onSwitchToLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const success = await onRegister(email, password, companyName)
      if (!success) {
        setError('Registration failed. Please try again.')
      }
    } catch (err) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-white/5 border border-white/10 rounded-2xl p-6">
        <h2 className="text-xl font-semibold text-white text-center mb-6">
          Create your AI Office
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-white/60 text-sm mb-1">Company Name</label>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-white/30 focus:outline-none focus:border-accent"
              placeholder="Your Company"
              required
            />
          </div>

          <div>
            <label className="block text-white/60 text-sm mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-white/30 focus:outline-none focus:border-accent"
              placeholder="you@company.com"
              required
            />
          </div>

          <div>
            <label className="block text-white/60 text-sm mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-white/30 focus:outline-none focus:border-accent"
              placeholder="Min 6 characters"
              required
              minLength={6}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent hover:bg-accent/80 text-white font-medium py-2.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? 'Creating account...' : 'Create Account'}
          </button>
        </form>

        <p className="mt-4 text-center text-white/40 text-sm">
          Already have an account?{' '}
          <button
            onClick={onSwitchToLogin}
            className="text-accent hover:text-accent/80 transition-colors"
          >
            Sign In
          </button>
        </p>
      </div>
    </div>
  )
}
