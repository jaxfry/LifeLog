import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { sessionsAPI, eventsAPI } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { Activity, Clock, Calendar, TrendingUp } from 'lucide-react';

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

const Analytics = () => {
  const [timeRange, setTimeRange] = useState(7); // days

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ['sessions', { limit: 100 }],
    queryFn: () => sessionsAPI.getSessions({ limit: 100 }),
  });

  const { data: events = [], isLoading: eventsLoading } = useQuery({
    queryKey: ['events', { limit: 500 }],
    queryFn: () => eventsAPI.getEvents({ limit: 500 }),
  });

  // Process data for analytics
  const sessionsByDay = sessions.reduce((acc, session) => {
    if (!session.start_time) return acc;
    const date = new Date(session.start_time).toLocaleDateString();
    acc[date] = (acc[date] || 0) + 1;
    return acc;
  }, {});

  const chartData = Object.entries(sessionsByDay)
    .sort((a, b) => new Date(a[0]) - new Date(b[0]))
    .slice(-timeRange)
    .map(([date, count]) => ({
      date: new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      sessions: count,
    }));

  // Session status distribution
  const statusData = sessions.reduce((acc, session) => {
    const status = session.status || 'unknown';
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});

  const pieData = Object.entries(statusData).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
  }));

  // Calculate stats
  const totalSessions = sessions.length;
  const totalEvents = events.length;
  const avgSessionsPerDay = totalSessions > 0 ? (totalSessions / Math.min(timeRange, 30)).toFixed(1) : 0;

  const isLoading = sessionsLoading || eventsLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Analytics</h1>
        <p className="text-gray-600">Insights into your activity patterns</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <Activity className="text-blue-600" size={20} />
            </div>
            <p className="text-sm text-gray-600">Total Sessions</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{totalSessions}</p>
        </div>

        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <Calendar className="text-green-600" size={20} />
            </div>
            <p className="text-sm text-gray-600">Total Events</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{totalEvents}</p>
        </div>

        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <TrendingUp className="text-purple-600" size={20} />
            </div>
            <p className="text-sm text-gray-600">Avg Sessions/Day</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{avgSessionsPerDay}</p>
        </div>

        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
              <Clock className="text-orange-600" size={20} />
            </div>
            <p className="text-sm text-gray-600">Time Range</p>
          </div>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sessions Over Time */}
        <div className="card">
          <h3 className="text-xl font-semibold text-gray-900 mb-4">Sessions Over Time</h3>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="sessions" fill="#3B82F6" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-500">
              No data available
            </div>
          )}
        </div>

        {/* Session Status Distribution */}
        <div className="card">
          <h3 className="text-xl font-semibold text-gray-900 mb-4">Session Status</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-500">
              No data available
            </div>
          )}
        </div>
      </div>

      {/* Recent Sessions */}
      <div className="card mt-6">
        <h3 className="text-xl font-semibold text-gray-900 mb-4">Recent Sessions</h3>
        {sessions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Start Time
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Events
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {sessions.slice(0, 10).map((session) => (
                  <tr key={session.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {new Date(session.start_time).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                        session.status === 'complete' ? 'bg-green-100 text-green-800' :
                        session.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {session.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {session.event_count || 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 text-center py-8">No sessions found</p>
        )}
      </div>
    </div>
  );
};

export default Analytics;
