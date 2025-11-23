import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      // Trigger a full page reload to /login to ensure clean state
      // This is acceptable for auth errors where we want to clear everything
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  login: async (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    
    const response = await api.post('/token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    
    if (response.data.access_token) {
      localStorage.setItem('token', response.data.access_token);
    }
    
    return response.data;
  },
  
  logout: () => {
    localStorage.removeItem('token');
  },
};

// Timeline API
export const timelineAPI = {
  getTimeline: async (params = {}) => {
    const response = await api.get('/timeline', { params });
    return response.data;
  },
};

// Sessions API
export const sessionsAPI = {
  getSessions: async (params = {}) => {
    const response = await api.get('/sessions', { params });
    return response.data;
  },
};

// Daily Summary API
export const dailySummaryAPI = {
  generateSummary: async (date) => {
    const response = await api.post(`/admin/generate-summary/${date}`);
    return response.data;
  },
};

// Logs API
export const logsAPI = {
  getLogs: async (params = {}) => {
    const response = await api.get('/logs', { params });
    return response.data;
  },
};

// Events API
export const eventsAPI = {
  getEvents: async (params = {}) => {
    const response = await api.get('/events', { params });
    return response.data;
  },
};

// Devices API
export const devicesAPI = {
  getDevices: async () => {
    const response = await api.get('/devices');
    return response.data;
  },
  
  createDevice: async (device) => {
    const response = await api.post('/devices', device);
    return response.data;
  },
  
  deleteDevice: async (deviceId) => {
    await api.delete(`/devices/${deviceId}`);
  },
  
  rotateKey: async (deviceId) => {
    const response = await api.post(`/devices/${deviceId}/rotate-key`);
    return response.data;
  },
};

// Config API
export const configAPI = {
  getConfig: async () => {
    const response = await api.get('/config');
    return response.data;
  },
  
  updateConfig: async (key, value, description) => {
    const response = await api.put(`/config/${key}`, { value, description });
    return response.data;
  },
};

// Health API
export const healthAPI = {
  getHealth: async () => {
    const response = await api.get('/health');
    return response.data;
  },
  
  getReadiness: async () => {
    const response = await api.get('/ready');
    return response.data;
  },
};

export default api;
