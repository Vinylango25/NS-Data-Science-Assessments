import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useState } from 'react'
import { Menu, X, Leaf } from 'lucide-react'

import Dashboard    from './pages/Dashboard'
import Surveys      from './pages/Surveys'
import SurveyDetail from './pages/SurveyDetail'
import MapPage      from './pages/MapPage'
import SpeciesQueue from './pages/SpeciesQueue'
import RunQC        from './pages/RunQC'
import Scorecard    from './pages/Scorecard'
import Report       from './pages/Report'

const NAV = [
  { to: '/dashboard',     label: 'Dashboard'       },
  { to: '/surveys',       label: 'Surveys'         },
  { to: '/map',           label: 'Map'             },
  { to: '/species-queue', label: 'Species Queue'   },
  { to: '/scorecard',     label: 'Scorecard'       },
  { to: '/report',        label: 'Report'          },
  { to: '/run-qc',        label: 'Run QC'          },
]

function Layout({ children }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="min-h-screen flex flex-col bg-gray-950">
      {/* Nav */}
      <nav className="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-15 py-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-600/20 flex items-center justify-center">
                <Leaf size={16} className="text-emerald-400" />
              </div>
              <div>
                <p className="text-sm font-semibold text-white leading-none">Vegetation QA/QC</p>
                <p className="text-xs text-gray-500 leading-none mt-0.5">Natural State · SAVMON · Lewa 2026</p>
              </div>
            </div>

            {/* Desktop nav */}
            <div className="hidden md:flex items-center gap-0.5">
              {NAV.map(link => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) =>
                    `px-3 py-2 text-sm rounded-lg transition-colors ${
                      isActive
                        ? 'text-emerald-400 bg-emerald-900/30'
                        : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
            </div>

            <button onClick={() => setOpen(!open)} className="md:hidden p-2 text-gray-400 hover:text-gray-200">
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {open && (
          <div className="md:hidden border-t border-gray-800 bg-gray-900">
            <div className="px-4 py-3 space-y-1">
              {NAV.map(link => (
                <NavLink key={link.to} to={link.to} onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `block px-3 py-2 text-sm rounded-lg ${isActive ? 'text-emerald-400 bg-emerald-900/30' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`
                  }>
                  {link.label}
                </NavLink>
              ))}
            </div>
          </div>
        )}
      </nav>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-gray-800 py-3">
        <p className="text-center text-xs text-gray-600">
          Natural State Analytics · Vegetation QA/QC Tool v1.0.0 · SAVMON Baseline 2026
        </p>
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/"              element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"     element={<Dashboard />} />
          <Route path="/surveys"       element={<Surveys />} />
          <Route path="/surveys/:key"  element={<SurveyDetail />} />
          <Route path="/map"           element={<MapPage />} />
          <Route path="/species-queue" element={<SpeciesQueue />} />
          <Route path="/report"        element={<Report />} />
          <Route path="/run-qc"        element={<RunQC />} />
          <Route path="/scorecard"     element={<Scorecard />} />
          <Route path="*"              element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
