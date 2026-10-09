import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup } from 'react-leaflet'
import { getPlots } from '../api/client'
import { Loading, ErrorBox, PageWrapper } from '../components/ui'

const STATUS_COLOR = { pass: '#34d399', warning: '#fb923c', fail: '#f87171' }
const plotColor    = p => !p.was_surveyed ? '#6b7280' : (STATUS_COLOR[p.qc_status] || '#6b7280')

export default function MapPage() {
  const { data = [], isLoading, error } = useQuery({
    queryKey: ['plots'],
    queryFn:  () => getPlots({}),
  })

  const withCoords = data.filter(p => p.centroid_lat != null && p.centroid_lon != null)

  const centre = withCoords.length
    ? [
        withCoords.reduce((s, p) => s + p.centroid_lat, 0) / withCoords.length,
        withCoords.reduce((s, p) => s + p.centroid_lon, 0) / withCoords.length,
      ]
    : [0.22, 37.47]

  const legend = [
    ['#34d399', 'Surveyed — pass'],
    ['#fb923c', 'Surveyed — warning / fail'],
    ['#6b7280', 'Not surveyed'],
  ]

  return (
    <PageWrapper
      title="Transect Map"
      subtitle={`${withCoords.length} plots with GPS coordinates · SAVMON Baseline 2026`}
    >
      {isLoading && <Loading />}
      {error     && <ErrorBox message={error.message} />}

      {!isLoading && !error && (
        <>
          {/* Legend */}
          <div className="flex flex-wrap gap-5 mb-4">
            {legend.map(([color, label]) => (
              <span key={label} className="flex items-center gap-2 text-xs text-gray-400">
                <span className="w-3 h-3 rounded-full shrink-0" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>

          {/* Map */}
          <div className="rounded-xl overflow-hidden ring-1 ring-gray-800" style={{ height: '560px' }}>
            <MapContainer center={centre} zoom={12} style={{ height: '100%', width: '100%' }}>
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              />

              {/* Transect lines */}
              {withCoords
                .filter(p => p.ep_a_lat && p.ep_b_lat)
                .map(p => (
                  <Polyline
                    key={`line-${p.plot_name}`}
                    positions={[[p.ep_a_lat, p.ep_a_lon], [p.ep_b_lat, p.ep_b_lon]]}
                    pathOptions={{ color: plotColor(p), weight: 2.5, opacity: 0.8 }}
                  />
                ))
              }

              {/* Plot centroids */}
              {withCoords.map(p => (
                <CircleMarker
                  key={p.plot_name}
                  center={[p.centroid_lat, p.centroid_lon]}
                  radius={7}
                  pathOptions={{
                    color: '#111827',
                    fillColor: plotColor(p),
                    fillOpacity: 0.9,
                    weight: 1.5,
                  }}
                >
                  <Popup>
                    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', minWidth: '160px', fontSize: '13px' }}>
                      <p style={{ fontWeight: 600, marginBottom: '6px', color: '#111' }}>
                        {p.plot_name?.replace('SavMon_LW_', '')}
                      </p>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                        <tbody>
                          {[
                            ['QC status', p.qc_status || 'not surveyed'],
                            ['Transect', p.transect_length_m != null ? `${p.transect_length_m.toFixed(1)} m` : '—'],
                            ['Species', p.total_species_occurrences ?? '—'],
                            ['Flags', p.n_flags > 0 ? `${p.n_flags} flag${p.n_flags > 1 ? 's' : ''}` : 'none'],
                          ].map(([k, v]) => (
                            <tr key={k}>
                              <td style={{ color: '#6b7280', paddingBottom: '2px', paddingRight: '8px' }}>{k}</td>
                              <td style={{ fontWeight: 500, color: '#111' }}>{v}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </div>
        </>
      )}
    </PageWrapper>
  )
}
