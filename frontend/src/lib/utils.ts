import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { formatDistanceStrict } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(start: Date, end: Date): string {
  return formatDistanceStrict(start, end);
}

export function getActivityMetadata(activity: string) {
  // Simple logic to assign colors and icons based on activity keywords
  if (
    activity.toLowerCase().includes("code") ||
    activity.toLowerCase().includes("develop")
  ) {
    return {
      icon: "Code",
      color: "blue",
      bgClass: "bg-blue-100",
      textClass: "text-blue-600",
      borderClass: "border-blue-500",
      iconBgClass: "bg-blue-200",
    };
  }
  if (
    activity.toLowerCase().includes("meeting") ||
    activity.toLowerCase().includes("call")
  ) {
    return {
      icon: "Users",
      color: "green",
      bgClass: "bg-green-100",
      textClass: "text-green-600",
      borderClass: "border-green-500",
      iconBgClass: "bg-green-200",
    };
  }
  // default case
  return {
    icon: "FileText",
    color: "gray",
    bgClass: "bg-gray-100",
    textClass: "text-gray-600",
    borderClass: "border-gray-500",
    iconBgClass: "bg-gray-200",
  };
}
