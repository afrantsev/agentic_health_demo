const SECTION_LABELS = {
  condition_overview: 'Condition overview',
  standard_of_care: 'Standard of care',
  emerging_treatments: 'Emerging treatments',
  companies_institutions: 'Companies & institutions',
}

const SOURCE_GROUPS = [
  {
    type: 'pubmed',
    title: 'Literature (PubMed)',
    describe: (condition) =>
      `Articles returned by PubMed searches for "${condition}" published in the last 5 years: epidemiology ` +
      'and burden reviews (Condition overview) and clinical practice guidelines (Standard of care).',
  },
  {
    type: 'trial',
    title: 'Clinical trials (ClinicalTrials.gov)',
    describe: (condition) =>
      `Active phase 2 and 3 interventional trials for "${condition}" returned by the Emerging treatments ` +
      'search of ClinicalTrials.gov.',
  },
  {
    type: 'sponsor',
    title: 'Trial sponsors (ClinicalTrials.gov)',
    describe: (condition, group) => {
      const { analyzed_trials: analyzed, total_trials: total } = group[0].meta
      const scope = analyzed < total ? `the first ${analyzed} of ${total}` : `all ${total}`
      return (
        `Computed from ${scope} active interventional trials for "${condition}" on ClinicalTrials.gov ` +
        '(recruiting, not yet recruiting, active, or enrolling by invitation). Each count is the number of those ' +
        'trials that list the organization as lead sponsor or collaborator; the top organizations are shown, and ' +
        'each link opens exactly the trials counted.'
      )
    },
  },
]

function List({ items }) {
  if (!items?.length) return <p className="muted">None listed.</p>
  return (
    <ul>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  )
}

function ExtLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  )
}

function AgentJson({ data }) {
  return (
    <details className="agent-json">
      <summary>Agent JSON output</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  )
}

function ConditionOverview({ data }) {
  return (
    <section className="section">
      <h2>Condition Overview</h2>
      <p>{data.summary}</p>

      <div className="facts">
        {data.key_facts.map((f, i) => (
          <div className="fact" key={i}>
            <div className="fact-value">{f.value}</div>
            <div className="fact-label">{f.label}</div>
            <div className="fact-source">
              {f.pmid ? (
                <ExtLink href={`https://pubmed.ncbi.nlm.nih.gov/${f.pmid}/`}>PMID {f.pmid}</ExtLink>
              ) : (
                <span className="muted">general knowledge</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <h3>What it is</h3>
      <p>{data.definition}</p>
      <h3>Subtypes &amp; stages</h3>
      <List items={data.subtypes} />
      <h3>Presentation &amp; diagnosis</h3>
      <p>{data.presentation_and_diagnosis}</p>
      <h3>Health system impact</h3>
      <p>{data.health_system_impact}</p>
      <AgentJson data={data} />
    </section>
  )
}

function StandardOfCare({ data }) {
  return (
    <section className="section">
      <h2>Current Standard of Care</h2>
      <p>{data.summary}</p>

      <h3>Treatment approach</h3>
      <table>
        <thead>
          <tr>
            <th>Setting</th>
            <th>Interventions</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {data.treatment_approach.map((t, i) => (
            <tr key={i}>
              <td className="nowrap">{t.setting}</td>
              <td>{t.interventions.join(', ')}</td>
              <td>{t.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Key guidelines</h3>
      {data.key_guidelines.length ? (
        <ul>
          {data.key_guidelines.map((g) => (
            <li key={g.pmid}>
              <ExtLink href={`https://pubmed.ncbi.nlm.nih.gov/${g.pmid}/`}>{g.title}</ExtLink>
              <span className="muted">
                {' '}
                — {[g.issuing_body, g.year].filter(Boolean).join(', ')} · PMID {g.pmid}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No relevant guidelines were found on PubMed.</p>
      )}

      <h3>Unmet needs</h3>
      <List items={data.unmet_needs} />
      <AgentJson data={data} />
    </section>
  )
}

function EmergingTreatments({ data }) {
  return (
    <section className="section">
      <h2>Emerging Treatments in Development</h2>
      <p>{data.summary}</p>

      <div className="cards">
        {data.therapies.map((t, i) => (
          <div className="card" key={i}>
            <div className="card-head">
              <strong>{t.name}</strong>
              <span className="badge">{t.phase}</span>
            </div>
            <div className="muted">
              {t.sponsor} · {t.mechanism}
            </div>
            <p>{t.potential_impact}</p>
            <div className="trial-links">
              {t.nct_ids.map((id) => (
                <ExtLink key={id} href={`https://clinicaltrials.gov/study/${id}`}>
                  {id}
                </ExtLink>
              ))}
            </div>
          </div>
        ))}
      </div>

      <h3>Key trends</h3>
      <List items={data.key_trends} />
      <AgentJson data={data} />
    </section>
  )
}

function OrgTable({ orgs }) {
  if (!orgs.length) return <p className="muted">None listed.</p>
  return (
    <table>
      <thead>
        <tr>
          <th>Organization</th>
          <th>Focus</th>
          <th>Active trials</th>
          <th>Notable programs</th>
        </tr>
      </thead>
      <tbody>
        {orgs.map((o, i) => (
          <tr key={i}>
            <td>
              <strong>{o.name}</strong>
              <div className="muted small">{o.category}</div>
            </td>
            <td>{o.focus}</td>
            <td className="center">{o.active_trial_count ?? '—'}</td>
            <td>{o.notable_programs.join(', ') || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function CompaniesInstitutions({ data }) {
  return (
    <section className="section">
      <h2>Key Companies &amp; Institutions</h2>
      <p>{data.summary}</p>
      <h3>Companies</h3>
      <OrgTable orgs={data.companies} />
      <h3>Institutions</h3>
      <OrgTable orgs={data.institutions} />
      <h3>Strategic notes</h3>
      <List items={data.strategic_notes} />
      <AgentJson data={data} />
    </section>
  )
}

// The same article can be retrieved by more than one agent; show it once with every section that used it.
function consolidate(sources) {
  const byKey = new Map()
  for (const s of sources) {
    const key = `${s.type}:${s.id}`
    if (!byKey.has(key)) byKey.set(key, { ...s, agents: [] })
    byKey.get(key).agents.push(s.agent)
  }
  return [...byKey.values()]
}

function SourceDetail({ source: s }) {
  if (s.type === 'pubmed') {
    return (
      <>
        <ExtLink href={s.url}>PMID {s.id}</ExtLink> — {s.title}{' '}
        <span className="muted">
          · {[s.meta.journal, s.meta.year].filter(Boolean).join(', ')}
        </span>
      </>
    )
  }
  if (s.type === 'trial') {
    return (
      <>
        <ExtLink href={s.url}>{s.id}</ExtLink> — {s.title}{' '}
        <span className="muted">
          · {s.meta.phase}, {s.meta.status}, {s.meta.sponsor}
        </span>
      </>
    )
  }
  return (
    <>
      <strong>{s.id}</strong> <span className="muted">({s.meta.category})</span> —{' '}
      <ExtLink href={s.url}>{s.meta.trial_count} trials</ExtLink>{' '}
      <span className="muted">
        · lead sponsor on {s.meta.lead_count}, collaborator on {s.meta.collaborator_count}
      </span>
    </>
  )
}

function Sources({ sources, condition }) {
  const all = consolidate(sources)
  return (
    <section className="section">
      <h2>Sources</h2>
      <p className="muted">
        Every record the agents retrieved from public APIs. Tags show which section used each source.
      </p>
      {SOURCE_GROUPS.map(({ type, title, describe }) => {
        const group = all.filter((s) => s.type === type)
        if (!group.length) return null
        return (
          <div key={type}>
            <h3>
              {title} ({group.length})
            </h3>
            <p className="muted small">{describe(condition, group)}</p>
            <ul className="source-list">
              {group.map((s) => (
                <li key={s.id}>
                  <SourceDetail source={s} />
                  {s.agents.map((a) => (
                    <span key={a} className="tag">
                      {SECTION_LABELS[a]}
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </section>
  )
}

export default function Briefing({ briefing }) {
  return (
    <div className="briefing">
      <p className="meta">
        Briefing for <strong>{briefing.condition}</strong> · generated{' '}
        {new Date(briefing.generated_at).toLocaleString()} in {briefing.duration_seconds}s · {briefing.model}
      </p>
      <ConditionOverview data={briefing.condition_overview} />
      <StandardOfCare data={briefing.standard_of_care} />
      <EmergingTreatments data={briefing.emerging_treatments} />
      <CompaniesInstitutions data={briefing.companies_institutions} />
      <Sources sources={briefing.sources} condition={briefing.condition} />
      <p className="disclaimer">
        AI-generated briefing for strategy discussion only. Not medical advice; verify against the linked primary
        sources.
      </p>
    </div>
  )
}
