import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { api, setAuthToken, getAuthToken, setOnUnauthorized } from '../lib/api';

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  userEmail: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  sessionExpired: boolean;
  clearSessionExpired: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const logout = useCallback(() => {
    setAuthToken(null);
    setIsAuthenticated(false);
    setUserEmail(null);
    localStorage.removeItem('user_email');
    navigate('/login');
  }, [navigate]);

  useEffect(() => {
    const token = getAuthToken();
    const email = localStorage.getItem('user_email');
    if (token && email) {
      setIsAuthenticated(true);
      setUserEmail(email);
    }
    setIsLoading(false);

    setOnUnauthorized(() => {
      setSessionExpired(true);
      setAuthToken(null);
      setIsAuthenticated(false);
      setUserEmail(null);
      localStorage.removeItem('user_email');
      const currentPath = location.pathname;
      navigate(`/login?next=${encodeURIComponent(currentPath)}`);
    });
  }, [navigate, location.pathname]);

  const login = async (email: string, password: string) => {
    const response = await api.login(email, password);
    setAuthToken(response.access_token);
    setIsAuthenticated(true);
    setUserEmail(email);
    localStorage.setItem('user_email', email);
  };

  const clearSessionExpired = () => {
    setSessionExpired(false);
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isLoading,
        userEmail,
        login,
        logout,
        sessionExpired,
        clearSessionExpired,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
