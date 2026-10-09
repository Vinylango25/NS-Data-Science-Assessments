import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RefreshCw, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'
import { getSurvey, regenerateNarrative } from '../api/client'
import { SeverityBadge, StatusBadge, Loading, ErrorBox, PageWrapper } from '../components/ui'

const SEV_ICON = {
  HIGH:   <XCircle   size={14} className="text-red-400 shrink-0 mt-0.5" />,
  MEDIUM: <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />,
  LOW:    <AlertTriangle size={14} className="text-blue-400 shrink-0 mt-0.5" />,
}

function KV({ label, value, accent }) {
  return (
    <div className="bg-gray-800/50 rounded-lg px-4 py-3">
      <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-xl font-bold ${accent || 'text-gray-100'}`}>{value ?? '—'}</p>
    </div>
  )
}

export default function SurveyDetail() {
  const { key }   = useParams()
  const navigate  = useNavigate()
  const qc        = useQueryClient()
  const surveyKey = decodeURIComponent(key)

  const { data, isLoading, error } = useQuery({
    queryKey: ['survey', surveyKey],
    queryFn:  () => getSurvey(surveyKey),
  })

  const regen = useMutation({
    mutationFn: () => regenerateNarrative(surveyKey),
    onSuccess:  () => qc.invalidateQueries(['survey', surveyKey]),
  })

  if (isLoading) return <Loading />
  if (error)     return <ErrorBox message={error.message} />
  if (!data)     return <ErrorBox message="Survey not found." />

  const { survey, flags = [], narrative } = data
  const plotShort = survey.plot_name?.replace('SavMon_LW_', '') || survey.plot_name

  const durationOk = !survey.duration_min || (survey.duration_min >= 10 && survey.duration_min <= 180)

  return (
    <PageWrapper
      title={plotShort}
      subtitle={`Recorded by ${survey.recorder || '?'} · ${survey.submission_date?.slice(0, 10) || '?'}`}
      action={
        <button onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors">
          <ArrowLeft size={15} /> Back
        </button>
      }
    >
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
        <div className="bg-gray-800/50 rounded-lg px-4 py-3 sm:col-span-1">
          <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">QC Status</p>
          <StatusBadge status={survey.qc_status} />
        </div>
        <KV label="Quadrats"  value={`${survey.quadrats_completed ?? '—'}/20`}
            accent={survey.quadrats_completed < 20 ? 'text-amber-400' : 'text-gray-100'} />
        <KV label="Herb quadrats"  value={survey.quadrats_with_herbs ?? '—'} />
        <KV label="Species"        value={survey.species_occurrences ?? '—'} />
        <KV label="Duration"
            value={survey.duration_min != null ? `${Math.round(survey.duration_min)} min` : '—'}
            accent={!durationOk ? 'text-amber-400' : 'text-gray-100'} />
      </div>

      {/* Narrative */}
      <div className="card-p mb-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[11px] text-gray-500 uppercase tracking-wider">QC Narrative</p>
          <button
            onClick={() => regen.mutate()}
            disabled={regen.isPending}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors disabled:opacity-40"
          >
            <RefreshCw size={12} className={regen.isPending ? 'animate-spin' : ''} />
            {regen.isPending ? 'Generating…' : 'Regenerate'}
          </button>
        </div>

        {narrative?.narrative
          ? <p className="text-sm text-gray-300 leading-relaxed">{narrative.narrative}</p>
          : <p className="text-sm text-gray-600 italic">
              No narrative yet.{' '}
              <button onClick={() => regen.mutate()} className="text-emerald-600 hover:text-emerald-400 not-italic">
                Generate one.
              </button>
            </p>
        }
        {narrative?.model && (
          <p className="text-[11px] text-gray-600 mt-2">Model: {narrative.model}</p>
        )}
      </div>

      {/* Flags */}
      <div className="card-p">
        <div className="flex items-center gap-2 mb-4">
          <p className="text-[11px] text-gray-500 uppercase tracking-wider">QC Flags</p>
          {flags.length > 0 && (
            <span className="text-xs text-gray-600">({flags.length})</span>
          )}
        </div>

        {flags.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-emerald-500">
            <CheckCircle2 size={15} />
            All checks passed — no flags on this survey.
          </div>
        ) : (
          <div className="space-y-2.5">
            {flags.map((f, i) => (
              <div key={f.id ?? i}
                   className="flex gap-3 bg-gray-800/40 rounded-lg border border-gray-700/50 px-4 py-3">
                <div className="pt-0.5 shrink-0">
                  {SEV_ICON[f.severity]}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <SeverityBadge severity={f.severity} />
                    <span className="text-[11px] font-mono text-gray-600">
                      [{f.flag_id}] {f.flag_type}
                      {f.quadrat_number != null && ` · Q${f.quadrat_number}`}
                    </span>
                  </div>
                  <p className="text-sm text-gray-300">{f.description}</p>
                  {f.field_value && (
                    <p className="text-xs text-gray-500 mt-1.5">
                      Found:{' '}
                      <code className="bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                        {f.field_value}
                      </code>
                      {f.expected_value && (
                        <> · Expected:{' '}
                          <code className="bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                            {f.expected_value}
                          </code>
                        </>
                      )}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </PageWrapper>
  )
}
