import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Habits from './pages/Habits'
import HabitDetail from './pages/HabitDetail'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted">Loading...</div>
      </div>
    )
  }

  if (!token) {
    const currentPath = window.location.pathname
    return <Navigate to={`/login?next=${encodeURIComponent(currentPath)}`} replace />
  }

  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="habits" element={<Habits />} />
        <Route path="habits/:id" element={<HabitDetail />} />
      </Route>
    </Routes>
  )
}
