// src/App.tsx
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import DayView from "./pages/DayView";

export default function App() {
  return (
    <Routes>
      {/* Redirect “/” to today’s day view */}
      <Route
        index
        element={<Navigate to={`/day/${new Date().toISOString().slice(0, 10)}`} replace />}
      />

      {/* Show the DayView for any /day/:day */}
      <Route path="/day/:day" element={<DayView />} />

      {/* Fallback: redirect to home */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
