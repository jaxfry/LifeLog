import { useState } from 'react';

interface SearchBarProps {
  placeholder?: string;
  onSearch?: (query: string) => void;
  onChange?: (query: string) => void;
  value?: string;
  className?: string;
}

const SearchIcon = () => (
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    fill="none" 
    viewBox="0 0 24 24" 
    strokeWidth={1.5} 
    stroke="currentColor" 
    className="w-4 h-4 text-secondary"
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
    className="w-4 h-4 text-secondary hover:text-primary transition-hover"
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
  onChange,
  value,
  className = "",
}: SearchBarProps) {
  const [internalQuery, setInternalQuery] = useState('');
  const query = value !== undefined ? value : internalQuery;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSearch && query.trim()) {
      onSearch(query.trim());
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (value === undefined) {
      setInternalQuery(e.target.value);
    }
    if (onChange) onChange(e.target.value);
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
          onChange={handleChange}
          className="block w-full rounded-lg pl-10 pr-10 py-2.5 border border-light 
                   text-sm placeholder:text-secondary 
                   bg-tertiary text-primary 
                   focus-ring transition-focus
                   hover:bg-tertiary/80"
          aria-label={placeholder}
        />
        {query && (
          <button 
            type="button" 
            className="absolute inset-y-0 right-0 pr-3 flex items-center hover:bg-tertiary rounded-r-lg transition-hover focus-ring"
            onClick={() => { if (value === undefined) setInternalQuery(''); if (onChange) onChange(''); }}
            aria-label="Clear search query"
          >
            <ClearIcon />
          </button>
        )}
      </div>
    </form>
  );
}
