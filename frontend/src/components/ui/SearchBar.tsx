import { useState } from 'react';

interface SearchBarProps {
  placeholder?: string;
  onSearch?: (query: string) => void;
  className?: string;
}

const SearchIcon = () => (
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    fill="none" 
    viewBox="0 0 24 24" 
    strokeWidth={1.5} 
    stroke="currentColor" 
    className="w-4 h-4 text-tertiary"
    aria-hidden="true"
  >
    <path 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" 
    />
  </svg>
);

const ClearIcon = () => (
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    fill="none" 
    viewBox="0 0 24 24" 
    strokeWidth={1.5} 
    stroke="currentColor" 
    className="w-4 h-4 text-tertiary hover:text-primary transition-colors"
    aria-hidden="true"
  >
    <path 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      d="M6 18 18 6M6 6l12 12" 
    />
  </svg>
);

export default function SearchBar({ 
  placeholder = "Search activities...", 
  onSearch,
  className = "",
}: SearchBarProps) {
  const [query, setQuery] = useState('');
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSearch && query.trim()) {
      onSearch(query.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className={`relative ${className}`} role="search" aria-label="Search activities">
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" aria-hidden="true">
          <SearchIcon />
        </div>
        <input
          type="search"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="block w-full rounded-lg pl-10 pr-10 py-2 border border-light 
                   text-sm placeholder:text-tertiary 
                   bg-surface-primary text-primary 
                   focus:outline-none focus:ring-2 focus:ring-primary-600 focus:border-focus"
          aria-label={placeholder}
        />
        {query && (
          <button 
            type="button" 
            className="absolute inset-y-0 right-0 pr-3 flex items-center hover:bg-surface-secondary rounded-r-lg transition-colors"
            onClick={() => setQuery('')}
            aria-label="Clear search query"
          >
            <ClearIcon />
          </button>
        )}
      </div>
    </form>
  );
}
