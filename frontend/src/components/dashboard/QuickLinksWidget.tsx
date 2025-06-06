import { Link } from "react-router-dom";

export default function QuickLinksWidget() {
  return (
    <section
      className="border-card bg-secondary p-4 shadow-card"
      aria-label="Quick links"
    >
      <h2 className="text-lg font-semibold mb-2 text-primary">Quick Links</h2>
      <ul className="space-y-2">
        <li>
          <Link
            to="/day/2025-05-22"
            className="text-link hover:underline focus:underline focus:ring-2 focus:ring-primary-500 rounded"
          >
            Sample Day (May 22, 2025)
          </Link>
        </li>
        <li>
          <Link
            to="/design-system"
            className="text-link hover:underline focus:underline focus:ring-2 focus:ring-primary-500 rounded"
          >
            Design System Showcase
          </Link>
        </li>
      </ul>
    </section>
  );
}
