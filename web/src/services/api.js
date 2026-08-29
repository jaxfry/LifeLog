import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token and timezone info to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Add timezone headers
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const offset = -new Date().getTimezoneOffset();
    const sign = offset >= 0 ? '+' : '-';
    const pad = (num) => String(Math.floor(Math.abs(num))).padStart(2, '0');
    const offsetStr = `${sign}${pad(offset / 60)}${pad(offset % 60)}`; // e.g. +0530 or -0800

    config.headers['X-Client-Timezone'] = timezone;
    config.headers['X-Client-Offset'] = offsetStr;
  } catch (e) {
    console.warn('Failed to get timezone info', e);
  }

  return config;
});

let refreshPromise = null;

const tryRefreshToken = async () => {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  if (!refreshPromise) {
    refreshPromise = api
      .post('/token/refresh', { refresh_token: refreshToken })
      .then((response) => {
        localStorage.setItem('token', response.data.access_token);
        if (response.data.refresh_token) {
          localStorage.setItem('refresh_token', response.data.refresh_token);
        }
        return true;
      })
      .catch(() => {
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        return false;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
};

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const original = error.config;
      const isAuthEndpoint = original?.url?.includes('/token');
      if (original && !original._retried && !isAuthEndpoint) {
        original._retried = true;
        const refreshed = await tryRefreshToken();
        if (refreshed) {
          original.headers.Authorization = `Bearer ${localStorage.getItem('token')}`;
          return api(original);
        }
      }
      localStorage.removeItem('token');
      localStorage.removeItem('refresh_token');
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
    if (response.data.refresh_token) {
      localStorage.setItem('refresh_token', response.data.refresh_token);
    }

    return response.data;
  },

  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
  },
};

// Timeline API
export const timelineAPI = {
  getTimeline: async (params = {}) => {
    const response = await api.get('/timeline', { params });
    return response.data;
  },
};

// Chapters API
export const chaptersAPI = {
  getChapters: async (params = {}) => {
    const response = await api.get('/chapters', { params });
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
  getSummary: async (date) => {
    const response = await api.get(`/summaries/${date}`);
    return response.data;
  },
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

// Analytics API
export const analyticsAPI = {
  getStats: async () => {
    const response = await api.get('/analytics/stats');
    return response.data;
  },

  getActivityVolume: async (days = 7) => {
    const response = await api.get('/analytics/activity-volume', { params: { days } });
    return response.data;
  },

  getStatusDistribution: async () => {
    const response = await api.get('/analytics/status-distribution');
    return response.data;
  },

  getDashboardMetrics: async () => {
    const response = await api.get('/analytics/dashboard-metrics');
    return response.data;
  },

  getCollectorStats: async () => {
    const response = await api.get('/analytics/collector-stats');
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

// Daily Summaries API (GET)
export const summariesAPI = {
  getSummaries: async (params = {}) => {
    const response = await api.get('/summaries', { params });
    return response.data;
  },

  getSummaryByDate: async (date) => {
    const response = await api.get(`/summaries/${date}`);
    return response.data;
  },
};

// Extensions API
export const extensionsAPI = {
  getExtensions: async () => {
    const response = await api.get('/extensions');
    return response.data;
  },

  downloadExtension: async (extensionId) => {
    const response = await api.get(`/client/download/${extensionId}`, {
      responseType: 'blob'
    });
    return response.data;
  },

  uploadExtension: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/extensions/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

export const sourcesAPI = {
  list: async () => (await api.get('/sources')).data,
  create: async (source) => (await api.post('/sources', source)).data,
  update: async (id, changes) => (await api.patch(`/sources/${id}`, changes)).data,
  sync: async (id) => (await api.post(`/sources/${id}/sync`)).data,
  disconnect: async (id) => api.delete(`/sources/${id}`),
};

export const lifeAreasAPI = {
  list: async () => (await api.get('/life-areas')).data,
  templates: async () => (await api.get('/life-area-templates')).data,
  create: async (area) => (await api.post('/life-areas', area)).data,
  update: async (id, changes) => (await api.patch(`/life-areas/${id}`, changes)).data,
  memories: async (id) => (await api.get(`/life-areas/${id}/memories`)).data,
};

export const inboxAPI = {
  list: async (status = 'pending') => (await api.get('/inbox', { params: { status } })).data,
  decide: async (id, decision, value = {}) => (
    await api.post(`/inbox/${id}/decision`, { decision, value })
  ).data,
};

export const capturesAPI = {
  list: async () => (await api.get('/captures')).data,
  get: async (id) => (await api.get(`/captures/${id}`)).data,
  createNote: async (note) => (await api.post('/captures/notes', note)).data,
  createFiles: async ({ files, kind, intent, contextHints, lifeAreaIds = [], privacy = {} }) => {
    const form = new FormData();
    form.append('kind', kind);
    form.append('captured_at', new Date().toISOString());
    if (intent) form.append('intent', intent);
    if (contextHints) form.append('context_hints', JSON.stringify(contextHints));
    form.append('life_area_ids', JSON.stringify(lifeAreaIds));
    form.append('privacy', JSON.stringify(privacy));
    files.forEach((file) => form.append('files', file));
    return (await api.post('/captures', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })).data;
  },
  retry: async (id) => (await api.post(`/captures/${id}/retry`)).data,
  confirmClassification: async (id, label) => (
    await api.post(`/captures/${id}/classification`, { label })
  ).data,
};

// AI Chat API
export const aiChatAPI = {
  sendMessage: async ({ message, history = [], lifeAreaId = null, timezone = 'UTC' }) => {
    const response = await api.post('/ai/chat', {
      message,
      life_area_id: lifeAreaId,
      history,
      timezone,
    });
    return response.data;
  },

  checkHealth: async () => {
    const response = await api.get('/ai/chat/health');
    return response.data;
  },
};

// Scheduler API
export const schedulerAPI = {
  getJobs: async () => {
    const response = await api.get('/scheduler/jobs');
    return response.data;
  },
};

// Files API
export const filesAPI = {
  uploadFile: async (file, metadata = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    if (metadata.category) formData.append('category', metadata.category);
    if (metadata.tags) formData.append('tags', metadata.tags);
    if (metadata.description) formData.append('description', metadata.description);
    
    const response = await api.post('/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  listFiles: async (params = {}) => {
    const response = await api.get('/files', { params });
    return response.data;
  },
  
  getFile: async (fileId) => {
    const response = await api.get(`/files/${fileId}`);
    return response.data;
  },
};

export default api;
