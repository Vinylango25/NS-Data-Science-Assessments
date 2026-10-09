import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Play, CheckCircle, XCircle, Clock, Loader, ClipboardCheck, ChevronRight } from 'lucide-react'
import { getRuns, triggerRun } from '../api/client'
import { Loading, ErrorBox, PageWrapper } from '../components/ui'

const STATUS_ICON = {
  queued:   <Clock       size={15} className="text-gray-400" />,
  running:  <Loader      size={15} className="text-blue-400 animate-spin" />,
  complete: <CheckCircle size={15} className="text-emerald-500" />,
  error:    <XCircle     size={15} className="text-red-500" />,
}

const STATUS_LABEL = {
  queued:   'text-gray-500',
  running:  'text-blue-400 font-medium',
  complete: 'text-emerald-400 font-medium',
  error:    'text-red-400 font-medium',
}

export default function RunQC() {
  const qc = useQueryClient()
  const [source, setSource] = useState('csv')

  const { data: runs = [], isLoading } = useQuery({
    queryKey:        ['runs'],
    queryFn:         getRuns,
    refetchInterval: 5_000,
  })

  const trigger = useMutation({
    mutationFn: () => triggerRun(source),
    onSuccess: () => {
      qc.invalidateQueries(['runs'])
      qc.invalidateQueries(['dashboard'])
      qc.invalidateQueries(['flags'])
      qc.invalidateQueries(['plots'])
    },
  })

  const hasRunning = runs.some(r => r.status === 'queued' || r.status === 'running')

  return (
    <PageWrapper
      title="Run QC"
      subtitle="Trigger the SOP quality check pipeline against the current vegetation survey data"
      action={
        <Link
          to="/scorecard"
          className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm
                     font-medium px-4 py-2 rounded-lg ring-1 ring-gray-700 transition-colors"
        >
          <ClipboardCheck size={15} className="text-emerald-400" />
          View Scorecard
          <ChevronRight size={13} className="text-gray-500" />
        </Link>
      }
    >

      {/* ── Trigger panel ──────────────────────────────────────────────────── */}
      <div className="card-p mb-5">
        <h2 className="section-title">Start a new QC run</h2>

        <div className="flex flex-wrap items-end gap-4 mt-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">Data source</label>
            <select
              className="dark-select"
              value={source}
              onChange={e => setSource(e.target.value)}
            >
              <option value="csv">CSV files (demo / local)</option>
              <option value="postgres">PostgreSQL (production)</option>
            </select>
          </div>

          <button
            onClick={() => trigger.mutate()}
            disabled={trigger.isPending || hasRunning}
            className="btn-primary"
          >
            {trigger.isPending
              ? <><Loader size={14} className="animate-spin" /> Starting…</>
              : <><Play size={14} /> Run QC now</>
            }
          </button>

          {hasRunning && (
            <span className="text-sm text-blue-400 flex items-center gap-1.5">
              <Loader size={13} className="animate-spin" />
              A run is in progress — refreshing every 5 s
            </span>
          )}
        </div>

        {trigger.isSuccess && (
          <div className="mt-4 text-sm text-emerald-300 bg-emerald-900/20 border border-emerald-800/50 rounded-lg px-4 py-3">
            ✓ Run queued (ID: {trigger.data?.run_id}). Results appear below when complete.
          </div>
        )}
        {trigger.isError && (
          <div className="mt-4 text-sm text-red-400 bg-red-900/20 border border-red-800/50 rounded-lg px-4 py-3">
            Failed to start run: {trigger.error?.message}
          </div>
        )}
      </div>

      {/* ── SOP parameters ─────────────────────────────────────────────────── */}
      <div className="card-p mb-5">
        <h2 className="section-title">SOP parameters</h2>
        <p className="text-xs text-gray-500 mb-4">
          Thresholds applied by each check. Change in{' '}
          <code className="bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded text-[11px]">.env</code>{' '}
          if the project protocol differs.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
          {[
            ['Quadrats per survey',       '20'],
            ['Survey duration max',        '180 min'],
            ['Transect length range',      '40 – 60 m'],
            ['Midpoint displacement max',  '25 m'],
            ['Quadrat GPS accuracy max',   '5 m'],
            ['Canonical format',           'Genus_species'],
          ].map(([k, v]) => (
            <div key={k} className="bg-gray-800/50 rounded-lg px-3 py-2.5">
              <p className="text-xs text-gray-500 mb-0.5">{k}</p>
              <p className="font-semibold text-gray-200 text-sm">{v}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 pt-4 border-t border-gray-800 flex items-center justify-between">
          <p className="text-xs text-gray-500">
            See the full scorecard for all 14 checks and their current results.
          </p>
          <Link
            to="/scorecard"
            className="flex items-center gap-1.5 text-sm text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            Open Scorecard <ChevronRight size={13} />
          </Link>
        </div>
      </div>

      {/* ── Run history ─────────────────────────────────────────────────────── */}
      <div className="card-p">
        <h2 className="section-title">Run history</h2>

        {isLoading && <Loading />}

        {!isLoading && runs.length === 0 && (
          <p className="text-sm text-gray-600 py-8 text-center">No runs yet. Start one above.</p>
        )}

        {runs.length > 0 && (
          <div className="overflow-x-auto mt-3">
            <table className="dark-table min-w-full">
              <thead>
                <tr>
                  {['Run', 'Started', 'Source', 'Status', 'Surveys', 'Flags H / M / L', 'Pending species'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map(r => (
                  <tr key={r.id}>
                    <td className="font-mono text-gray-500 text-xs">#{r.id}</td>
                    <td className="text-gray-500 text-xs whitespace-nowrap">
                      {r.run_at ? new Date(r.run_at).toLocaleString() : '—'}
                    </td>
                    <td className="text-gray-500">{r.data_source}</td>
                    <td>
                      <span className={`flex items-center gap-1.5 ${STATUS_LABEL[r.status] || 'text-gray-500'}`}>
                        {STATUS_ICON[r.status]}
                        {r.status}
                      </span>
                    </td>
                    <td>{r.n_surveys ?? '—'}</td>
                    <td>
                      {r.status === 'complete' ? (
                        <span className="font-mono text-sm">
                          <span className="text-red-400 font-semibold">{r.n_flags_high}</span>
                          <span className="text-gray-600"> / </span>
                          <span className="text-amber-400">{r.n_flags_medium}</span>
                          <span className="text-gray-600"> / </span>
                          <span className="text-blue-400">{r.n_flags_low}</span>
                        </span>
                      ) : <span className="text-gray-600">—</span>}
                    </td>
                    <td>
                      {r.n_pending_species != null
                        ? <span className={r.n_pending_species > 0 ? 'text-amber-400 font-medium' : 'text-gray-500'}>
                            {r.n_pending_species}
                          </span>
                        : <span className="text-gray-600">—</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageWrapper>
  )
}
