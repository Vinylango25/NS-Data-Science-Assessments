/**
 * Scorecard.jsx
 * ─────────────
 * Single flat table: Category | Check (code + name + result) | Why we check this
 * All 14 checks fully defined, live counts from flags.json + dashboard.json.
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckCircle2, XCircle, AlertTriangle, Info } from 'lucide-react'
import { getDashboard, getFlags } from '../api/client'
import { Loading, ErrorBox, PageWrapper, SeverityBadge } from '../components/ui'

// ── All 14 checks ─────────────────────────────────────────────────────────
const ALL_CHECKS = [
  // ── Survey ───────────────────────────────────────────────────────────────
  {
    id: 'S1',
    category: 'Survey',
    flag_type: 'survey_rejected',
    label: 'Survey rejected by reviewer',
    severity: 'HIGH',
    sop: 'ODK §Review',
    why: `ODK Central allows a designated reviewer to accept or reject each submission. A rejected survey means the review team identified a fundamental problem — wrong plot, completely illegible data, or submitted in error. It must not be included in any analysis. If a rejection is overturned after investigation, the survey must be re-submitted and approved before it re-enters the dataset.`,
  },
  {
    id: 'S2',
    category: 'Survey',
    flag_type: 'duplicate_survey',
    label: 'Duplicate survey for same plot',
    severity: 'HIGH',
    sop: 'Protocol §4',
    why: `Each plot should have exactly one approved survey per monitoring window. If two approved surveys exist for the same plot, any species richness or occupancy model that treats surveys as independent samples will double-count that plot. This typically happens when a recorder re-submits after a connectivity issue and the original submission also synced. One of the two must be rejected before analysis proceeds.`,
  },
  {
    id: 'S3',
    category: 'Survey',
    flag_type: 'survey_duration_outlier',
    label: 'Survey duration outlier (>180 min)',
    severity: 'MEDIUM',
    sop: 'SOP §5.13',
    why: `A complete 20-quadrat survey should take between 45 minutes and 3 hours depending on vegetation density. A recorded duration above 180 minutes almost always means the ODK timer was left running after the field team finished — the GPS and timestamps in the form will then reflect hours of idle time rather than active survey time. This does not invalidate the species data but the timestamp-derived metrics (duration, start/end time) cannot be trusted. Duration below 10 minutes indicates the form was submitted without the survey being completed.`,
  },
  {
    id: 'S4',
    category: 'Survey',
    flag_type: 'unregistered_plot',
    label: 'Survey references unregistered plot UUID',
    severity: 'HIGH',
    sop: 'SOP §5.4',
    why: `Every ODK survey form is pre-loaded with a plot UUID pulled from the vegplots entity list. If that UUID does not match any plot in the registry, it means either the entity list was not updated before the field team's departure or the recorder manually edited the plot identifier. There is no way to geolocate, deduplicate, or validate a survey without a confirmed plot match. The survey cannot be included in spatial analysis until the UUID is resolved.`,
  },

  // ── Plot ─────────────────────────────────────────────────────────────────
  {
    id: 'P1',
    category: 'Plot',
    flag_type: 'viable_plot_not_surveyed',
    label: 'Viable plot not surveyed',
    severity: 'MEDIUM',
    sop: 'SOP §5.1',
    why: `A plot marked viable in the registry was accessible and intended for the monitoring window but has no approved survey. This is a sampling gap — the plot contributes a structural zero to any occupancy or presence-absence model, but it is unclear whether that zero reflects genuine absence or missed effort. The project manager needs to determine whether the plot was skipped intentionally (e.g. dangerous conditions) or by oversight before the dataset is closed for analysis.`,
  },
  {
    id: 'P2',
    category: 'Plot',
    flag_type: 'non_viable_plot_surveyed',
    label: 'Non-viable plot surveyed',
    severity: 'MEDIUM',
    sop: 'SOP §5.3',
    why: `Plots are marked non-viable when they have been destroyed, permanently flooded, converted to cropland, or are otherwise unable to represent the target habitat. If a non-viable plot is included in richness or diversity estimates it inflates or deflates summary statistics depending on the nature of the habitat change. The survey data should be archived but excluded from all analysis outputs until the project ecologist confirms the plot's status.`,
  },
  {
    id: 'P3',
    category: 'Plot',
    flag_type: ['transect_too_short', 'transect_too_long', 'transect_length_missing'],
    label: 'Transect length outside 40–60 m',
    severity: 'MEDIUM',
    sop: 'SOP §3.1',
    why: `The SOP specifies a 50 m transect with a ±20% tolerance (40–60 m). The 20 quadrats are positioned at fixed intervals along this transect, so a shorter transect compresses the sampling points and a longer one stretches them beyond the intended plot boundary. Both distort the spatial representativeness of the quadrat sample. A missing transect length (endpoints identical or absent) means the haversine distance cannot be computed at all, which also prevents the midpoint offset check (P4) from running.`,
  },
  {
    id: 'P4',
    category: 'Plot',
    flag_type: 'midpoint_displaced',
    label: 'Midpoint >25 m from registered centroid',
    severity: 'MEDIUM',
    sop: 'SOP §5.5',
    why: `The plot centroid in the vegplots entity is the permanent spatial anchor for that monitoring location — it is what allows the same ground to be resurveyed in future years. If the recorded midpoint of the transect is more than 25 m from the centroid, the transect was likely laid on a different part of the landscape than intended. For long-term monitoring this creates pseudoreplication: successive surveys will sample different vegetation patches while appearing to track the same plot.`,
  },

  // ── Quadrat ───────────────────────────────────────────────────────────────
  {
    id: 'Q1',
    category: 'Quadrat',
    flag_type: 'quadrat_gps_accuracy',
    label: 'Quadrat GPS accuracy >5 m',
    severity: 'LOW',
    sop: 'SOP §4.2',
    why: `Consumer GPS under open savanna canopy typically achieves 3–5 m accuracy. Above 5 m the recorded coordinate may not reliably locate the quadrat for a revisit — a 5 m error in any direction can place the nominal position outside the actual quadrat boundaries. This is flagged as LOW because the species data recorded in the quadrat is still valid; the spatial coordinate is the only affected field. It becomes HIGH-priority only if the project intends sub-metre relocation for repeat visits.`,
  },
  {
    id: 'Q2',
    category: 'Quadrat',
    flag_type: 'herbs_present_no_species',
    label: 'herbs_present = Yes but no species recorded',
    severity: 'MEDIUM',
    sop: 'SOP §5.6–5.7',
    why: `The recorder explicitly marked that herbs are present in the quadrat but recorded zero species names. This is almost certainly a data-entry omission — the recorder tapped "Yes" and then navigated past the species list without entering any names. Including this quadrat as "herbs present" in herb-cover estimates while leaving the species list empty will suppress the true species count and inflate the proportion of quadrats with unidentified herb presence. The recorder should be contacted to supply the missing species or the quadrat should be recoded as herbs_absent.`,
  },
  {
    id: 'Q3',
    category: 'Quadrat',
    flag_type: 'no_herbs_but_species',
    label: 'herbs_present = No but species names listed',
    severity: 'MEDIUM',
    sop: 'SOP §5.6',
    why: `The recorder marked no herbs present but the form contains species names for that quadrat. This is an internal contradiction — either the herbs_present field is wrong (recorder tapped No accidentally) or the species names belong to a different quadrat. Either way the herb-cover calculation and the species count are inconsistent. If used as-is, the quadrat contributes to species richness counts while also appearing to have zero herb cover, which will produce nonsensical cover-to-richness ratios.`,
  },
  {
    id: 'Q4',
    category: 'Quadrat',
    flag_type: 'canonical_trailing_whitespace',
    label: 'Trailing whitespace in canonical species name',
    severity: 'LOW',
    sop: 'SOP §5.7',
    why: `The canonical species name has a leading or trailing space (e.g. "Evolvulus alsinoides " with a trailing space). String equality comparisons are case- and whitespace-sensitive: "Evolvulus alsinoides" and "Evolvulus alsinoides " are treated as different strings by every database join and GBIF API lookup. A name with a trailing space will fail to match its entry in the master species list, producing a false negative in any presence-absence matrix. The fix is trivial (str.strip()) but must be applied before any join operation.`,
  },
  {
    id: 'Q5',
    category: 'Quadrat',
    flag_type: 'non_standard_canonical',
    label: 'Name not in Genus_species format',
    severity: 'LOW',
    sop: 'SOP §5.7',
    why: `The SOP requires canonical names in Genus_species underscore format (e.g. "Evolvulus_alsinoides") to ensure unambiguous two-part identification. Names entered as "Evolvulus alsinoides" (space-separated), "evolvulus alsinoides" (lowercase genus), or single-word entries will not match GBIF's taxonomic backbone or the master species list without manual intervention. The format also makes it immediately obvious when a record contains only a genus name or a vernacular name, both of which are valid reasons for further review.`,
  },

  // ── Species ───────────────────────────────────────────────────────────────
  {
    id: 'R1',
    category: 'Species',
    flag_type: 'species_pending_review',
    label: 'Additional species pending taxonomic review',
    severity: 'MEDIUM',
    sop: 'SOP §6',
    why: `Recorders may encounter plants that are not on the pre-loaded species list. These are captured as "additional species" with a provisional identifier (UUID) and reason code: new_unknown (plant not recognised by the recorder) or new_missing (plant recognised but absent from the master list). Until a botanist reviews and confirms each entry, the species name attached to these records is not trusted for any richness or diversity analysis. The 107 pending entries in this dataset are a normal feature of baseline surveys in species-rich savanna — they signal a backlog of identification work, not a data collection failure.`,
  },
]

// ── Category colours ──────────────────────────────────────────────────────
const CAT_STYLE = {
  Survey:  { dot: 'bg-emerald-500', text: 'text-emerald-400', bg: 'bg-emerald-900/20' },
  Plot:    { dot: 'bg-sky-500',     text: 'text-sky-400',     bg: 'bg-sky-900/20'     },
  Quadrat: { dot: 'bg-violet-500',  text: 'text-violet-400',  bg: 'bg-violet-900/20'  },
  Species: { dot: 'bg-amber-500',   text: 'text-amber-400',   bg: 'bg-amber-900/20'   },
}

function flagMatchesCheck(flag, check) {
  if (Array.isArray(check.flag_type)) return check.flag_type.includes(flag.flag_type)
  return flag.flag_type === check.flag_type || flag.flag_id === check.id
}

export default function Scorecard() {
  const { data: dashboard, isLoading: loadD, error: errD } = useQuery({
    queryKey: ['dashboard'],
    queryFn:  getDashboard,
  })
  const { data: flagsResp, isLoading: loadF } = useQuery({
    queryKey: ['flags-all'],
    queryFn:  () => getFlags({ page: 1, page_size: 9999 }),
  })

  const isLoading = loadD || loadF

  const allFlags = useMemo(() => {
    if (!flagsResp) return []
    return Array.isArray(flagsResp) ? flagsResp : (flagsResp.results || [])
  }, [flagsResp])

  const enriched = useMemo(() =>
    ALL_CHECKS.map(check => {
      const matches = allFlags.filter(f => flagMatchesCheck(f, check))
      return { ...check, count: matches.length, examples: matches.slice(0, 2) }
    }),
    [allFlags]
  )

  const passing  = enriched.filter(c => c.count === 0).length
  const total    = enriched.length
  const passRate = Math.round((passing / total) * 100)

  if (isLoading) return <Loading text="Loading scorecard…" />
  if (errD)      return <ErrorBox message={errD.message} />

  const d = dashboard || {}

  return (
    <PageWrapper
      title="QC Scorecard"
      subtitle={`${total} checks · ${d.n_surveys_total ?? '—'} surveys · ${d.n_quadrats ?? '—'} quadrats`}
    >

      {/* ── Summary strip ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">

        <div className="card-p col-span-2 sm:col-span-1">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Pass rate</p>
          <div className="flex items-end gap-2 mb-3">
            <span className={`text-4xl font-bold tracking-tight ${passRate >= 90 ? 'text-emerald-400' : passRate >= 70 ? 'text-amber-400' : 'text-red-400'}`}>
              {passRate}%
            </span>
            <span className="text-sm text-gray-500 mb-1">{passing}/{total}</span>
          </div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${passRate >= 90 ? 'bg-emerald-500' : 'bg-amber-500'}`}
                 style={{ width: `${passRate}%` }} />
          </div>
        </div>

        <div className="card-p">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">HIGH flags</p>
          <p className={`text-3xl font-bold ${d.n_flags_high > 0 ? 'text-red-400' : 'text-emerald-400'}`}>{d.n_flags_high ?? '—'}</p>
          <p className="text-xs text-gray-500 mt-1.5">{d.n_flags_high > 0 ? 'Resolve before analysis' : 'All clear'}</p>
        </div>

        <div className="card-p">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">MEDIUM flags</p>
          <p className={`text-3xl font-bold ${d.n_flags_medium > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>{d.n_flags_medium ?? '—'}</p>
          <p className="text-xs text-gray-500 mt-1.5">Investigate before final analysis</p>
        </div>

        <div className="card-p">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">LOW flags</p>
          <p className={`text-3xl font-bold ${d.n_flags_low > 0 ? 'text-blue-400' : 'text-emerald-400'}`}>{d.n_flags_low ?? '—'}</p>
          <p className="text-xs text-gray-500 mt-1.5">Advisory — fix before name matching</p>
        </div>
      </div>

      {/* ── Main table ─────────────────────────────────────────────────────── */}
      <div className="card-p p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-900/80 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-28">Category</th>
                <th className="px-4 py-3.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-72">Check</th>
                <th className="px-4 py-3.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Why we check this</th>
                <th className="px-4 py-3.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-24">Result</th>
              </tr>
            </thead>
            <tbody>
              {enriched.map((check, idx) => {
                const cs      = CAT_STYLE[check.category] || CAT_STYLE.Survey
                const passing = check.count === 0
                const icon    = passing
                  ? <CheckCircle2 size={15} className="text-emerald-500 shrink-0 mt-0.5" />
                  : check.severity === 'HIGH'
                    ? <XCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
                    : <AlertTriangle size={15} className={`shrink-0 mt-0.5 ${check.severity === 'MEDIUM' ? 'text-amber-400' : 'text-blue-400'}`} />

                // show category label only on first row of that category
                const prevCat = idx > 0 ? enriched[idx - 1].category : null
                const showCat = check.category !== prevCat

                return (
                  <tr key={check.id}
                      className={`border-t border-gray-800/60 hover:bg-gray-800/20 transition-colors align-top`}>

                    {/* Category */}
                    <td className="px-5 py-4">
                      {showCat && (
                        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-md ${cs.bg} ${cs.text}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${cs.dot}`} />
                          {check.category}
                        </span>
                      )}
                    </td>

                    {/* Check name + code + severity + SOP */}
                    <td className="px-4 py-4">
                      <div className="flex items-start gap-2">
                        {icon}
                        <div>
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <span className="font-mono text-[11px] font-bold text-gray-500">{check.id}</span>
                            <span className="text-sm font-medium text-gray-200">{check.label}</span>
                          </div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <SeverityBadge severity={check.severity} />
                            <span className="text-[11px] font-mono text-gray-600">{check.sop}</span>
                          </div>
                          {/* Inline examples */}
                          {check.examples.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {check.examples.map((f, i) => (
                                <div key={i} className="text-[11px] text-gray-500 bg-gray-800/50 rounded px-2 py-1 leading-relaxed">
                                  {f.description || f.flag_type}
                                  {f.field_value && <span className="ml-1 font-mono text-gray-600">· {String(f.field_value).slice(0, 40)}</span>}
                                </div>
                              ))}
                              {check.count > 2 && (
                                <p className="text-[11px] text-gray-600">+{check.count - 2} more</p>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Why we check this */}
                    <td className="px-4 py-4">
                      <p className="text-xs text-gray-400 leading-relaxed">{check.why}</p>
                    </td>

                    {/* Result */}
                    <td className="px-4 py-4 text-right">
                      {passing
                        ? <span className="text-xs text-emerald-600 font-medium whitespace-nowrap">✓ Pass</span>
                        : <span className={`text-sm font-bold whitespace-nowrap ${
                            check.severity === 'HIGH' ? 'text-red-400' :
                            check.severity === 'MEDIUM' ? 'text-amber-400' : 'text-blue-400'
                          }`}>{check.count}</span>
                      }
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Footer note */}
        <div className="px-5 py-3.5 border-t border-gray-800 flex items-center gap-2 text-xs text-gray-600">
          <Info size={12} className="shrink-0" />
          <span>
            Counts reflect the most recent QC run.{' '}
            <Link to="/run-qc" className="text-emerald-700 hover:text-emerald-500 underline underline-offset-2">
              Re-run
            </Link>{' '}
            to refresh. HIGH flags must be resolved before analysis. LOW flags are advisory.
          </span>
        </div>
      </div>
    </PageWrapper>
  )
}
