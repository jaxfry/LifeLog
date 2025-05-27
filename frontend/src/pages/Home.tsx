import { useNavigate } from "react-router-dom";
import { useState } from "react";
import Card from "../components/ui/Card";

export default function Home() {
  const navigate = useNavigate();
  const [date, setDate] = useState<string>(() =>
    new Date().toISOString().slice(0, 10)
  );

  const go = () => navigate(`/day/${date}`);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-md bg-white rounded-2xl shadow p-8 space-y-6">
        <h1 className="text-2xl font-bold text-gray-800 text-center">
          LifeLog Viewer
        </h1>

        <div>
          <label className="block text-sm font-medium mb-1">Pick a date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full px-3 py-2 border rounded-md"
          />
        </div>

        <button
          onClick={go}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          View Day
        </button>
      </div>

      {/* Add a responsive grid layout to the Home page */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card>
          <h2 className="text-lg font-bold">Today's Stats</h2>
          {/* Add stats content here */}
        </Card>
        <Card>
          <h2 className="text-lg font-bold">Quick Actions</h2>
          {/* Add quick actions here */}
        </Card>
        <Card>
          <h2 className="text-lg font-bold">Weekly Overview</h2>
          {/* Add weekly overview content here */}
        </Card>
      </div>
    </div>
  );
}
