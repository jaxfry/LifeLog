import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import DayLayout from "./layouts/DayLayout"; // Updated import path
import DesignSystemShowcase from "./components/DesignSystemShowcase";
import { useThemeInitialization } from "./hooks/useThemeInitialization";

export default function App() {
  // Initialize theme system
  useThemeInitialization();

  return (
    <div className="h-full w-full overflow-hidden">
      <Routes>
        <Route index element={<Dashboard />} />

        {/* Specific day - using new TimeFlow layout */}
        <Route path="/day/:day" element={<DayLayout />} />

        {/* Design System Showcase */}
        <Route path="/design-system" element={<DesignSystemShowcase />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
