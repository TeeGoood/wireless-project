'use client';

import { useState, FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';

interface LoginPopupProps {
  onClose?: () => void;
}

export function LoginPopup({ onClose }: LoginPopupProps) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password.trim()) {
      setError('Please enter username and password');
      return;
    }
    // Demo check (replace with real auth later)
    const DEMO_USERNAME = 'admin';
    const DEMO_PASSWORD = 'admin';
    if (username.trim() !== DEMO_USERNAME || password !== DEMO_PASSWORD) {
      setError('Invalid username or password');
      return;
    }
    login();
    setUsername('');
    setPassword('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" aria-modal="true" role="dialog">
      <div className="bg-white rounded-2xl shadow-xl border-2 border-[#ABB4B3] p-8 w-full max-w-sm mx-4">
        <h2 className="text-xl font-bold text-darkTeal mb-6">Login</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="login-username" className="block text-sm font-medium text-darkTeal mb-1">
              Username
            </label>
            <input
              id="login-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2 border-2 border-[#ABB4B3] rounded-lg text-darkTeal focus:outline-none focus:ring-2 focus:ring-mediumBlue"
              placeholder="Username"
              autoComplete="username"
            />
          </div>
          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-darkTeal mb-1">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2 border-2 border-[#ABB4B3] rounded-lg text-darkTeal focus:outline-none focus:ring-2 focus:ring-mediumBlue"
              placeholder="Password"
              autoComplete="current-password"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              className="flex-1 py-2 px-4 bg-mediumBlue text-white font-medium rounded-xl hover:opacity-90 transition-opacity"
            >
              Log in
            </button>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="py-2 px-4 border-2 border-[#ABB4B3] text-darkTeal rounded-xl hover:bg-gray-100 transition-colors"
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
