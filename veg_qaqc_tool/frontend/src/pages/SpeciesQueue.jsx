import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, AlertTriangle } from 'lucide-react'
import { getSpeciesQueue } from '../api/client'
import { Loading, ErrorBox, Empty, PageWrapper } from '../components/ui'

const MODE_LABEL = {
  new_unknown: 'Unknown plant',
  new_missing: 'Not in master list',
}

export default function SpeciesQueue() {
  const [filter, setFilter] = useState({ plot_name: '', recorder: '' })

  const { data = [], isLoading, error } = useQuery({
    queryKey: ['species-queue', filter],
    queryFn:  () => getSpeciesQueue({
      ...(filter.plot_name ? { plot_name: filter.plot_name } : {}),
      ...(filter.recorder  ? { recorder:  filter.recorder  } : {}),
    }),
  })

  const set = (k, v) => setFilter(f => ({ ...f, [k]: v }))

  return (
    <PageWrapper
      title="Species Review Queue"
      subtitle={`${data.length} provisional entr${data.length !== 1 ? 'ies' : 'y'} awaiting taxonomic confirmation`}
    >
      {/* Context banner */}
      <div className="flex items-start gap-3 bg-amber-900/20 border border-amber-800/40 rounded-xl px-4 py-3.5 mb-5 text-sm text-amber-300">
        <AlertTriangle size={15} className="shrink-0 mt-0.5" />
        <p>
          These species were recorded under provisional names because they were absent from the
          pre-loaded species list. A botanist must confirm each entry before it can be included
          in richness analysis. Species richness counts are lower bounds until this queue is cleared.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Filter by plot…"
            className="dark-input pl-8 w-48"
            value={filter.plot_name}
            onChange={e => set('plot_name', e.target.value)}
          />
        </div>
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Filter by recorder…"
            className="dark-input pl-8 w-44"
            value={filter.recorder}
            onChange={e => set('recorder', e.target.value)}
          />
        </div>
      </div>

      {isLoading && <Loading />}
      {error     && <ErrorBox message={error.message} />}
      {!isLoading && !error && data.length === 0 && (
        <Empty text="No pending entries — queue is clear." />
      )}

      {data.length > 0 && (
        <div className="card overflow-hidden">
          <table className="dark-table">
            <thead>
              <tr>
                {['Plot', 'Date', 'Provisional name', 'Validated name', 'Entry mode', 'Status'].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map(s => (
                <tr key={s.id ?? s.survey_key}>
                  <td className="font-medium text-emerald-400">
                    {s.plot_name?.replace('SavMon_LW_', '') || '—'}
                  </td>
                  <td className="text-gray-500 text-xs">
                    {s.submission_date?.slice(0, 10) || '—'}
                  </td>
                  <td>
                    <code className="bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded text-[11px]">
                      {s.provisional_name || '—'}
                    </code>
                  </td>
                  <td className="text-gray-400 italic text-sm">
                    {s.validated_name
                      ? <span className="not-italic text-gray-300">{s.validated_name}</span>
                      : <span className="text-amber-500 not-italic">not confirmed</span>
                    }
                  </td>
                  <td className="text-xs text-gray-500">
                    {MODE_LABEL[s.species_entry_mode] || s.species_entry_mode || '—'}
                  </td>
                  <td>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-900/40 text-amber-300 ring-1 ring-amber-800/50">
                      {s.review_status || 'pending'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageWrapper>
  )
}
