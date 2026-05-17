import { useState } from 'react'

const PLANS = [
  { id: 'starter', name: 'Starter', price: '$49/mo', features: ['5 AI Agents', '1,000 tasks/mo', 'Email support'] },
  { id: 'pro', name: 'Pro', price: '$149/mo', features: ['12 AI Agents', '10,000 tasks/mo', 'Priority support'] },
  { id: 'agency', name: 'Agency', price: '$499/mo', features: ['Unlimited Agents', '50,000 tasks/mo', 'Dedicated support'] },
]

const AVAILABLE_AGENTS = [
  'Alice', 'Sam', 'Max', 'Eva', 'Leo', 'Nova',
  'Iris', 'Oscar', 'outbound_sales', 'zenith', 'text_agency', 'combo_bot'
]

/**
 * Multi-step onboarding wizard
 * Step 1: Confirm company name
 * Step 2: Choose plan
 * Step 3: Select agents
 * Step 4: Success
 */
export default function OnboardingWizard({ onComplete, companyName: initialCompany }) {
  const [step, setStep] = useState(1)
  const [companyName, setCompanyName] = useState(initialCompany || '')
  const [selectedPlan, setSelectedPlan] = useState('starter')
  const [selectedAgents, setSelectedAgents] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const toggleAgent = (agent) => {
    setSelectedAgents(prev =>
      prev.includes(agent)
        ? prev.filter(a => a !== agent)
        : [...prev, agent]
    )
  }

  const handleComplete = async () => {
    setLoading(true)
    setError(null)
    try {
      const token = localStorage.getItem('ai_office_token')
      const response = await fetch('/api/onboarding/setup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          company_name: companyName,
          plan_choice: selectedPlan,
          selected_agents: selectedAgents
        })
      })
      if (!response.ok) {
        throw new Error('Setup failed')
      }
      setStep(4)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-lg bg-white/5 border border-white/10 rounded-2xl p-6">
        {/* Progress indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {[1, 2, 3, 4].map(s => (
            <div
              key={s}
              className={`w-2.5 h-2.5 rounded-full transition-colors ${
                s <= step ? 'bg-accent' : 'bg-white/20'
              }`}
            />
          ))}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Step 1: Company name */}
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-white text-center">
              Confirm your company name
            </h2>
            <p className="text-white/50 text-sm text-center">
              This will be your workspace name in AI Office
            </p>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-white/30 focus:outline-none focus:border-accent"
              placeholder="Company Name"
            />
            <button
              onClick={() => setStep(2)}
              disabled={!companyName.trim()}
              className="w-full bg-accent hover:bg-accent/80 text-white font-medium py-2.5 rounded-lg transition-colors disabled:opacity-50"
            >
              Continue
            </button>
          </div>
        )}

        {/* Step 2: Choose plan */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-white text-center">
              Choose your plan
            </h2>
            <div className="grid gap-3">
              {PLANS.map(plan => (
                <button
                  key={plan.id}
                  onClick={() => setSelectedPlan(plan.id)}
                  className={`p-4 rounded-xl border text-left transition-all ${
                    selectedPlan === plan.id
                      ? 'border-accent bg-accent/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white font-medium">{plan.name}</span>
                    <span className="text-accent font-semibold">{plan.price}</span>
                  </div>
                  <ul className="space-y-1">
                    {plan.features.map(f => (
                      <li key={f} className="text-white/50 text-sm">{f}</li>
                    ))}
                  </ul>
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setStep(1)}
                className="flex-1 bg-white/5 hover:bg-white/10 text-white font-medium py-2.5 rounded-lg transition-colors border border-white/10"
              >
                Back
              </button>
              <button
                onClick={() => setStep(3)}
                className="flex-1 bg-accent hover:bg-accent/80 text-white font-medium py-2.5 rounded-lg transition-colors"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Select agents */}
        {step === 3 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-white text-center">
              Select your AI agents
            </h2>
            <p className="text-white/50 text-sm text-center">
              Choose which agents to activate in your office
            </p>
            <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
              {AVAILABLE_AGENTS.map(agent => (
                <button
                  key={agent}
                  onClick={() => toggleAgent(agent)}
                  className={`p-3 rounded-lg border text-sm text-left transition-all ${
                    selectedAgents.includes(agent)
                      ? 'border-accent bg-accent/10 text-white'
                      : 'border-white/10 bg-white/5 text-white/60 hover:border-white/20'
                  }`}
                >
                  {agent}
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setStep(2)}
                className="flex-1 bg-white/5 hover:bg-white/10 text-white font-medium py-2.5 rounded-lg transition-colors border border-white/10"
              >
                Back
              </button>
              <button
                onClick={handleComplete}
                disabled={loading || selectedAgents.length === 0}
                className="flex-1 bg-accent hover:bg-accent/80 text-white font-medium py-2.5 rounded-lg transition-colors disabled:opacity-50"
              >
                {loading ? 'Setting up...' : 'Complete Setup'}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Success */}
        {step === 4 && (
          <div className="space-y-4 text-center">
            <div className="text-4xl mb-2">&#10003;</div>
            <h2 className="text-xl font-semibold text-white">
              Your AI Office is ready!
            </h2>
            <p className="text-white/50 text-sm">
              {selectedAgents.length} agents activated on the {selectedPlan} plan
            </p>
            <button
              onClick={onComplete}
              className="w-full bg-accent hover:bg-accent/80 text-white font-medium py-2.5 rounded-lg transition-colors"
            >
              Enter AI Office
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
