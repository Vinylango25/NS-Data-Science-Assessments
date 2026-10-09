/**
 * Report.jsx — Polished assessment report, dynamically generated from live data
 */

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts'
import { CheckCircle2, AlertTriangle, XCircle, ChevronRight, ExternalLink, ArrowUpRight } from 'lucide-react'
import { getDashboard, getSurveys, getPlots, getFlags } from '../api/client'
import { Loading, ErrorBox, PageWrapper } from '../components/ui'

const SEV_COLOR  = { HIGH: '#f87171', MEDIUM: '#fb923c', LOW: '#60a5fa' }
const SEV_BG     = { HIGH: 'bg-red-900/20 border-red-800/40 text-red-300', MEDIUM: 'bg-amber-900/20 border-amber-800/40 text-amber-300', LOW: 'bg-blue-900/20 border-blue-800/40 text-blue-300' }

// ── small reusable pieces ────────────────────────────────────────────────────
function KV({ label, value, accent }) {
  return (
    <div>
      <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-lg font-bold ${accent || 'text-gray-100'}`}>{value ?? '—'}</p>
    </div>
  )
}

function Divider() {
  return <div className="border-t border-gray-800 my-6" />
}

function SectionLabel({ letter, title }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="w-7 h-7 rounded-lg bg-emerald-900/40 ring-1 ring-emerald-800/50 flex items-center justify-center shrink-0">
        <span className="text-[11px] font-bold text-emerald-400">{letter}</span>
      </div>
      <h2 className="text-sm font-semibold text-gray-100 tracking-wide">{title}</h2>
    </div>
  )
}

function FlagPill({ severity, count }) {
  const styles = {
    HIGH:   'bg-red-900/40 text-red-300 ring-red-800/50',
    MEDIUM: 'bg-amber-900/40 text-amber-300 ring-amber-800/50',
    LOW:    'bg-blue-900/40 text-blue-300 ring-blue-800/50',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ring-1 ${styles[severity]}`}>
      <span className="font-mono">{count}</span> {severity}
    </span>
  )
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="font-medium text-gray-200 mb-0.5">{label}</p>
      <p style={{ color: payload[0]?.fill }}>{payload[0]?.value} flags</p>
    </div>
  )
}

// ── main component ─────────────────────────────────────────────────────────
export default function Report() {
  const { data: d,         isLoading: ldD, error: errD } = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard })
  const { data: surveys = [], isLoading: ldS }           = useQuery({ queryKey: ['surveys'],   queryFn: () => getSurveys({}) })
  const { data: plots = [],   isLoading: ldP }           = useQuery({ queryKey: ['plots'],     queryFn: () => getPlots({}) })
  const { data: flagsResp,    isLoading: ldF }           = useQuery({ queryKey: ['flags-all'], queryFn: () => getFlags({ page: 1, page_size: 9999 }) })

  const flags = useMemo(() => {
    if (!flagsResp) return []
    return Array.isArray(flagsResp) ? flagsResp : (flagsResp.results || [])
  }, [flagsResp])

  const an = useMemo(() => {
    if (!surveys.length || !plots.length) return null

    const durations = surveys.map(s => s.duration_min).filter(Boolean)
    const rejected  = surveys.filter(s => s.review_state === 'rejected')
    const outliers  = surveys.filter(s => s.duration_min > 180)

    const sortedPlots = [...plots].sort((a, b) => (b.total_species_occurrences || 0) - (a.total_species_occurrences || 0))
    const top5        = sortedPlots.slice(0, 5)
    const maxSpp      = top5[0]?.total_species_occurrences || 1

    const shortT = plots.filter(p => p.transect_length_m && p.transect_length_m < 40)
    const longT  = plots.filter(p => p.transect_length_m && p.transect_length_m > 60)
    const tlArr  = plots.map(p => p.transect_length_m).filter(Boolean)

    const flagByType = {}
    for (const f of flags) {
      if (!flagByType[f.flag_type]) flagByType[f.flag_type] = { n: 0, sev: f.severity }
      flagByType[f.flag_type].n++
    }
    const chartData = Object.entries(flagByType)
      .map(([t, v]) => ({ name: t.replace(/_/g, ' '), count: v.n, sev: v.sev }))
      .sort((a, b) => b.count - a.count)

    const pieData = [
      { name: 'HIGH',   value: d?.n_flags_high   || 0, fill: SEV_COLOR.HIGH   },
      { name: 'MEDIUM', value: d?.n_flags_medium  || 0, fill: SEV_COLOR.MEDIUM },
      { name: 'LOW',    value: d?.n_flags_low     || 0, fill: SEV_COLOR.LOW    },
    ].filter(x => x.value > 0)

    return {
      durations, rejected, outliers, top5, maxSpp, shortT, longT, tlArr, chartData, pieData,
      avgDur:     durations.reduce((a, b) => a + b, 0) / durations.length,
      avgTransect: tlArr.reduce((a, b) => a + b, 0) / tlArr.length,
      recorders:  [...new Set(surveys.map(s => s.recorder).filter(Boolean))],
    }
  }, [surveys, plots, flags, d])

  if (ldD || ldS || ldP || ldF) return <Loading text="Generating report…" />
  if (errD)   return <ErrorBox message={errD.message} />
  if (!an)    return <Loading text="Computing analytics…" />

  return (
    <PageWrapper
      title="Assessment Report"
      subtitle="SAVMON Baseline 2026 · Lewa Wildlife Conservancy"
    >
      {/* ── Hero banner ─────────────────────────────────────────────────── */}
      <div className="card-p mb-5">
        <div className="flex flex-wrap gap-x-10 gap-y-4 mb-5">
          <KV label="Plots surveyed"    value={`${d.n_plots_surveyed} / ${d.n_plots_viable}`} accent="text-emerald-400" />
          <KV label="Surveys"           value={`${d.n_surveys_approved} approved`} accent="text-gray-100" />
          <KV label="Quadrats"          value={d.n_quadrats} />
          <KV label="Herb coverage"     value={`${d.pct_quadrats_with_herbs}%`} accent="text-emerald-400" />
          <KV label="Pending species"   value={d.n_pending_species} accent={d.n_pending_species > 0 ? 'text-amber-400' : 'text-emerald-400'} />
          <KV label="Recorders"         value={an.recorders.join(' · ')} />
        </div>

        <div className="flex flex-wrap gap-2">
          <FlagPill severity="HIGH"   count={d.n_flags_high}   />
          <FlagPill severity="MEDIUM" count={d.n_flags_medium} />
          <FlagPill severity="LOW"    count={d.n_flags_low}    />
          <span className="text-xs text-gray-600 self-center ml-1">{flags.length} total QC flags</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-5">

        {/* ── LEFT COLUMN: Sections A, B, C ──────────────────────────────── */}
        <div className="lg:col-span-2 space-y-5">

          {/* Section A — Survey summary */}
          <div className="card-p">
            <SectionLabel letter="A" title="Survey-level summary" />

            <div className="grid grid-cols-3 gap-4 mb-5">
              <KV label="Total submitted" value={d.n_surveys_total} />
              <KV label="Approved"        value={d.n_surveys_approved} accent="text-emerald-400" />
              <KV label="Rejected"        value={d.n_surveys_rejected} accent={d.n_surveys_rejected > 0 ? 'text-red-400' : 'text-emerald-400'} />
            </div>

            <div className="grid grid-cols-2 gap-4 mb-5">
              <KV label="Avg duration"   value={`${an.avgDur.toFixed(0)} min`} />
              <KV label="Duration range" value={`${Math.min(...an.durations).toFixed(0)} – ${Math.max(...an.durations).toFixed(0)} min`} />
            </div>

            {an.rejected.length > 0 && (
              <div className={`border rounded-lg px-4 py-3 text-xs mb-3 ${SEV_BG.HIGH}`}>
                <p className="font-semibold mb-1.5 flex items-center gap-1.5">
                  <XCircle size={12} /> {an.rejected.length} rejected — must be resolved before analysis
                </p>
                {an.rejected.map(s => (
                  <p key={s.odk_key} className="text-red-300/70">
                    {s.plot_name?.replace('SavMon_LW_', '')} · {s.recorder} · {s.submission_date}
                  </p>
                ))}
              </div>
            )}

            {an.outliers.length > 0 && (
              <div className={`border rounded-lg px-4 py-3 text-xs ${SEV_BG.MEDIUM}`}>
                <p className="font-semibold mb-1 flex items-center gap-1.5">
                  <AlertTriangle size={12} /> Duration outlier — timer likely left running
                </p>
                {an.outliers.map(s => (
                  <p key={s.odk_key} className="text-amber-300/70">
                    {s.plot_name?.replace('SavMon_LW_', '')} · {s.duration_min?.toFixed(0)} min · {s.recorder}
                  </p>
                ))}
              </div>
            )}
          </div>

          {/* Section B — Plot summary */}
          <div className="card-p">
            <SectionLabel letter="B" title="Plot-level summary" />

            <div className="grid grid-cols-3 gap-4 mb-5">
              <KV label="Registered" value={d.n_plots_registered} />
              <KV label="Viable"     value={d.n_plots_viable} />
              <KV label="Surveyed"   value={`${d.n_plots_surveyed} (100%)`} accent="text-emerald-400" />
            </div>

            <div className="grid grid-cols-2 gap-4 mb-5">
              <KV label="Avg transect" value={`${an.avgTransect.toFixed(1)} m`} />
              <KV label="Out of range" value={`${an.shortT.length + an.longT.length} plots`}
                  accent={(an.shortT.length + an.longT.length) > 0 ? 'text-amber-400' : 'text-emerald-400'} />
            </div>

            {/* Species richness bars */}
            <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-3">Top 5 plots by species richness</p>
            <div className="space-y-2">
              {an.top5.map(p => (
                <div key={p.plot_name} className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 w-14 shrink-0">{p.plot_name?.replace('SavMon_LW_', '')}</span>
                  <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                    <div className="h-full rounded-full bg-emerald-600"
                         style={{ width: `${Math.round(((p.total_species_occurrences || 0) / an.maxSpp) * 100)}%` }} />
                  </div>
                  <span className="text-xs font-semibold text-gray-300 w-8 text-right">{p.total_species_occurrences}</span>
                  {p.qc_status !== 'pass' && (
                    <span className="text-[10px] text-amber-500 bg-amber-900/30 px-1.5 py-0.5 rounded">{p.qc_status}</span>
                  )}
                </div>
              ))}
            </div>

            {(an.shortT.length > 0 || an.longT.length > 0) && (
              <div className={`border rounded-lg px-4 py-3 text-xs mt-4 ${SEV_BG.MEDIUM}`}>
                <p className="font-semibold mb-1.5">Transect anomalies (SOP §3.1: 40–60 m)</p>
                <div className="grid grid-cols-2 gap-x-6 gap-y-0.5">
                  {an.shortT.map(p => (
                    <p key={p.plot_name} className="text-amber-300/80">
                      {p.plot_name?.replace('SavMon_LW_', '')} — {p.transect_length_m?.toFixed(1)} m ↓
                    </p>
                  ))}
                  {an.longT.map(p => (
                    <p key={p.plot_name} className="text-amber-300/80">
                      {p.plot_name?.replace('SavMon_LW_', '')} — {p.transect_length_m?.toFixed(1)} m ↑
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Section C — Sampling effort */}
          <div className="card-p">
            <SectionLabel letter="C" title="Sampling effort" />

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
              <KV label="Total quadrats"  value={d.n_quadrats} />
              <KV label="With herbs"      value={`${d.pct_quadrats_with_herbs}%`} accent="text-emerald-400" />
              <KV label="Coverage"        value="100%"   accent="text-emerald-400" />
              <KV label="Pending species" value={d.n_pending_species} accent="text-amber-400" />
            </div>

            <div className={`border rounded-lg px-4 py-3 text-xs ${SEV_BG.MEDIUM}`}>
              <p className="font-semibold mb-1 flex items-center gap-1.5">
                <AlertTriangle size={12} /> {d.n_pending_species} species awaiting botanist confirmation
              </p>
              <p className="text-amber-300/70 mb-2">
                Richness counts are lower bounds until the queue is cleared.
              </p>
              <Link to="/species-queue" className="inline-flex items-center gap-1 text-amber-400 hover:text-amber-300 font-medium">
                Review species queue <ChevronRight size={11} />
              </Link>
            </div>
          </div>
        </div>

        {/* ── RIGHT COLUMN: Flag chart + D ───────────────────────────────── */}
        <div className="space-y-5">

          {/* Severity pie */}
          <div className="card-p">
            <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-4">Flag severity</p>
            <div className="flex items-center justify-center">
              <PieChart width={160} height={160}>
                <Pie data={an.pieData} cx={75} cy={75} innerRadius={45} outerRadius={72}
                     paddingAngle={3} dataKey="value">
                  {an.pieData.map((e, i) => <Cell key={i} fill={e.fill} opacity={0.85} />)}
                </Pie>
              </PieChart>
            </div>
            <div className="space-y-1.5 mt-2">
              {an.pieData.map(e => (
                <div key={e.name} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: e.fill }} />
                    <span className="text-gray-400">{e.name}</span>
                  </div>
                  <span className="font-semibold" style={{ color: e.fill }}>{e.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Section D — Flag chart */}
          <div className="card-p">
            <SectionLabel letter="D" title="Flag breakdown" />
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={an.chartData} layout="vertical"
                        margin={{ top: 0, right: 8, left: 120, bottom: 0 }}>
                <XAxis type="number" tick={{ fill: '#4b5563', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 10 }}
                       width={115} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[0, 3, 3, 0]} maxBarSize={12}>
                  {an.chartData.map((e, i) => <Cell key={i} fill={SEV_COLOR[e.sev]} opacity={0.8} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Section E — Actions */}
          <div className="card-p">
            <SectionLabel letter="E" title="Required actions" />
            <div className="space-y-3 text-xs">
              <div className="flex gap-2">
                <XCircle size={13} className="text-red-400 shrink-0 mt-0.5" />
                <p className="text-gray-400 leading-relaxed">
                  <span className="text-red-400 font-semibold">Immediate:</span> Resolve the 2 rejected surveys
                  and 2 duplicate submissions before any analysis.
                </p>
              </div>
              <div className="flex gap-2">
                <AlertTriangle size={13} className="text-amber-400 shrink-0 mt-0.5" />
                <p className="text-gray-400 leading-relaxed">
                  <span className="text-amber-400 font-semibold">Before analysis:</span> Botanist to confirm {d.n_pending_species} species.
                  Verify transect lengths for {an.shortT.length + an.longT.length} out-of-range plots.
                </p>
              </div>
              <div className="flex gap-2">
                <CheckCircle2 size={13} className="text-blue-400 shrink-0 mt-0.5" />
                <p className="text-gray-400 leading-relaxed">
                  <span className="text-blue-400 font-semibold">Before name-matching:</span> Clean {d.n_flags_low} LOW-severity
                  canonical name formatting issues.
                </p>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-800">
              <Link to="/scorecard"
                    className="flex items-center justify-between text-xs text-gray-500 hover:text-gray-300 transition-colors">
                <span>Full 14-check scorecard</span>
                <ArrowUpRight size={13} />
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <div className="card-p">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="text-xs text-gray-500">
            <p className="font-medium text-gray-400 mb-1">Dev Team integration</p>
            <p>Set <code className="bg-gray-800 px-1 rounded">VITE_STATIC=false</code> and <code className="bg-gray-800 px-1 rounded">VITE_API_URL</code> to connect to NS Analytics. No frontend changes needed.</p>
          </div>
          <a href="https://frontend-sandy-tau-56.vercel.app" target="_blank" rel="noopener noreferrer"
             className="flex items-center gap-1.5 text-xs text-emerald-500 hover:text-emerald-400 shrink-0">
            Live demo <ExternalLink size={11} />
          </a>
        </div>
      </div>

    </PageWrapper>
  )
}
