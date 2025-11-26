import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { eventsAPI, sessionsAPI, logsAPI } from '../services/api';
import { Database, Filter, Search, Calendar, Clock, RefreshCw } from 'lucide-react';
import { formatDateTime } from '../utils/dateUtils';
import DatePicker from '../components/DatePicker';

const DATA_TYPES = [
  { value: 'events', label: 'Events', description: 'Normalized activity events' },
  { value: 'sessions', label: 'Sessions', description: 'Grouped activity sessions' },
  { value: 'logs', label: 'Raw Logs', description: 'Original data from collectors' },
];

const DataExplorer = () => {
  const [dataType, setDataType] = useState('events');
  const [page, setPage] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const limit = 20;

  // Build query params
  const params = {
    offset: page * limit,
    limit,
  };

  if (startDate) {
    params.start_date = startDate.toISOString();
  }
  if (endDate) {
    params.end_date = endDate.toISOString();
  }
  if (statusFilter && dataType === 'sessions') {
    params.status = statusFilter;
  }

  // Fetch data based on type
  const { data: events = [], isLoading: eventsLoading, refetch: refetchEvents } = useQuery({
    queryKey: ['data-explorer-events', page, limit, startDate, endDate],
    queryFn: () => eventsAPI.getEvents(params),
    enabled: dataType === 'events',
  });

  const { data: sessions = [], isLoading: sessionsLoading, refetch: refetchSessions } = useQuery({
    queryKey: ['data-explorer-sessions', page, limit, startDate, endDate, statusFilter],
    queryFn: () => sessionsAPI.getSessions(params),
    enabled: dataType === 'sessions',
  });

  const { data: logs = [], isLoading: logsLoading, refetch: refetchLogs } = useQuery({
    queryKey: ['data-explorer-logs', page, limit, startDate, endDate],
    queryFn: () => logsAPI.getLogs(params),
    enabled: dataType === 'logs',
  });

  const data = dataType === 'events' ? events : dataType === 'sessions' ? sessions : logs;
  const isLoading = eventsLoading || sessionsLoading || logsLoading;
  const refetch = dataType === 'events' ? refetchEvents : dataType === 'sessions' ? refetchSessions : refetchLogs;

  // Filter by search term (client-side for demo)
  // Note: For large datasets, consider implementing server-side search
  const filteredData = data.filter(item => {
    if (!searchTerm) return true;
    const searchLower = searchTerm.toLowerCase();
    const itemStr = JSON.stringify(item).toLowerCase();
    return itemStr.includes(searchLower);
  });

  const handleReset = () => {
    setSearchTerm('');
    setStartDate(null);
    setEndDate(null);
    setStatusFilter('');
    setPage(0);
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Data Explorer</h1>
        <p className="text-gray-600">Browse and search your collected data</p>
      </div>

      {/* Data Type Selector */}
      <div className="card mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Data Type</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {DATA_TYPES.map(type => (
            <button
              key={type.value}
              onClick={() => {
                setDataType(type.value);
                setPage(0);
              }}
              className={`p-4 rounded-lg border-2 transition-all text-left ${
                dataType === type.value
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Database size={20} className={dataType === type.value ? 'text-blue-600' : 'text-gray-600'} />
                <span className={`font-semibold ${dataType === type.value ? 'text-blue-900' : 'text-gray-900'}`}>
                  {type.label}
                </span>
              </div>
              <p className="text-sm text-gray-600">{type.description}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Filter size={20} className="text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-700">Filters</h3>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          {/* Search */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Search
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
              <input
                type="text"
                placeholder="Search data..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Start Date */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Start Date
            </label>
            <DatePicker
              date={startDate}
              setDate={(date) => {
                setStartDate(date);
                setPage(0);
              }}
              placeholder="Start Date"
            />
          </div>

          {/* End Date */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              End Date
            </label>
            <DatePicker
              date={endDate}
              setDate={(date) => {
                setEndDate(date);
                setPage(0);
              }}
              placeholder="End Date"
            />
          </div>

          {/* Status Filter (for sessions only) */}
          {dataType === 'sessions' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Status
              </label>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(0);
                }}
                className="input-field"
              >
                <option value="">All</option>
                <option value="pending">Pending</option>
                <option value="processed">Processed</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <button onClick={() => refetch()} className="btn-secondary flex items-center gap-2">
            <RefreshCw size={18} />
            Refresh
          </button>
          <button onClick={handleReset} className="btn-secondary">
            Reset Filters
          </button>
        </div>
      </div>

      {/* Data Display */}
      {isLoading ? (
        <div className="flex items-center justify-center min-h-96">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      ) : filteredData.length === 0 ? (
        <div className="card text-center py-12">
          <Database className="mx-auto mb-4 text-gray-400" size={48} />
          <p className="text-gray-600 text-lg">No data found</p>
          <p className="text-gray-500 text-sm mt-2">Try adjusting your filters</p>
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {filteredData.map((item) => (
              <div key={item.id} className="card hover:shadow-lg transition-shadow">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    {/* Type-specific rendering */}
                    {dataType === 'events' && (
                      <>
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-lg font-semibold text-gray-900">
                            {item.type || 'Event'}
                          </h3>
                          {item.source_log_id && (
                            <span className="text-xs text-gray-500 font-mono">
                              Log: {item.source_log_id.substring(0, 8)}...
                            </span>
                          )}
                        </div>
                      </>
                    )}

                    {dataType === 'sessions' && (
                      <>
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-lg font-semibold text-gray-900">Session</h3>
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            item.status === 'processed' ? 'bg-green-100 text-green-700' :
                            item.status === 'failed' ? 'bg-red-100 text-red-700' :
                            'bg-yellow-100 text-yellow-700'
                          }`}>
                            {item.status}
                          </span>
                        </div>
                      </>
                    )}

                    {dataType === 'logs' && (
                      <>
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-lg font-semibold text-gray-900">Raw Log</h3>
                          {item.extension_id && (
                            <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">
                              {item.extension_id}
                            </span>
                          )}
                        </div>
                      </>
                    )}

                    {/* Timestamps */}
                    <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600 mb-3">
                      {item.created_at && (
                        <span className="flex items-center gap-1">
                          <Clock size={14} />
                          {formatDateTime(item.created_at)}
                        </span>
                      )}
                      {item.start_time && (
                        <span className="flex items-center gap-1">
                          <Calendar size={14} />
                          {formatDateTime(item.start_time)}
                          {item.end_time && ` → ${formatDateTime(item.end_time)}`}
                        </span>
                      )}
                      {item.received_at && (
                        <span className="flex items-center gap-1">
                          <Clock size={14} />
                          Received: {formatDateTime(item.received_at)}
                        </span>
                      )}
                    </div>

                    {/* Data preview */}
                    <div className="bg-gray-50 rounded-lg p-3 overflow-x-auto">
                      <pre className="text-xs text-gray-700">
                        {JSON.stringify(item.data || item.payload || item, null, 2).substring(0, 500)}
                        {JSON.stringify(item.data || item.payload || item, null, 2).length > 500 && '...'}
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex justify-center gap-4 mt-8">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="flex items-center text-gray-600">
              Page {page + 1}
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={filteredData.length < limit}
              className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default DataExplorer;
