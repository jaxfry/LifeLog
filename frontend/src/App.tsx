import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import DayView from "./pages/DayView";
import DesignSystemShowcase from "./components/DesignSystemShowcase";

export default function App() {
  return (
    <Routes>
      <Route index element={<Home />} />

      {/* Specific day */}
      <Route path="/day/:day" element={<DayView />} />

      {/* Design System Showcase */}
      <Route path="/design-system" element={<DesignSystemShowcase />} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
