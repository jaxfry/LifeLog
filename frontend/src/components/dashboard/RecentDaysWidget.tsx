import { Link } from "react-router-dom";

function getRecentDays(count: number) {
  const days: string[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push(d.toISOString().slice(0, 10));
  }
  return days;
}

export default function RecentDaysWidget() {
  const days = getRecentDays(7);

  return (
    <section
      className="border-card bg-secondary p-4 shadow-card"
      aria-label="Recent days"
    >
      <h2 className="text-lg font-semibold mb-2 text-primary">Recent Days</h2>
      <ul className="space-y-2">
        {days.map((day) => (
          <li key={day}>
            <Link
              to={`/day/${day}`}
              className="text-link hover:underline focus:underline focus:ring-2 focus:ring-primary-500 rounded"
            >
              {day}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
