import { format, parseISO, formatDistanceToNow, startOfDay, endOfDay } from 'date-fns';

export const formatDate = (date, formatStr = 'PPP') => {
  if (!date) return '';
  const parsedDate = typeof date === 'string' ? parseISO(date) : date;
  return format(parsedDate, formatStr);
};

export const formatDateTime = (date) => {
  return formatDate(date, 'PPP p');
};

export const formatTime = (date) => {
  return formatDate(date, 'p');
};

export const formatRelative = (date) => {
  if (!date) return '';
  const parsedDate = typeof date === 'string' ? parseISO(date) : date;
  return formatDistanceToNow(parsedDate, { addSuffix: true });
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
