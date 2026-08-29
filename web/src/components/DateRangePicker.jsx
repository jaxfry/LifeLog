import { useState } from 'react';
import { Calendar, X } from 'lucide-react';
import { format, subDays, startOfMonth, endOfMonth, isAfter, parseISO } from 'date-fns';

const DateRangePicker = ({ startDate, endDate, onChange, className = '' }) => {
    const [localStart, setLocalStart] = useState(startDate || '');
    const [localEnd, setLocalEnd] = useState(endDate || '');
    const [error, setError] = useState('');

    const handleDateChange = (type, value) => {
        setError('');
        let newStart = type === 'start' ? value : localStart;
        let newEnd = type === 'end' ? value : localEnd;

        // Basic validation logic
        if (newStart && newEnd) {
            if (isAfter(parseISO(newStart), parseISO(newEnd))) {
                // If start is after end, we can either error or auto-correct.
                // Let's auto-correct for a smoother experience if the user is just clicking around,
                // but if they are typing, maybe we should just warn.
                // For now, let's just set the error and not propagate the change if it's invalid?
                // Actually, the user requirement was "don't allow invalid ranges".
                // Let's auto-adjust the other date if it makes sense, or just show error.

                if (type === 'start') {
                    // If they moved start after end, clear end or move end to start?
                    // Let's just show an error and not trigger onChange for the parent yet
                    setError('Start date cannot be after end date');
                    setLocalStart(value);
                    return;
                } else {
                    setError('End date cannot be before start date');
                    setLocalEnd(value);
                    return;
                }
            }
        }

        if (type === 'start') setLocalStart(value);
        else setLocalEnd(value);

        // Propagate to parent if valid (or if one is empty, which is valid state for "filtering")
        onChange({ start: newStart, end: newEnd });
    };

    const applyPreset = (preset) => {
        const today = new Date();
        let start, end;

        switch (preset) {
            case 'last7':
                end = today;
                start = subDays(today, 6);
                break;
            case 'last30':
                end = today;
                start = subDays(today, 29);
                break;
            case 'thisMonth':
                start = startOfMonth(today);
                end = endOfMonth(today); // or today? usually "this month" implies the whole month range
                break;
            case 'clear':
                start = '';
                end = '';
                break;
            default:
                return;
        }

        const startStr = start ? format(start, 'yyyy-MM-dd') : '';
        const endStr = end ? format(end, 'yyyy-MM-dd') : '';

        setLocalStart(startStr);
        setLocalEnd(endStr);
        setError('');
        onChange({ start: startStr, end: endStr });
    };

    return (
        <div className={`flex flex-col gap-2 ${className}`}>
            <div className="flex flex-wrap items-center gap-2">
                <div className="relative flex items-center">
                    <Calendar className="absolute left-3 text-gray-400" size={16} />
                    <input
                        type="date"
                        value={localStart}
                        max={localEnd || undefined}
                        onChange={(e) => handleDateChange('start', e.target.value)}
                        className={`pl-9 pr-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none ${error ? 'border-red-300 focus:ring-red-200' : 'border-gray-300'
                            }`}
                        placeholder="Start Date"
                    />
                </div>
                <span className="text-gray-400">to</span>
                <div className="relative flex items-center">
                    <Calendar className="absolute left-3 text-gray-400" size={16} />
                    <input
                        type="date"
                        value={localEnd}
                        min={localStart || undefined}
                        onChange={(e) => handleDateChange('end', e.target.value)}
                        className={`pl-9 pr-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none ${error ? 'border-red-300 focus:ring-red-200' : 'border-gray-300'
                            }`}
                        placeholder="End Date"
                    />
                </div>

                {(localStart || localEnd) && (
                    <button
                        onClick={() => applyPreset('clear')}
                        className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
                        title="Clear dates"
                    >
                        <X size={16} />
                    </button>
                )}
            </div>

            {error && <p className="text-xs text-red-500 ml-1">{error}</p>}

            <div className="flex gap-2 overflow-x-auto pb-1">
                <button
                    onClick={() => applyPreset('last7')}
                    className="px-3 py-1 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-full transition-colors whitespace-nowrap"
                >
                    Last 7 Days
                </button>
                <button
                    onClick={() => applyPreset('last30')}
                    className="px-3 py-1 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-full transition-colors whitespace-nowrap"
                >
                    Last 30 Days
                </button>
                <button
                    onClick={() => applyPreset('thisMonth')}
                    className="px-3 py-1 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-full transition-colors whitespace-nowrap"
                >
                    This Month
                </button>
            </div>
        </div>
    );
};

export default DateRangePicker;
