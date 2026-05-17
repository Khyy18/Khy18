import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, ArrowRight, ArrowLeft, Building, Mail, Target, Rocket } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { useToast } from '../components/ui/Toast'

const STEPS = [
  { id: 1, title: 'Company Info', icon: Building },
  { id: 2, title: 'Email Setup', icon: Mail },
  { id: 3, title: 'Ideal Customer', icon: Target },
  { id: 4, title: 'First Campaign', icon: Rocket },
]

export default function Onboarding() {
  const [currentStep, setCurrentStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    company_name: '', domain: '',
    smtp_host: '', smtp_port: '587', smtp_user: '', smtp_password: '',
    industry: '', company_size: '', titles: '', geo: '',
    campaign_name: '',
  })
  const { get, post } = useApi()
  const navigate = useNavigate()
  const toast = useToast()

  useEffect(() => {
    get('/api/onboarding/status').then(data => {
      if (data?.completed) navigate('/dashboard')
      if (data?.current_step) setCurrentStep(data.current_step)
    }).catch(() => {})
  }, [get, navigate])

  const updateField = (key, value) => setFormData(prev => ({ ...prev, [key]: value }))

  const handleNext = async () => {
    setLoading(true)
    try {
      const payload = getStepPayload()
      await post(`/api/onboarding/step${currentStep}`, payload)
      if (currentStep < 4) {
        setCurrentStep(currentStep + 1)
      } else {
        toast('Onboarding complete! Welcome aboard.', 'success')
        navigate('/dashboard')
      }
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const getStepPayload = () => {
    switch (currentStep) {
      case 1: return { company_name: formData.company_name, domain: formData.domain }
      case 2: return { smtp_host: formData.smtp_host, smtp_port: Number(formData.smtp_port), smtp_user: formData.smtp_user, smtp_password: formData.smtp_password }
      case 3: return { industry: formData.industry, company_size: formData.company_size, titles: formData.titles, geo: formData.geo }
      case 4: return { campaign_name: formData.campaign_name }
      default: return {}
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-white mb-2">Set up your account</h1>
          <p className="text-white/50">Complete these steps to get started</p>
        </div>

        {/* Stepper */}
        <div className="flex items-center justify-center mb-8 gap-2">
          {STEPS.map((step, i) => (
            <div key={step.id} className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                currentStep > step.id ? 'bg-green-500 text-white' :
                currentStep === step.id ? 'bg-accent text-white' :
                'bg-white/10 text-white/40'
              }`}>
                {currentStep > step.id ? <CheckCircle className="w-4 h-4" /> : step.id}
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-8 h-0.5 mx-1 ${currentStep > step.id ? 'bg-green-500' : 'bg-white/10'}`} />
              )}
            </div>
          ))}
        </div>

        {/* Form */}
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">{STEPS[currentStep - 1].title}</h2>

          <div className="space-y-4">
            {currentStep === 1 && (
              <>
                <div>
                  <label className="block text-sm text-white/70 mb-1">Company Name</label>
                  <input value={formData.company_name} onChange={e => updateField('company_name', e.target.value)} placeholder="Acme Inc" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
                <div>
                  <label className="block text-sm text-white/70 mb-1">Domain</label>
                  <input value={formData.domain} onChange={e => updateField('domain', e.target.value)} placeholder="acme.com" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
              </>
            )}

            {currentStep === 2 && (
              <>
                <div>
                  <label className="block text-sm text-white/70 mb-1">SMTP Host</label>
                  <input value={formData.smtp_host} onChange={e => updateField('smtp_host', e.target.value)} placeholder="smtp.gmail.com" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
                <div>
                  <label className="block text-sm text-white/70 mb-1">SMTP Port</label>
                  <input type="number" value={formData.smtp_port} onChange={e => updateField('smtp_port', e.target.value)} className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
                <div>
                  <label className="block text-sm text-white/70 mb-1">SMTP User</label>
                  <input value={formData.smtp_user} onChange={e => updateField('smtp_user', e.target.value)} placeholder="user@gmail.com" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
                <div>
                  <label className="block text-sm text-white/70 mb-1">SMTP Password</label>
                  <input type="password" value={formData.smtp_password} onChange={e => updateField('smtp_password', e.target.value)} placeholder="App password" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
              </>
            )}

            {currentStep === 3 && (
              <>
                <div>
                  <label className="block text-sm text-white/70 mb-1">Industry</label>
                  <input value={formData.industry} onChange={e => updateField('industry', e.target.value)} placeholder="SaaS, Fintech, Healthcare..." className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
                <div>
                  <label className="block text-sm text-white/70 mb-1">Company Size</label>
                  <input value={formData.company_size} onChange={e => updateField('company_size', e.target.value)} placeholder="50-200 employees" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
                <div>
                  <label className="block text-sm text-white/70 mb-1">Target Titles</label>
                  <input value={formData.titles} onChange={e => updateField('titles', e.target.value)} placeholder="CTO, VP Engineering, Head of Sales" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
                <div>
                  <label className="block text-sm text-white/70 mb-1">Geography</label>
                  <input value={formData.geo} onChange={e => updateField('geo', e.target.value)} placeholder="US, EU, Global" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
                </div>
              </>
            )}

            {currentStep === 4 && (
              <div>
                <label className="block text-sm text-white/70 mb-1">Campaign Name</label>
                <input value={formData.campaign_name} onChange={e => updateField('campaign_name', e.target.value)} placeholder="Q1 Outbound" className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-accent/50" />
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between mt-6">
            <button
              onClick={() => setCurrentStep(s => Math.max(1, s - 1))}
              disabled={currentStep === 1}
              className="flex items-center gap-2 px-4 py-2 text-sm text-white/60 hover:text-white disabled:opacity-30 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
            <button
              onClick={handleNext}
              disabled={loading}
              className="flex items-center gap-2 px-6 py-2.5 bg-accent hover:bg-accent/80 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Saving...' : currentStep === 4 ? 'Finish' : 'Continue'}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
