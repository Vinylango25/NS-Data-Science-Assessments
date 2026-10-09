import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts'
import { Link } from 'react-router-dom'
import { AlertTriangle, ChevronRight } from 'lucide-react'
import { getDashboard } from '../api/client'
import { Loading, ErrorBox, PageWrapper } from '../components/ui'

const SEV_COLOR = { HIGH: '#f87171', MEDIUM: '#fb923c', LOW: '#60a5fa' }

function KV({ label, value, accent, sub }) {
  return (
    <div>
      <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-2xl font-bold ${accent || 'text-gray-100'}`}>{value ?? '—'}</p>
      {sub && <p className="text-[11px] text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="font-medium text-gray-200 mb-0.5">{label}</p>
      <p style={{ color: payload[0]?.fill }}>{payload[0]?.value} flags</p>
    </div>
  )
}

export default function Dashboard() {
  const { data: d, isLoading, error } = useQuery({
    queryKey:        ['dashboard'],
    queryFn:         getDashboard,
    refetchInterval: 30_000,
  })

  if (isLoading) return <Loading text="Loading dashboard…" />
  if (error)     return <ErrorBox message={error.message} />
  if (!d)        return <ErrorBox message="No QC data found. Run QC to generate results." />

  const flagData = (d.flag_type_summary || [])
    .map(f => ({ name: f.flag_type.replace(/_/g, ' '), count: f.n, sev: f.severity }))
    .sort((a, b) => b.count - a.count)

  const pieData = [
    { name: 'HIGH',   value: d.n_flags_high,   fill: SEV_COLOR.HIGH   },
    { name: 'MEDIUM', value: d.n_flags_medium,  fill: SEV_COLOR.MEDIUM },
    { name: 'LOW',    value: d.n_flags_low,     fill: SEV_COLOR.LOW    },
  ].filter(x => x.value > 0)

  const totalFlags  = d.n_flags_high + d.n_flags_medium + d.n_flags_low
  const lastRun     = d.run_at ? new Date(d.run_at).toLocaleString() : '—'

  return (
    <PageWrapper
      title="Dashboard"
      subtitle={`Last run ${lastRun} · ${d.data_source} data source`}
    >
      {/* HIGH flag alert */}
      {d.n_flags_high > 0 && (
        <div className="flex items-center gap-3 bg-red-950/40 border border-red-800/50 rounded-xl px-4 py-3 mb-5 text-sm">
          <AlertTriangle size={15} className="text-red-400 shrink-0" />
          <span className="text-red-300">
            <strong className="text-red-200">{d.n_flags_high} HIGH severity flag{d.n_flags_high > 1 ? 's' : ''}</strong>
            {' '}must be resolved before this data is used in analysis.
          </span>
          <Link to="/scorecard" className="ml-auto flex items-center gap-1 text-xs text-red-400 hover:text-red-300 whitespace-nowrap shrink-0">
            View <ChevronRight size={12} />
          </Link>
        </div>
      )}

      {/* Hero metrics */}
      <div className="card-p mb-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
          <KV label="Plots surveyed"
              value={`${d.n_plots_surveyed}/${d.n_plots_viable}`}
              accent={d.n_plots_surveyed === d.n_plots_viable ? 'text-emerald-400' : 'text-amber-400'}
              sub="viable plots" />
          <KV label="Surveys approved"
              value={d.n_surveys_approved}
              accent="text-gray-100"
              sub={d.n_surveys_rejected > 0 ? `${d.n_surveys_rejected} rejected` : 'none rejected'} />
          <KV label="Quadrats"
              value={d.n_quadrats}
              sub={`${d.pct_quadrats_with_herbs}% with herbs`} />
          <KV label="Pending species"
              value={d.n_pending_species}
              accent={d.n_pending_species > 0 ? 'text-amber-400' : 'text-emerald-400'}
              sub="awaiting botanist" />
        </div>

        <div className="border-t border-gray-800 mt-5 pt-4 flex flex-wrap gap-6">
          <KV label="Registered plots" value={d.n_plots_registered} />
          <KV label="Surveys total"    value={d.n_surveys_total}    />
          <KV label="HIGH flags"       value={d.n_flags_high}   accent={d.n_flags_high   > 0 ? 'text-red-400'   : 'text-emerald-400'} />
          <KV label="MEDIUM flags"     value={d.n_flags_medium} accent={d.n_flags_medium > 0 ? 'text-amber-400' : 'text-emerald-400'} />
          <KV label="LOW flags"        value={d.n_flags_low}    accent={d.n_flags_low    > 0 ? 'text-blue-400'  : 'text-emerald-400'} />
          <KV label="Total flags"      value={totalFlags} />
        </div>
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-3 gap-5">

        {/* Donut */}
        <div className="card-p flex flex-col">
          <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-4">Flags by severity</p>
          {pieData.length > 0 ? (
            <>
              <div className="flex justify-center">
                <PieChart width={160} height={160}>
                  <Pie data={pieData} cx={75} cy={75} innerRadius={45} outerRadius={72}
                       paddingAngle={3} dataKey="value">
                    {pieData.map((e, i) => <Cell key={i} fill={e.fill} opacity={0.85} />)}
                  </Pie>
                </PieChart>
              </div>
              <div className="space-y-2 mt-3">
                {pieData.map(e => (
                  <div key={e.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: e.fill }} />
                      <span className="text-gray-400">{e.name}</span>
                    </div>
                    <span className="font-bold" style={{ color: e.fill }}>{e.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-emerald-400 text-sm">
              ✓ No flags — all checks passed
            </div>
          )}
        </div>

        {/* Bar chart — 2 cols */}
        <div className="card-p md:col-span-2">
          <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-4">
            Flag breakdown — {totalFlags} total
          </p>
          {flagData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={flagData} layout="vertical"
                        margin={{ top: 0, right: 12, left: 168, bottom: 0 }}>
                <XAxis type="number" tick={{ fill: '#4b5563', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }}
                       width={164} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTip />} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={16}>
                  {flagData.map((e, i) => <Cell key={i} fill={SEV_COLOR[e.sev]} opacity={0.8} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-16 text-gray-600 text-sm">No flags</div>
          )}
          <div className="mt-3 pt-3 border-t border-gray-800 flex items-center justify-between">
            <p className="text-xs text-gray-600">Per-check breakdown with SOP references</p>
            <Link to="/scorecard" className="flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-400">
              Open Scorecard <ChevronRight size={12} />
            </Link>
          </div>
        </div>
      </div>
    </PageWrapper>
  )
}
