const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export const API_ENDPOINTS = {
  auth: {
    login: `${API_BASE_URL}/api/auth/login`,
    logout: `${API_BASE_URL}/api/auth/logout`,
    user: `${API_BASE_URL}/api/auth/user`,
  },
  converse: `${API_BASE_URL}/api/converse`,
  converseStream: `${API_BASE_URL}/api/converse/stream`,
  clear: `${API_BASE_URL}/api/clear`,
}; 