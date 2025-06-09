import { Link } from "react-router-dom";

export default function Dashboard() {
  return (
    <main className="h-full w-full flex flex-col items-center justify-center bg-surface-secondary text-primary space-y-6 p-4">
      <h1 className="text-3xl font-bold">TimeFlow Dashboard</h1>
      <p className="text-secondary text-center max-w-md">
        Welcome to TimeFlow! Choose a date from the sidebar once the timeline view is implemented, or explore the sample day below.
      </p>
      <Link
        to="/day/2025-05-22"
        className="px-4 py-2 bg-primary-600 text-on-primary rounded-lg hover:bg-primary-700 transition-colors"
      >
        View Sample Day
      </Link>
    </main>
  );
}
