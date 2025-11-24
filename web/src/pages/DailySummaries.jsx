import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dailySummaryAPI } from '../services/api';
import { formatDate, formatDateForAPI } from '../utils/dateUtils';
import { Calendar, Star, Smile, TrendingUp, ChevronLeft, ChevronRight } from 'lucide-react';

const DailySummaries = () => {
  const [selectedDate, setSelectedDate] = useState(new Date());
  const queryClient = useQueryClient();

  const dateStr = formatDateForAPI(selectedDate);

  const { data: summary, isLoading, isError } = useQuery({
    queryKey: ['dailySummary', dateStr],
    queryFn: () => dailySummaryAPI.generateSummary(dateStr),
    retry: false,
  });

  const generateMutation = useMutation({
    mutationFn: (date) => dailySummaryAPI.generateSummary(date),
    onSuccess: () => {
      queryClient.invalidateQueries(['dailySummary', dateStr]);
    },
  });

  const handlePreviousDay = () => {
    const newDate = new Date(selectedDate);
    newDate.setDate(newDate.getDate() - 1);
    setSelectedDate(newDate);
  };

  const handleNextDay = () => {
    const newDate = new Date(selectedDate);
    newDate.setDate(newDate.getDate() + 1);
    setSelectedDate(newDate);
  };

  const handleGenerate = () => {
    generateMutation.mutate(dateStr);
  };

  const getMoodEmoji = (mood) => {
    const moodMap = {
      happy: '😊',
      neutral: '😐',
      sad: '😢',
      excited: '🤗',
      tired: '😴',
      productive: '💪',
    };
    return moodMap[mood?.toLowerCase()] || '😊';
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Daily Summaries</h1>
        <p className="text-gray-600">Review your daily activities and insights</p>
      </div>

      {/* Date Selector */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <div className="flex items-center justify-between">
          <button
            onClick={handlePreviousDay}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ChevronLeft size={24} />
          </button>
          
          <div className="flex items-center gap-3">
            <Calendar className="text-blue-600" size={24} />
            <h2 className="text-2xl font-semibold text-gray-900">
              {formatDate(selectedDate, 'EEEE, MMMM d, yyyy')}
            </h2>
          </div>
          
          <button
            onClick={handleNextDay}
            disabled={formatDateForAPI(selectedDate) >= formatDateForAPI(new Date())}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight size={24} />
          </button>
        </div>
      </div>

      {/* Summary Content */}
      {isLoading ? (
        <div className="flex items-center justify-center min-h-96">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      ) : isError || !summary ? (
        <div className="card text-center py-12">
          <Calendar className="mx-auto mb-4 text-gray-400" size={48} />
          <p className="text-gray-600 text-lg mb-4">No summary available for this date</p>
          <button
            onClick={handleGenerate}
            disabled={generateMutation.isPending}
            className="btn-primary"
          >
            {generateMutation.isPending ? 'Generating...' : 'Generate Summary'}
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Summary Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {summary.productivity_score !== null && (
              <div className="card">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                    <TrendingUp className="text-green-600" size={20} />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Productivity</p>
                    <p className="text-2xl font-bold text-gray-900">{summary.productivity_score}/10</p>
                  </div>
                </div>
              </div>
            )}
            
            {summary.mood && (
              <div className="card">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center text-2xl">
                    {getMoodEmoji(summary.mood)}
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Mood</p>
                    <p className="text-xl font-semibold text-gray-900 capitalize">{summary.mood}</p>
                  </div>
                </div>
              </div>
            )}
            
            {summary.key_activities && summary.key_activities.length > 0 && (
              <div className="card">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                    <Star className="text-blue-600" size={20} />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Activities</p>
                    <p className="text-2xl font-bold text-gray-900">{summary.key_activities.length}</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Summary Text */}
          <div className="card">
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Daily Summary</h3>
            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
              {summary.summary_text}
            </p>
          </div>

          {/* Key Activities */}
          {summary.key_activities && summary.key_activities.length > 0 && (
            <div className="card">
              <h3 className="text-xl font-semibold text-gray-900 mb-4">Key Activities</h3>
              <ul className="space-y-2">
                {summary.key_activities.map((activity, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-sm font-medium text-blue-600">
                      {index + 1}
                    </span>
                    <span className="text-gray-700">{activity}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Regenerate Button */}
          <div className="text-center">
            <button
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
              className="btn-secondary"
            >
              {generateMutation.isPending ? 'Regenerating...' : 'Regenerate Summary'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default DailySummaries;
