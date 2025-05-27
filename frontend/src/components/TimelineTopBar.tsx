import SearchBar from './ui/SearchBar';

interface TimelineTopBarProps {
  formattedDate: string;
}

export default function TimelineTopBar({ formattedDate }: TimelineTopBarProps) {
  return (
    <div className="px-6 py-4 border-b border-gray-100" style={{ backgroundColor: '#020412' }}>
      <div className="flex justify-between items-center mb-1">
        <div className="text-2xl font-semibold text-gray-800">
          {formattedDate}
        </div>
        <div className="flex items-center gap-2">
          <button className="p-2 rounded hover:bg-gray-100">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-gray-500">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75" />
            </svg>
          </button>
        </div>
      </div>
      <div className="flex justify-between items-center">
        <div className="text-sm text-gray-500">
          Track your digital footprint
        </div>
        <SearchBar placeholder="Search activities..." className="w-64" />
      </div>
    </div>
  );
}
