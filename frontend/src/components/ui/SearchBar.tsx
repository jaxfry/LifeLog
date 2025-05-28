import { useState } from 'react';

interface SearchBarProps {
  placeholder?: string;
  onSearch?: (query: string) => void;
  className?: string;
  style?: React.CSSProperties;
}

export default function SearchBar({ 
  placeholder = "Search activities...", 
  onSearch,
  className = "",
  style
}: SearchBarProps) {
  const [query, setQuery] = useState('');
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSearch && query.trim()) {
      onSearch(query.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className={`relative ${className}`} style={style}>
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <svg 
            xmlns="http://www.w3.org/2000/svg" 
            fill="none" 
            viewBox="0 0 24 24" 
            strokeWidth={1.5} 
            stroke="currentColor" 
            className="w-4 h-4 text-gray-500"
          >
            <path 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" 
            />
          </svg>
        </div>
        <input
          type="text"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="block w-full rounded-lg pl-10 pr-3 py-2 border border-gray-200 
                   text-sm placeholder:text-gray-500 text-gray-900
                   focus:outline-none focus:ring-2 focus:ring-gray-900"
          style={{ backgroundColor: '#0F101D', color: 'white' }}
        />
        <button 
          type="button" 
          className="absolute inset-y-0 right-0 pr-3 flex items-center"
          onClick={() => setQuery('')}
          style={{ display: query ? 'flex' : 'none' }}
        >
          <svg 
            xmlns="http://www.w3.org/2000/svg" 
            fill="none" 
            viewBox="0 0 24 24" 
            strokeWidth={1.5} 
            stroke="currentColor" 
            className="w-4 h-4 text-gray-500 hover:text-gray-700"
          >
            <path 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              d="M6 18 18 6M6 6l12 12" 
            />
          </svg>
        </button>
      </div>
    </form>
  );
}
