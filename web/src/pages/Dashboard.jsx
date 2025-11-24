import { useQuery } from '@tanstack/react-query';
import { analyticsAPI, summariesAPI } from '../services/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Activity, Database, Cpu, HardDrive, TrendingUp, Calendar, Sparkles } from 'lucide-react';
import { formatDate } from '../utils/dateUtils';

const Dashboard = () => {
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['dashboard-metrics'],
    queryFn: () => analyticsAPI.getDashboardMetrics(),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const { data: summaries = [], isLoading: summariesLoading } = useQuery({
    queryKey: ['recent-summaries'],
    queryFn: () => summariesAPI.getSummaries({ limit: 1 }),
  });

  const isLoading = metricsLoading || summariesLoading;

  // Format chart data
  const chartData = metrics?.activity_volume?.map(item => ({
    date: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    activities: item.count,
  })) || [];

  const latestSummary = summaries[0];

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
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Dashboard</h1>
        <p className="text-gray-600">Your LifeLog overview and insights</p>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-lg transition-shadow">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
              <Activity className="text-blue-600" size={24} />
            </div>
            <div>
              <p className="text-sm text-gray-600">Total Events</p>
              <p className="text-2xl font-bold text-gray-900">{metrics?.total_events?.toLocaleString() || 0}</p>
            </div>
          </div>
        </div>

        <div className="card hover:shadow-lg transition-shadow">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
              <Database className="text-green-600" size={24} />
            </div>
            <div>
              <p className="text-sm text-gray-600">Active Collectors</p>
              <p className="text-2xl font-bold text-gray-900">{metrics?.active_collectors || 0}</p>
            </div>
          </div>
        </div>

        <div className="card hover:shadow-lg transition-shadow">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center">
              <Cpu className="text-purple-600" size={24} />
            </div>
            <div>
              <p className="text-sm text-gray-600">AI Processing</p>
              <p className="text-2xl font-bold text-gray-900">{metrics?.ai_processing?.toLocaleString() || 0}</p>
            </div>
          </div>
        </div>

        <div className="card hover:shadow-lg transition-shadow">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 bg-orange-100 rounded-lg flex items-center justify-center">
              <HardDrive className="text-orange-600" size={24} />
            </div>
            <div>
              <p className="text-sm text-gray-600">Storage Used</p>
              <p className="text-2xl font-bold text-gray-900">{metrics?.storage_used_mb?.toFixed(1) || 0} MB</p>
            </div>
          </div>
        </div>
      </div>

      {/* Activity Volume Chart */}
      <div className="card mb-8">
        <div className="flex items-center gap-3 mb-6">
          <TrendingUp className="text-blue-600" size={24} />
          <h2 className="text-xl font-semibold text-gray-900">Activity Volume (Last 7 Days)</h2>
        </div>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="activities" 
                name="Activities" 
                stroke="#3B82F6" 
                strokeWidth={2}
                dot={{ fill: '#3B82F6', r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-64 text-gray-500">
            No activity data available
          </div>
        )}
      </div>

      {/* Daily Brief */}
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
            <Sparkles className="text-white" size={20} />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Daily Brief</h2>
            <p className="text-sm text-gray-500">AI-generated insights from your latest day</p>
          </div>
        </div>

        {latestSummary ? (
          <div className="mt-4">
            <div className="flex items-center gap-2 mb-3">
              <Calendar className="text-gray-400" size={16} />
              <span className="text-sm font-medium text-gray-700">
                {formatDate(new Date(latestSummary.date), 'EEEE, MMMM d, yyyy')}
              </span>
            </div>
            
            <div className="prose prose-sm max-w-none">
              <p className="text-gray-700 whitespace-pre-wrap">{latestSummary.summary_text}</p>
            </div>

            {latestSummary.key_activities && latestSummary.key_activities.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <h3 className="text-sm font-semibold text-gray-900 mb-2">Key Activities</h3>
                <div className="flex flex-wrap gap-2">
                  {latestSummary.key_activities.map((activity, idx) => (
                    <span 
                      key={idx}
                      className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm"
                    >
                      {activity}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(latestSummary.productivity_score !== null || latestSummary.mood) && (
              <div className="mt-4 pt-4 border-t border-gray-200 flex gap-6">
                {latestSummary.productivity_score !== null && (
                  <div>
                    <span className="text-sm text-gray-600">Productivity Score: </span>
                    <span className="text-lg font-semibold text-gray-900">{latestSummary.productivity_score}/10</span>
                  </div>
                )}
                {latestSummary.mood && (
                  <div>
                    <span className="text-sm text-gray-600">Mood: </span>
                    <span className="text-lg font-semibold text-gray-900 capitalize">{latestSummary.mood}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <Sparkles className="mx-auto mb-3 text-gray-400" size={32} />
            <p>No daily brief available yet</p>
            <p className="text-sm mt-1">Daily summaries are generated automatically</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
