/**
 * src/api/client.js
 * -----------------
 * Static demo mode — reads pre-generated JSON from /public/data/.
 * No backend required. Deploys fully on Vercel.
 *
 * To switch to a live backend, set VITE_API_URL and set VITE_STATIC=false.
 */

const STATIC = import.meta.env.VITE_STATIC !== 'false'
const BASE   = import.meta.env.VITE_API_URL || ''

// ── Static loader ─────────────────────────────────────────────────────────────
async function loadJson(name) {
  const res = await fetch(`/data/${name}.json`)
  if (!res.ok) throw new Error(`Failed to load ${name}.json`)
  return res.json()
}

// Cache so we only fetch once per session
const _cache = {}
async function cached(name) {
  if (!_cache[name]) _cache[name] = loadJson(name)
  return _cache[name]
}

// ── Dashboard ──────────────────────────────────────────────────────────────────
export async function getDashboard() {
  if (STATIC) return cached('dashboard')
  const r = await fetch(`${BASE}/api/v1/veg/dashboard`)
  return r.json()
}

// ── Runs (static: return a single synthetic completed run) ────────────────────
export async function getRuns() {
  if (STATIC) {
    const d = await cached('dashboard')
    return [{ id: 1, run_at: d.run_at, data_source: 'csv', status: 'complete',
              n_surveys: d.n_surveys_total, n_plots: d.n_plots_registered,
              n_quadrats: d.n_quadrats, n_flags_high: d.n_flags_high,
              n_flags_medium: d.n_flags_medium, n_flags_low: d.n_flags_low,
              n_pending_species: d.n_pending_species, completed_at: d.run_at }]
  }
  const r = await fetch(`${BASE}/api/v1/veg/runs`)
  return r.json()
}

export async function getRun(id) {
  if (STATIC) { const runs = await getRuns(); return runs[0] }
  const r = await fetch(`${BASE}/api/v1/veg/runs/${id}`)
  return r.json()
}

export async function triggerRun(source) {
  if (STATIC) {
    // Simulate a trigger in static mode
    await new Promise(r => setTimeout(r, 800))
    return { run_id: 1, status: 'complete', message: 'Demo mode — data is pre-loaded.' }
  }
  const r = await fetch(`${BASE}/api/v1/veg/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data_source: source }),
  })
  return r.json()
}

// ── Surveys ────────────────────────────────────────────────────────────────────
export async function getSurveys(params = {}) {
  if (STATIC) {
    let data = await cached('surveys')
    if (params.qc_status)    data = data.filter(s => s.qc_status === params.qc_status)
    if (params.recorder)     data = data.filter(s => s.recorder?.toLowerCase().includes(params.recorder.toLowerCase()))
    if (params.review_state) {
      if (params.review_state === 'approved') data = data.filter(s => s.review_state !== 'rejected')
      else data = data.filter(s => s.review_state === params.review_state)
    }
    return data
  }
  const qs = new URLSearchParams(params).toString()
  const r  = await fetch(`${BASE}/api/v1/veg/surveys${qs ? '?'+qs : ''}`)
  return r.json()
}

export async function getSurvey(key) {
  if (STATIC) {
    const surveys = await cached('surveys')
    const survey  = surveys.find(s => s.odk_key === key)
    if (!survey) throw new Error('Survey not found')
    const flags   = survey.flags || []
    const narrative = survey.narrative || null
    return { survey, flags, narrative }
  }
  const r = await fetch(`${BASE}/api/v1/veg/surveys/${encodeURIComponent(key)}`)
  return r.json()
}

// ── Plots ──────────────────────────────────────────────────────────────────────
export async function getPlots(params = {}) {
  if (STATIC) {
    let data = await cached('plots')
    if (params.qc_status !== undefined && params.qc_status !== '')
      data = data.filter(p => p.qc_status === params.qc_status)
    if (params.surveyed !== undefined)
      data = data.filter(p => p.was_surveyed === params.surveyed)
    return data
  }
  const qs = new URLSearchParams(params).toString()
  const r  = await fetch(`${BASE}/api/v1/veg/plots${qs ? '?'+qs : ''}`)
  return r.json()
}

export async function getPlot(name) {
  if (STATIC) {
    const plots = await cached('plots')
    const plot  = plots.find(p => p.plot_name === name)
    if (!plot) throw new Error('Plot not found')
    return { plot, flags: plot.flags || [], surveys: plot.surveys || [] }
  }
  const r = await fetch(`${BASE}/api/v1/veg/plots/${encodeURIComponent(name)}`)
  return r.json()
}

// ── Flags ──────────────────────────────────────────────────────────────────────
export async function getFlags(params = {}) {
  if (STATIC) {
    let data = await cached('flags')
    if (params.severity)  data = data.filter(f => f.severity === params.severity.toUpperCase())
    if (params.flag_type) data = data.filter(f => f.flag_type === params.flag_type)
    if (params.plot_name) data = data.filter(f => f.plot_name?.toLowerCase().includes(params.plot_name.toLowerCase()))
    const page      = params.page || 1
    const page_size = params.page_size || 50
    const total     = data.length
    const results   = data.slice((page-1)*page_size, page*page_size).map((f,i) => ({ id: i+1, ...f }))
    return { total, page, page_size, results }
  }
  const qs = new URLSearchParams(params).toString()
  const r  = await fetch(`${BASE}/api/v1/veg/flags${qs ? '?'+qs : ''}`)
  return r.json()
}

// ── Species queue ──────────────────────────────────────────────────────────────
export async function getSpeciesQueue(params = {}) {
  if (STATIC) {
    let data = await cached('species_queue')
    if (params.plot_name) data = data.filter(s => s.plot_name?.toLowerCase().includes(params.plot_name.toLowerCase()))
    if (params.recorder)  data = data.filter(s => s.recorder?.toLowerCase().includes(params.recorder.toLowerCase()))
    return data.map((s,i) => ({ id: i+1, ...s }))
  }
  const qs = new URLSearchParams(params).toString()
  const r  = await fetch(`${BASE}/api/v1/veg/species-queue${qs ? '?'+qs : ''}`)
  return r.json()
}

// ── Narrative ──────────────────────────────────────────────────────────────────
export async function getNarrative(key) {
  if (STATIC) {
    const surveys = await cached('surveys')
    const survey  = surveys.find(s => s.odk_key === key)
    if (survey?.narrative) return survey.narrative
    throw new Error('No narrative')
  }
  const r = await fetch(`${BASE}/api/v1/veg/narrative/${encodeURIComponent(key)}`)
  return r.json()
}

export async function regenerateNarrative(key) {
  if (STATIC) {
    // Static fallback — generate rule-based narrative client-side
    const surveys = await cached('surveys')
    const s = surveys.find(sv => sv.odk_key === key)
    if (!s) return { narrative: 'Survey not found.' }
    const flags  = s.flags || []
    const high   = flags.filter(f => f.severity === 'HIGH')
    const medium = flags.filter(f => f.severity === 'MEDIUM')
    const plot   = s.plot_name?.replace('SavMon_LW_','') || 'this plot'
    let text = `Survey of ${plot} by ${s.recorder || 'the field team'} completed ${s.quadrats_completed ?? 20}/20 quadrats with ${s.species_occurrences ?? 0} species occurrences.`
    if (!flags.length) {
      text += ' This survey passed all QC checks with no issues identified.'
    } else if (high.length) {
      text += ` ${high.length} HIGH-severity issue(s) require immediate attention: ${high[0].description}`
    } else if (medium.length) {
      text += ` ${medium.length} MEDIUM-severity flag(s) warrant investigation before analysis.`
    }
    return { survey_key: key, plot_name: s.plot_name, narrative: text, model: 'rule-based', generated_at: new Date().toISOString() }
  }
  const r = await fetch(`${BASE}/api/v1/veg/narrative/${encodeURIComponent(key)}`, { method: 'POST' })
  return r.json()
}
