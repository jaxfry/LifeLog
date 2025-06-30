import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { formatDistanceStrict } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function formatDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function formatDuration(start: Date, end: Date): string {
  return formatDistanceStrict(start, end);
}

const activityMetadataConfig = [
  {
    keywords: ["code", "develop"],
    metadata: {
      icon: "Code",
      color: "blue",
      bgClass: "bg-blue-100",
      textClass: "text-blue-600",
      borderClass: "border-blue-500",
      iconBgClass: "bg-blue-200",
    },
  },
  {
    keywords: ["meeting", "call"],
    metadata: {
      icon: "Users",
      color: "green",
      bgClass: "bg-green-100",
      textClass: "text-green-600",
      borderClass: "border-green-500",
      iconBgClass: "bg-green-200",
    },
  },
];

const defaultMetadata = {
  icon: "FileText",
  color: "gray",
  bgClass: "bg-gray-100",
  textClass: "text-gray-600",
  borderClass: "border-gray-500",
  iconBgClass: "bg-gray-200",
};

export function getActivityMetadata(activity: string) {
  const lowerCaseActivity = activity.toLowerCase();
  for (const config of activityMetadataConfig) {
    if (config.keywords.some(keyword => lowerCaseActivity.includes(keyword))) {
      return config.metadata;
    }
  }
  return defaultMetadata;
}
