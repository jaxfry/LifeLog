import { useState } from 'react';
import { format } from 'date-fns';
import { DayPicker } from 'react-day-picker';
import 'react-day-picker/dist/style.css';
import { Calendar as CalendarIcon } from 'lucide-react';

const DatePicker = ({ date, setDate, placeholder }) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleDayClick = (selectedDate) => {
    setDate(selectedDate);
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-left"
        onClick={() => setIsOpen(!isOpen)}
      >
        <CalendarIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
        {date ? format(date, 'PPP') : <span className="text-gray-500">{placeholder}</span>}
      </button>
      {isOpen && (
        <div className="absolute z-10 mt-2 bg-white border border-gray-300 rounded-lg shadow-lg">
          <DayPicker
            mode="single"
            selected={date}
            onSelect={handleDayClick}
            initialFocus
          />
        </div>
      )}
    </div>
  );
};

export default DatePicker;
