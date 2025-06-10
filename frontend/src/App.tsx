import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import TimelinePage from "./pages/Timeline";
import Projects from "./pages/Projects";
import Insights from "./pages/Insights";
import ShellLayout from "./layouts/ShellLayout";
import DesignSystemShowcase from "./components/DesignSystemShowcase";
import { useThemeInitialization } from "./hooks/useThemeInitialization";

export default function App() {
  // Initialize theme system
  useThemeInitialization();

  return (
    <div className="h-full w-full overflow-hidden">
      <Routes>
        <Route element={<ShellLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="day/:day" element={<TimelinePage />} />
          <Route path="projects" element={<Projects />} />
          <Route path="insights" element={<Insights />} />
        </Route>

        {/* Design System Showcase */}
        <Route path="design-system" element={<DesignSystemShowcase />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
