import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';

export function Layout({ children }: { children: React.ReactNode }) {
  const { userEmail, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const navLinks = [
    { to: '/', label: 'Dashboard' },
    { to: '/habits', label: 'Habits' },
  ];

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-surface border-b border-border sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link to="/" className="text-lg font-semibold text-primary">
              Ethara
            </Link>
            <nav className="hidden md:flex items-center gap-6">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`text-sm font-medium transition-colors ${
                    location.pathname === link.to
                      ? 'text-primary'
                      : 'text-muted hover:text-gray-900'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-4">
            <span className="hidden sm:block text-sm text-muted">{userEmail}</span>
            <button
              onClick={logout}
              className="text-sm text-muted hover:text-gray-900 transition-colors"
            >
              Sign out
            </button>
            <button
              className="md:hidden p-2 text-muted hover:text-gray-900"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label="Toggle menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav className="md:hidden border-t border-border bg-surface px-4 py-2">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setMenuOpen(false)}
                className={`block py-2 text-sm font-medium ${
                  location.pathname === link.to
                    ? 'text-primary'
                    : 'text-muted hover:text-gray-900'
                }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        )}
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {children}
      </main>
    </div>
  );
}
