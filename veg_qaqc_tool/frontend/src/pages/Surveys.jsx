import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getSurveys } from '../api/client'
import { StatusBadge, Loading, ErrorBox, Empty, PageWrapper } from '../components/ui'
import { ChevronRight, Search } from 'lucide-react'

const QC_COLOR = { pass: 'text-emerald-400', warning: 'text-amber-400', fail: 'text-red-400' }

export default function Surveys() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState({ qc_status: '', recorder: '', review_state: '' })

  const { data = [], isLoading, error } = useQuery({
    queryKey: ['surveys', filter],
    queryFn:  () => getSurveys({
      ...(filter.qc_status    ? { qc_status:    filter.qc_status    } : {}),
      ...(filter.recorder     ? { recorder:     filter.recorder     } : {}),
      ...(filter.review_state ? { review_state: filter.review_state } : {}),
    }),
  })

  const set = (k, v) => setFilter(f => ({ ...f, [k]: v }))

  return (
    <PageWrapper
      title="Surveys"
      subtitle={`${data.length} submission${data.length !== 1 ? 's' : ''}`}
    >
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <select className="dark-select" value={filter.qc_status} onChange={e => set('qc_status', e.target.value)}>
          <option value="">All QC statuses</option>
          <option value="pass">Pass</option>
          <option value="warning">Warning</option>
          <option value="fail">Fail</option>
        </select>

        <select className="dark-select" value={filter.review_state} onChange={e => set('review_state', e.target.value)}>
          <option value="">All review states</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>

        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Recorder name…"
            className="dark-input pl-8 w-44"
            value={filter.recorder}
            onChange={e => set('recorder', e.target.value)}
          />
        </div>
      </div>

      {isLoading && <Loading />}
      {error     && <ErrorBox message={error.message} />}
      {!isLoading && !error && data.length === 0 && <Empty text="No surveys match this filter." />}

      {data.length > 0 && (
        <div className="card overflow-hidden">
          <table className="dark-table">
            <thead>
              <tr>
                {['Plot', 'Recorder', 'Date', 'Duration', 'Quadrats', 'Species', 'Flags', 'Status', 'Review', ''].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map(s => (
                <tr
                  key={s.odk_key}
                  className="cursor-pointer"
                  onClick={() => navigate(`/surveys/${encodeURIComponent(s.odk_key)}`)}
                >
                  <td className={`font-medium ${QC_COLOR[s.qc_status] || 'text-gray-300'}`}>
                    {s.plot_name?.replace('SavMon_LW_', '') || '—'}
                  </td>
                  <td>{s.recorder || '—'}</td>
                  <td className="text-gray-500 text-xs">{s.submission_date?.slice(0, 10) || '—'}</td>
                  <td className="text-gray-400 text-xs font-mono">
                    {s.duration_min != null ? `${Math.round(s.duration_min)} min` : '—'}
                  </td>
                  <td className="text-center">
                    <span className={s.quadrats_completed < 20 ? 'text-amber-400 font-semibold' : 'text-gray-300'}>
                      {s.quadrats_completed ?? '—'}
                    </span>
                    <span className="text-gray-600">/20</span>
                  </td>
                  <td className="text-gray-300">{s.species_occurrences ?? '—'}</td>
                  <td>
                    {s.n_flags > 0
                      ? <span className="font-bold text-red-400">{s.n_flags}</span>
                      : <span className="text-gray-700">—</span>
                    }
                  </td>
                  <td><StatusBadge status={s.qc_status} /></td>
                  <td>
                    <span className={s.review_state === 'rejected'
                      ? 'text-red-400 font-medium text-xs'
                      : 'text-gray-600 text-xs'}>
                      {s.review_state || '—'}
                    </span>
                  </td>
                  <td><ChevronRight size={14} className="text-gray-700" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageWrapper>
  )
}
