import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { timelineAPI } from '../services/api';
import { formatDateTime, formatRelative } from '../utils/dateUtils';
import { Clock, Calendar, Search, Filter, RefreshCw } from 'lucide-react';

const Timeline = () => {
  const [page, setPage] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const limit = 20;

  const { data: timeline = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: ['timeline', page, limit],
    queryFn: () => timelineAPI.getTimeline({ 
      offset: page * limit, 
      limit 
    }),
  });

  const filteredTimeline = timeline.filter(item => 
    !searchTerm || 
    item.summary?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.title?.toLowerCase().includes(searchTerm.toLowerCase())
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
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Timeline</h1>
        <p className="text-gray-600">Your AI-generated activity timeline</p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow-md p-4 mb-6">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
            <input
              type="text"
              placeholder="Search timeline..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          
          <button
            onClick={() => refetch()}
            className="btn-secondary flex items-center gap-2 whitespace-nowrap"
          >
            <RefreshCw size={20} />
            Refresh
          </button>
        </div>
      </div>

      {/* Timeline Items */}
      {filteredTimeline.length === 0 ? (
        <div className="card text-center py-12">
          <Calendar className="mx-auto mb-4 text-gray-400" size={48} />
          <p className="text-gray-600 text-lg">No timeline entries found</p>
          <p className="text-gray-500 text-sm mt-2">Start collecting data to see your timeline</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredTimeline.map((item) => (
            <div key={item.id} className="card hover:shadow-lg transition-shadow">
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0 w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                  <Clock className="text-blue-600" size={24} />
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {item.title || 'Activity'}
                    </h3>
                    <span className="text-sm text-gray-500 whitespace-nowrap ml-4">
                      {formatRelative(item.start_time)}
                    </span>
                  </div>
                  
                  <p className="text-gray-700 mb-3 whitespace-pre-wrap">
                    {item.summary}
                  </p>
                  
                  <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
                    <span className="flex items-center gap-1">
                      <Calendar size={14} />
                      {formatDateTime(item.start_time)}
                    </span>
                    {item.end_time && (
                      <span>
                        → {formatDateTime(item.end_time)}
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
      {timeline.length >= limit && (
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
            disabled={timeline.length < limit}
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
