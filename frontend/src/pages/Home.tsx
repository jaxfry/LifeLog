import React, { useState, useEffect } from "react";
import {
  DailySummaryWidget,
  QuickLinksWidget,
  ThemeWidget,
  StatsWidget,
  RecentDaysWidget,
  AIInsightsWidget,
} from "../components/dashboard";

interface WidgetDef {
  label: string;
  key: string;
  element: React.ReactElement;
}

const AVAILABLE_WIDGETS: WidgetDef[] = [
  { key: "quickLinks", label: "Quick Links", element: <QuickLinksWidget /> },
  {
    key: "dailySummary",
    label: "Daily Summary",
    element: <DailySummaryWidget />,
  },
  { key: "stats", label: "Daily Stats", element: <StatsWidget /> },
  { key: "recent", label: "Recent Days", element: <RecentDaysWidget /> },
  { key: "theme", label: "Theme Switcher", element: <ThemeWidget /> },
  { key: "insights", label: "AI Insights", element: <AIInsightsWidget /> },
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
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const move = (key: string, direction: -1 | 1) => {
    setSelected((prev) => {
      const idx = prev.indexOf(key);
      if (idx === -1) return prev;
      const newIdx = idx + direction;
      if (newIdx < 0 || newIdx >= prev.length) return prev;
      const arr = [...prev];
      arr.splice(idx, 1);
      arr.splice(newIdx, 0, key);
      return arr;
    });
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
        <section
          className="mb-4 border-card bg-secondary p-4 shadow-card"
          aria-label="Dashboard settings"
        >
          <h2 className="text-lg font-medium mb-2 text-primary">
            Choose Widgets
          </h2>
          <div className="space-y-2">
            {AVAILABLE_WIDGETS.map((w) => {
              const idx = selected.indexOf(w.key);
              return (
                <div key={w.key} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selected.includes(w.key)}
                    onChange={() => toggle(w.key)}
                  />
                  <span className="flex-1">{w.label}</span>
                  <button
                    className="px-1 text-xs text-secondary hover:text-primary"
                    onClick={() => move(w.key, -1)}
                    disabled={idx <= 0}
                    aria-label="Move up"
                  >
                    ▲
                  </button>
                  <button
                    className="px-1 text-xs text-secondary hover:text-primary"
                    onClick={() => move(w.key, 1)}
                    disabled={idx === -1 || idx === selected.length - 1}
                    aria-label="Move down"
                  >
                    ▼
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {selected.map((key) => {
          const w = AVAILABLE_WIDGETS.find((w) => w.key === key);
          return w ? <div key={w.key}>{w.element}</div> : null;
        })}
        {selected.length === 0 && !customize && (
          <p className="text-secondary">No widgets selected.</p>
        )}
      </div>
    </div>
  );
}
