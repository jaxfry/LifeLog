import AIInsights from '../AIInsights';
import { useDayData } from '../../hooks/useDayData';

export default function AIInsightsWidget() {
  const { data, loading, error } = useDayData('2025-05-22');

  if (loading) {
    return (
      <section className="border-card bg-secondary p-4 shadow-card">
        <p className="text-secondary">Loading insights...</p>
      </section>
    );
  }

  if (error || !data) {
    return (
      <section className="border-card bg-secondary p-4 shadow-card">
        <p className="text-secondary">Failed to load insights.</p>
      </section>
    );
  }

  return (
    <section className="border-card bg-secondary p-4 shadow-card" aria-label="AI insights">
      <h2 className="text-lg font-semibold mb-2 text-primary">AI Insights</h2>
      <AIInsights summary={data.summary} entries={data.entries} />
    </section>
  );
}
