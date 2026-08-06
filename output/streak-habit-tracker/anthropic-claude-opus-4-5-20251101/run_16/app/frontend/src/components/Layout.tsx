import { Outlet, Link, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useState } from 'react'

export default function Layout() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-surface border-b border-border sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link to="/" className="text-lg font-semibold text-gray-900">
              Ethara
            </Link>
            <nav className="hidden md:flex items-center gap-6">
              <Link
                to="/"
                className={`text-sm font-medium transition-colors ${
                  isActive('/') && location.pathname === '/'
                    ? 'text-primary'
                    : 'text-muted hover:text-gray-900'
                }`}
              >
                Dashboard
              </Link>
              <Link
                to="/habits"
                className={`text-sm font-medium transition-colors ${
                  isActive('/habits')
                    ? 'text-primary'
                    : 'text-muted hover:text-gray-900'
                }`}
              >
                Habits
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-4">
            <span className="hidden sm:block text-sm text-muted">{user?.email}</span>
            <button
              onClick={logout}
              className="text-sm text-muted hover:text-gray-900 transition-colors"
            >
              Sign out
            </button>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="md:hidden p-2 -mr-2 text-muted hover:text-gray-900"
              aria-label="Toggle menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav className="md:hidden border-t border-border px-4 py-2">
            <Link
              to="/"
              onClick={() => setMenuOpen(false)}
              className={`block py-2 text-sm font-medium ${
                isActive('/') && location.pathname === '/'
                  ? 'text-primary'
                  : 'text-muted'
              }`}
            >
              Dashboard
            </Link>
            <Link
              to="/habits"
              onClick={() => setMenuOpen(false)}
              className={`block py-2 text-sm font-medium ${
                isActive('/habits')
                  ? 'text-primary'
                  : 'text-muted'
              }`}
            >
              Habits
            </Link>
          </nav>
        )}
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
