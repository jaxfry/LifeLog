import { useMemo } from 'react';
import SearchBar from './ui/SearchBar';
import FilterIcon from './icons/FilterIcon';

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
    <header className="px-6 py-4 border-b border-light bg-surface-primary" role="banner">
      <div className="flex justify-between items-center mb-1">
        <h1 className="text-3xl font-bold text-primary">
          {formattedDate}
        </h1>
        <div className="flex items-center gap-2" role="group" aria-label="Search and filter controls">
          <SearchBar placeholder="Search activities..." className="w-[300px]" />
          <button 
            className="p-2 rounded hover:bg-surface-secondary transition-colors"
            aria-label="Open filter options"
          >
            <FilterIcon className="w-5 h-5 text-secondary" />
          </button>
        </div>
      </div>
      <p className="text-sm text-secondary mb-2">
        Track your digital footprint
      </p>
      
      {/* Filter tabs */}
      <nav aria-label="Activity filter categories">
        <div className="flex gap-2 overflow-x-auto hide-scrollbar">
          {filterOptions.map(option => (
            <button
              key={option.id}
              className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap transition-colors ${
                activeFilter === option.id 
                  ? 'bg-primary-600 text-on-primary' 
                  : 'bg-surface-light text-on-surface-light hover:bg-surface-tertiary'
              }`}
              onClick={() => onFilterChange(option.id)}
              aria-pressed={activeFilter === option.id}
              aria-label={`Filter by ${option.label}`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </nav>
    </header>
  );
}
