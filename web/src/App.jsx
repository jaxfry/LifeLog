import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Timeline from './pages/Timeline';
import DailySummaries from './pages/DailySummaries';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import Devices from './pages/Devices';
import Extensions from './pages/Extensions';
import DataExplorer from './pages/DataExplorer';
import AIInsights from './pages/AIInsights';
import Files from './pages/Files';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Dashboard />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/timeline"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Timeline />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/devices"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Devices />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/extensions"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Extensions />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/data-explorer"
              element={
                <ProtectedRoute>
                  <Layout>
                    <DataExplorer />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/files"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Files />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/ai-insights"
              element={
                <ProtectedRoute>
                  <Layout>
                    <AIInsights />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/summaries"
              element={
                <ProtectedRoute>
                  <Layout>
                    <DailySummaries />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/analytics"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Analytics />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Settings />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
