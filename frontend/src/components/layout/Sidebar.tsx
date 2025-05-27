import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function Sidebar() {
  const [currentMonth, setCurrentMonth] = useState('May 2025');
  const navigate = useNavigate();
  
  // Days in current month view
  const daysInMonth = Array.from({ length: 31 }, (_, i) => i + 1);
  
  // Dummy active day (highlighted in calendar)
  const activeDay = 24;
  
  // Calendar header days
  const weekdays = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  return (
    <aside className="w-72 flex-shrink-0 bg-gray-900 text-white flex flex-col h-screen">
      <div className="p-5 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"></path>
          </svg>
        </div>
        <h1 className="text-xl font-semibold">TimeFlow</h1>
      </div>
      
      <p className="text-gray-400 text-sm px-5">Your intelligent activity journal</p>
      
      <div className="mt-6 px-5">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg">{currentMonth}</h2>
          <div className="flex gap-2">
            <button 
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-800"
              onClick={() => setCurrentMonth('April 2025')}
            >
              ‹
            </button>
            <button 
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-800"
              onClick={() => setCurrentMonth('June 2025')}
            >
              ›
            </button>
          </div>
        </div>
        
        {/* Calendar */}
        <div className="grid grid-cols-7 gap-y-2 text-center">
          {/* Weekday headers */}
          {weekdays.map(day => (
            <div key={day} className="text-gray-500 text-xs">{day}</div>
          ))}
          
          {/* Empty slots for days before month start (adjust as needed) */}
          {[...Array(3)].map((_, i) => (
            <div key={`empty-${i}`} className="h-6"></div>
          ))}
          
          {/* Days */}
          {daysInMonth.map(day => (
            <button
              key={day}
              className={`h-7 w-7 rounded-full flex items-center justify-center mx-auto text-sm
                ${day === activeDay 
                  ? 'bg-indigo-600 text-white' 
                  : 'hover:bg-gray-800'}`}
              onClick={() => navigate(`/day/2025-05-${day.toString().padStart(2, '0')}`)}
            >
              {day}
            </button>
          ))}
        </div>
      </div>
      
      <div className="mt-auto">
        <div className="p-5">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 flex items-center justify-center rounded-full bg-green-500">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-white">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"></path>
              </svg>
            </div>
            <p className="text-sm text-gray-300">Today's Focus</p>
          </div>
          <div className="mt-2 text-2xl font-bold">7h 30m</div>
        </div>
        
        <div className="p-5 border-t border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 flex items-center justify-center text-amber-400">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                <path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
              </svg>
            </div>
            <p className="text-sm text-gray-300">Break Time</p>
          </div>
          <div className="mt-2 text-2xl font-bold">45m</div>
        </div>
      </div>
    </aside>
  );
}
