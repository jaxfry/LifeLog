// src/lib/timeline-utils.ts

import { 
  MessageSquare, 
  Moon, 
  MousePointerClick,
  Globe,
  Terminal,
  type LucideIcon 
} from "lucide-react";

export interface ActivityMetadata {
  icon: LucideIcon;
  color: string;
  bgClass: string;
  iconBgClass: string;
  textClass: string;
  borderClass: string;
}

/**
 * Returns metadata for a given activity string, such as an icon and color.
 *
 * @param activity - The activity string to get metadata for.
 * @returns An object containing metadata for the activity.
 */
export function getActivityMetadata(activity: string): ActivityMetadata {
  const lowerCaseActivity = activity.toLowerCase();
  
  if (lowerCaseActivity.includes('develop') || lowerCaseActivity.includes('coding') || lowerCaseActivity.includes('script')) {
    return { 
      icon: Terminal, 
      color: 'development', 
      bgClass: 'bg-development/10',
      iconBgClass: 'bg-development/20',
      textClass: 'text-development',
      borderClass: 'border-development/20'
    };
  }
  
  if (lowerCaseActivity.includes('chat') || lowerCaseActivity.includes('discord') || lowerCaseActivity.includes('communicating')) {
    return { 
      icon: MessageSquare, 
      color: 'communication', 
      bgClass: 'bg-communication/10',
      iconBgClass: 'bg-communication/20',
      textClass: 'text-communication',
      borderClass: 'border-communication/20'
    };
  }
  
  if (lowerCaseActivity.includes('user away') || lowerCaseActivity.includes('locked')) {
    return { 
      icon: Moon, 
      color: 'system', 
      bgClass: 'bg-system/10',
      iconBgClass: 'bg-system/20',
      textClass: 'text-system',
      borderClass: 'border-system/20'
    };
  }
  
  if (lowerCaseActivity.includes('browse') || lowerCaseActivity.includes('web')) {
    return { 
      icon: Globe, 
      color: 'general', 
      bgClass: 'bg-general/10',
      iconBgClass: 'bg-general/20',
      textClass: 'text-general',
      borderClass: 'border-general/20'
    };
  }
  
  return { 
    icon: MousePointerClick, 
    color: 'general', 
    bgClass: 'bg-general/10',
    iconBgClass: 'bg-general/20',
    textClass: 'text-general',
    borderClass: 'border-general/20'
  };
}

/**
 * Formats the duration between two dates into a human-readable string.
 *
 * @param start - The start date.
 * @param end - The end date.
 * @returns A string representing the duration (e.g., "1h 30m").
 */
export function formatDuration(start: Date, end: Date): string {
  const diff = end.getTime() - start.getTime();
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}
