import React, { useState, useEffect } from "react";
import {
  DailySummaryWidget,
  QuickLinksWidget,
  ThemeWidget,
} from "../components/dashboard";

interface WidgetDef {
  label: string;
  key: string;
  element: React.ReactElement;
}

const AVAILABLE_WIDGETS: WidgetDef[] = [
  { key: "quickLinks", label: "Quick Links", element: <QuickLinksWidget /> },
  { key: "dailySummary", label: "Daily Summary", element: <DailySummaryWidget /> },
  { key: "theme", label: "Theme Switcher", element: <ThemeWidget /> },
];

export default function Home() {
  const [selected, setSelected] = useState<string[]>([]);
  const [customize, setCustomize] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("dashboard-widgets");
    if (stored) {
      try {
        setSelected(JSON.parse(stored));
      } catch {
        setSelected(AVAILABLE_WIDGETS.map((w) => w.key));
      }
    } else {
      setSelected(AVAILABLE_WIDGETS.map((w) => w.key));
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("dashboard-widgets", JSON.stringify(selected));
  }, [selected]);

  const toggle = (key: string) => {
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  return (
    <div className="h-full w-full bg-background-secondary p-6 overflow-auto">
      <header className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold text-primary">Dashboard</h1>
        <button
          className="px-3 py-1 bg-primary-600 text-on-primary rounded-md focus-ring"
          onClick={() => setCustomize((c) => !c)}
        >
          {customize ? "Done" : "Customize"}
        </button>
      </header>

      {customize && (
        <section className="mb-4 border-card bg-secondary p-4 shadow-card" aria-label="Dashboard settings">
          <h2 className="text-lg font-medium mb-2 text-primary">Choose Widgets</h2>
          <div className="space-y-2">
            {AVAILABLE_WIDGETS.map((w) => (
              <label key={w.key} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.includes(w.key)}
                  onChange={() => toggle(w.key)}
                />
                <span>{w.label}</span>
              </label>
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {AVAILABLE_WIDGETS.filter((w) => selected.includes(w.key)).map((w) => (
          <div key={w.key}>{w.element}</div>
        ))}
        {selected.length === 0 && !customize && (
          <p className="text-secondary">No widgets selected.</p>
        )}
      </div>
    </div>
  );
}
