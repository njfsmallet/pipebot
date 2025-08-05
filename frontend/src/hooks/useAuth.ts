import { useState, useEffect } from 'react';
import { User } from '../types';
import { API_ENDPOINTS } from '../config/api';

export const useAuth = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkAuth = async () => {
    try {
      const response = await fetch(API_ENDPOINTS.auth.user);
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        setIsAuthenticated(true);
        setError(null);
      } else {
        const errorData = await response.json();
        setIsAuthenticated(false);
        setUser(null);
        setError(errorData.detail || 'Authentication failed');
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      setIsAuthenticated(false);
      setUser(null);
      setError('Failed to check authentication status');
    }
  };

  const handleLogin = () => {
    setError(null);
    window.location.href = API_ENDPOINTS.auth.login;
  };

  const handleLogout = async () => {
    try {
      await fetch(API_ENDPOINTS.auth.logout);
      
      // Update state
      setIsAuthenticated(false);
      setUser(null);
      setError(null);
      
      // Redirect to home page
      window.location.href = '/';
    } catch (error) {
      console.error('Logout failed:', error);
      setError('Failed to logout');
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  return {
    isAuthenticated,
    user,
    error,
    handleLogin,
    handleLogout,
    checkAuth
  };
}; 