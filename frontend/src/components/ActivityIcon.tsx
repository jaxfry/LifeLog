import { Code, Users, FileText } from 'lucide-react';
import React from 'react';

const iconMap: { [key: string]: React.ElementType } = {
  Code,
  Users,
  FileText,
};

type ActivityIconProps = {
  icon: string;
  className?: string;
};

export function ActivityIcon({ icon, className }: ActivityIconProps) {
  const IconComponent = iconMap[icon];
  if (!IconComponent) {
    return <FileText className={className} />; // Default icon
  }
  return <IconComponent className={className} />;
}
