'use client';

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface AuthContextValue {
  isLogin: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLogin, setIsLogin] = useState(true);

  const login = useCallback(() => {
    setIsLogin(true);
  }, []);

  const logout = useCallback(() => {
    setIsLogin(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isLogin, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
