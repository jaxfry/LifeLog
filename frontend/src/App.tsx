import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import DayLayout from "./components/layout/DayLayout";
import DesignSystemShowcase from "./components/DesignSystemShowcase";

export default function App() {
  return (
    <Routes>
      <Route index element={<Home />} />

      {/* Specific day - using new TimeFlow layout */}
      <Route path="/day/:day" element={<DayLayout />} />

      {/* Design System Showcase */}
      <Route path="/design-system" element={<DesignSystemShowcase />} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
