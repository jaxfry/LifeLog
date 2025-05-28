import { useMemo } from 'react';
import SearchBar from './ui/SearchBar';

interface TimelineTopBarProps {
  formattedDate: string;
  activeFilter: string;
  onFilterChange: (filter: string) => void;
}

export default function TimelineTopBar({ 
  formattedDate, 
  activeFilter, 
  onFilterChange 
}: TimelineTopBarProps) {
  // Generate filter options from hardcoded categories
  const filterOptions = useMemo(() => {
    const categories = ["All", "Work", "Creative", "Communication", "Entertainment", "Productivity"];
    return categories.map(category => ({
      id: category,
      label: category
    }));
  }, []); // Dependency array is empty as categories are static

  return (
    <div className="px-6 py-4 border-b border-gray-100" style={{ backgroundColor: '#0F101D' }}>
      <div className="flex justify-between items-center mb-1">
        <div className="text-3xl font-bold text-white">
          {formattedDate}
        </div>
        <div className="flex items-center gap-2">
          <SearchBar placeholder="Search activities..." className="w-[300px]" />
          <button className="p-2 rounded hover:bg-gray-100">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-gray-500">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75" />
            </svg>
          </button>
        </div>
      </div>
      <div className="text-sm text-gray-400 mb-2">
        Track your digital footprint
      </div>
      
      {/* Filter tabs */}
      <div className="flex gap-2 overflow-x-auto hide-scrollbar">
        {filterOptions.map(option => (
          <button
            key={option.id}
            className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap ${
              activeFilter === option.id 
                ? 'bg-indigo-600 text-white' 
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            onClick={() => onFilterChange(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
