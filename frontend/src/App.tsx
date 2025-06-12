import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import TimelinePage from './pages/TimelinePage';
import ProjectsPage from './pages/ProjectsPage';
import InsightsPage from './pages/InsightsPage';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/timeline" element={<TimelinePage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/insights" element={<InsightsPage />} />
      </Routes>
    </Router>
  );
}

export default App;
