import { format, parseISO, formatDistanceToNow, startOfDay, endOfDay } from 'date-fns';

export const formatDate = (date, formatStr = 'PPP') => {
  if (!date) return '';
  let parsedDate = typeof date === 'string' ? parseISO(date) : date;
  
  // Handle naive UTC strings from server by treating them as UTC
  if (typeof date === 'string') {
    // A logical date is a calendar value, not an instant. Keep it at local
    // midnight so users west of UTC do not see the previous day.
    if (/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      parsedDate = parseISO(date);
    }
    // Check if it has a timezone offset (Z, +HH:mm, -HH:mm, +HHmm, -HHmm)
    const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(date);
    if (!hasTimezone && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      parsedDate = parseISO(date + 'Z');
    }
  }

  // API data can be incomplete while a record is being processed. date-fns
  // throws for Invalid Date, which should never take down an entire page.
  if (!(parsedDate instanceof Date) || Number.isNaN(parsedDate.getTime())) {
    return '';
  }
  
  return format(parsedDate, formatStr);
};

export const formatDateTime = (date, timezone) => {
  if (!date) return '';
  
  if (timezone && timezone !== 'UTC') {
    const zonedDate = getZonedDate(date, timezone);
    return format(zonedDate, 'PPP p');
  }

  return formatDate(date, 'PPP p');
};

export const formatTime = (date, timezone) => {
  if (!date) return '';

  if (timezone && timezone !== 'UTC') {
    const zonedDate = getZonedDate(date, timezone);
    return format(zonedDate, 'p');
  }

  return formatDate(date, 'p');
};

const getZonedDate = (dateStr, timezone) => {
  // Ensure we start with a UTC date object
  let date;
  if (typeof dateStr === 'string') {
    // If it's a string, parse it. 
    // If it doesn't have timezone info, assume it's UTC (as per our server convention)
    const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(dateStr);
    const isoStr = !hasTimezone ? dateStr + 'Z' : dateStr;
    date = parseISO(isoStr);
  } else {
    date = dateStr;
  }

  // Parse offset string (e.g., "-0500", "+0530")
  const match = timezone.match(/([+-])(\d{2})(\d{2})/);
  if (match) {
    const sign = match[1] === '+' ? 1 : -1;
    const hours = parseInt(match[2], 10);
    const minutes = parseInt(match[3], 10);
    const offsetMs = sign * (hours * 60 + minutes) * 60 * 1000;
    
    // We want to display the time as it was in that timezone.
    // Since date-fns formats in local time, we need to shift the underlying timestamp
    // so that the local representation matches the target timezone's wall clock time.
    // 
    // However, simply adding offsetMs to UTC timestamp gives us the time in UTC.
    // We want to construct a Date object where getFullYear(), getHours() etc match the target time.
    
    const utcMillis = date.getTime();
    const targetMillis = utcMillis + offsetMs;
    const targetDate = new Date(targetMillis);
    
    // Now we construct a "Local" date that has the same components as the UTC target date
    return new Date(
      targetDate.getUTCFullYear(),
      targetDate.getUTCMonth(),
      targetDate.getUTCDate(),
      targetDate.getUTCHours(),
      targetDate.getUTCMinutes(),
      targetDate.getUTCSeconds()
    );
  }
  
  return date;
};

export const formatRelative = (date) => {
  if (!date) return '';
  let parsedDate = typeof date === 'string' ? parseISO(date) : date;
  
  // Handle naive UTC strings from server by treating them as UTC
  if (typeof date === 'string') {
    // Check if it has a timezone offset (Z, +HH:mm, -HH:mm, +HHmm, -HHmm)
    const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(date);
    if (!hasTimezone) {
      parsedDate = parseISO(date + 'Z');
    }
  }
  
  return formatDistanceToNow(parsedDate, { addSuffix: true });
};

export const formatDuration = (start, end) => {
  if (!start || !end) return '';
  
  let startDate = typeof start === 'string' ? parseISO(start) : start;
  let endDate = typeof end === 'string' ? parseISO(end) : end;

  // Handle naive UTC strings
  if (typeof start === 'string' && !/Z$|[+-]\d{2}:?\d{2}$/.test(start)) {
    startDate = parseISO(start + 'Z');
  }
  if (typeof end === 'string' && !/Z$|[+-]\d{2}:?\d{2}$/.test(end)) {
    endDate = parseISO(end + 'Z');
  }

  const diffMs = endDate.getTime() - startDate.getTime();
  const diffMins = Math.round(diffMs / 60000);
  
  if (diffMins < 60) {
    return `${diffMins} min`;
  }
  
  const hours = Math.floor(diffMins / 60);
  const mins = diffMins % 60;
  
  if (mins === 0) {
    return `${hours} hr`;
  }
  
  return `${hours} hr ${mins} min`;
};

export const formatDateForAPI = (date) => {
  return format(date, 'yyyy-MM-dd');
};

export const getDayBounds = (date) => {
  return {
    start: startOfDay(date),
    end: endOfDay(date),
  };
};
