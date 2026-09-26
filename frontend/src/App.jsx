import { useEffect, useState } from 'react'
import { fetchBriefing } from './api'
import Briefing from './Briefing'

const EXAMPLES = ['Multiple Sclerosis', 'Type 2 Diabetes', 'Non-Small Cell Lung Cancer', 'Rheumatoid Arthritis']

export default function App() {
  const [condition, setCondition] = useState('')
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)
  const [briefing, setBriefing] = useState(null)

  useEffect(() => {
    if (!loading) return
    const start = Date.now()
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(id)
  }, [loading])

  async function handleSubmit(e) {
    e.preventDefault()
    const trimmed = condition.trim()
    if (!trimmed) return

    setLoading(true)
    setElapsed(0)
    setError(null)
    setBriefing(null)
    try {
      setBriefing(await fetchBriefing(trimmed))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Condition Briefing Generator</h1>
        <p className="subtitle">
          Four agents build a structured briefing in parallel: condition overview (PubMed reviews), standard of
          care (PubMed guidelines), emerging treatments (ClinicalTrials.gov trials), and key companies &amp;
          institutions (ClinicalTrials.gov sponsors).
        </p>
      </header>

      <form onSubmit={handleSubmit} className="condition-form">
        <input
          type="text"
          placeholder="e.g. Multiple Sclerosis"
          value={condition}
          onChange={(e) => setCondition(e.target.value)}
          disabled={loading}
          maxLength={200}
          aria-label="Medical condition"
        />
        <button type="submit" disabled={loading || !condition.trim()}>
          {loading ? 'Generating…' : 'Generate Briefing'}
        </button>
      </form>
      <div className="examples">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" className="chip" disabled={loading} onClick={() => setCondition(ex)}>
            {ex}
          </button>
        ))}
      </div>

      {loading && (
        <p className="status">
          <span className="spinner" aria-hidden="true" /> Agents are working in parallel… {elapsed}s (usually under 30 seconds)
        </p>
      )}
      {error && <p className="status error">{error}</p>}
      {briefing && <Briefing briefing={briefing} />}
    </div>
  )
}
