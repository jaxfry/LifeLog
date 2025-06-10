import { useMemo } from 'react';
import SearchBar from '../components/ui/SearchBar';
import FilterIcon from "../components/icons/FilterIcon";
import { ThemeSwitcher } from '../components/ui';

interface TimelineTopBarProps {
  formattedDate: string;
  activeFilter: string;
  onFilterChange: (filter: string) => void;
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
}

export default function TimelineTopBar({ 
  formattedDate, 
  activeFilter, 
  onFilterChange,
  searchQuery,
  onSearchQueryChange,
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
    <header className="px-6 py-4 border-b border-light bg-secondary shadow-card" role="banner">
      <div className="flex justify-between items-center mb-1">
        <h1 className="type-h2">
          {formattedDate}
        </h1>
        <div className="flex items-center gap-3" role="group" aria-label="Search and filter controls">
          <SearchBar 
            placeholder="Search activities..." 
            className="w-[300px]" 
            value={searchQuery}
            onChange={onSearchQueryChange}
          />
          <button 
            className="p-2 rounded-lg hover:bg-tertiary transition-hover focus-ring"
            aria-label="Open filter options"
          >
            <FilterIcon className="w-5 h-5 text-secondary" />
          </button>
          <ThemeSwitcher />
        </div>
      </div>
      <p className="type-caption mb-4">
        Track your digital footprint
      </p>
      
      {/* Filter tabs */}
      <nav aria-label="Activity filter categories">
        <div className="flex gap-2 overflow-x-auto hide-scrollbar">
          {filterOptions.map(option => (
            <button
              key={option.id}
              className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-hover focus-ring ${
                activeFilter === option.id 
                  ? 'bg-accent-gradient text-inverse shadow-card' 
                  : 'bg-tertiary text-primary hover:bg-tertiary/80 border border-light'
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
