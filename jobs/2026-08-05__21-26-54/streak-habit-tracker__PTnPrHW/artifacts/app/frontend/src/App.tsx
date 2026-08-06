import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './hooks/useAuth';
import { ToastProvider } from './components/Toast';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/Login';
import { DashboardPage } from './pages/Dashboard';
import { HabitsPage } from './pages/Habits';
import { HabitDetailPage } from './pages/HabitDetail';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ToastProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <DashboardPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/habits"
                element={
                  <ProtectedRoute>
                    <HabitsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/habits/:id"
                element={
                  <ProtectedRoute>
                    <HabitDetailPage />
                  </ProtectedRoute>
                }
              />
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
