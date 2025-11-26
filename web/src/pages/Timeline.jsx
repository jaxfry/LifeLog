import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { timelineAPI, chaptersAPI } from '../services/api';
import { formatDateTime, formatRelative, formatDuration } from '../utils/dateUtils';
import { Clock, Calendar, Search, Filter, RefreshCw, Layers, List } from 'lucide-react';
import DatePicker from '../components/DatePicker';

const Timeline = () => {
  const [page, setPage] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [viewMode, setViewMode] = useState('chapters'); // 'chapters' or 'detailed'
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const limit = 20;

  const timelineParams = useMemo(() => {
    const params = {
      offset: page * limit,
      limit
    };
    
    if (startDate) {
      params.start_date = startDate.toISOString();
    }
    if (endDate) {
      params.end_date = endDate.toISOString();
    }
    
    return params;
  }, [page, limit, startDate, endDate]);

  const { data: timeline = [], isLoading: isLoadingTimeline, isError: isErrorTimeline, error: errorTimeline, refetch: refetchTimeline } = useQuery({
    queryKey: ['timeline', page, limit, startDate, endDate],
    queryFn: () => timelineAPI.getTimeline(timelineParams),
    enabled: viewMode === 'detailed',
  });

  const { data: chapters = [], isLoading: isLoadingChapters, isError: isErrorChapters, error: errorChapters, refetch: refetchChapters } = useQuery({
    queryKey: ['chapters', page, limit, startDate, endDate],
    queryFn: () => chaptersAPI.getChapters(timelineParams),
    enabled: viewMode === 'chapters',
  });

  const isLoading = viewMode === 'detailed' ? isLoadingTimeline : isLoadingChapters;
  const isError = viewMode === 'detailed' ? isErrorTimeline : isErrorChapters;
  const error = viewMode === 'detailed' ? errorTimeline : errorChapters;
  const data = viewMode === 'detailed' ? timeline : chapters;
  const refetch = viewMode === 'detailed' ? refetchTimeline : refetchChapters;

  const filteredData = data.filter(item => 
    !searchTerm || 
    (item.activity || item.title)?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (item.notes || item.summary)?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-lg">
        <p className="font-semibold mb-2">Error loading timeline</p>
        <p className="text-sm">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Timeline</h1>
          <p className="text-gray-600">Your AI-generated activity timeline</p>
        </div>
        
        <div className="flex bg-gray-100 p-1 rounded-lg">
          <button
            onClick={() => setViewMode('chapters')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              viewMode === 'chapters' 
                ? 'bg-white text-blue-600 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <Layers size={18} />
            Chapters
          </button>
          <button
            onClick={() => setViewMode('detailed')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              viewMode === 'detailed' 
                ? 'bg-white text-blue-600 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <List size={18} />
            Detailed
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow-md p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <div className="md:col-span-2 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
            <input
              type="text"
              placeholder="Search timeline..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          
          <div>
            <DatePicker
              date={startDate}
              setDate={(date) => {
                setStartDate(date);
                setPage(0);
              }}
              placeholder="Start Date"
            />
          </div>
          
          <div>
            <DatePicker
              date={endDate}
              setDate={(date) => {
                setEndDate(date);
                setPage(0);
              }}
              placeholder="End Date"
            />
          </div>
        </div>
        
        <div className="flex gap-2">
          <button
            onClick={() => refetch()}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw size={20} />
            Refresh
          </button>
          <button
            onClick={() => {
              setSearchTerm('');
              setStartDate(null);
              setEndDate(null);
              setPage(0);
            }}
            className="btn-secondary"
          >
            Clear Filters
          </button>
        </div>
      </div>

      {/* Timeline Items */}
      {filteredData.length === 0 ? (
        <div className="card text-center py-12">
          <Calendar className="mx-auto mb-4 text-gray-400" size={48} />
          <p className="text-gray-600 text-lg">No entries found</p>
          <p className="text-gray-500 text-sm mt-2">Start collecting data to see your timeline</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredData.map((item) => (
            <div key={item.id} className="card hover:shadow-lg transition-shadow">
              <div className="flex items-start gap-4">
                <div className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center ${
                  viewMode === 'chapters' ? 'bg-purple-100' : 'bg-blue-100'
                }`}>
                  {viewMode === 'chapters' ? (
                    <Layers className="text-purple-600" size={24} />
                  ) : (
                    <Clock className="text-blue-600" size={24} />
                  )}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {viewMode === 'chapters' ? item.title : (item.activity || 'Activity')}
                      {item.end_time && (
                        <span className="ml-2 text-sm font-normal text-gray-500">
                          ({formatDuration(item.start_time, item.end_time)})
                        </span>
                      )}
                    </h3>
                    <span className="text-sm text-gray-500 whitespace-nowrap ml-4">
                      {formatRelative(item.start_time)}
                    </span>
                  </div>
                  
                  <p className="text-gray-700 mb-3 whitespace-pre-wrap">
                    {viewMode === 'chapters' ? item.summary : item.notes}
                  </p>
                  
                  <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
                    <span className="flex items-center gap-1">
                      <Calendar size={14} />
                      {formatDateTime(item.start_time, item.timezone)}
                    </span>
                    {item.end_time && (
                      <span>
                        → {formatDateTime(item.end_time, item.timezone)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {data.length >= limit && (
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
            disabled={data.length < limit}
            className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default Timeline;
