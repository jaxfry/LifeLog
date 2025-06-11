import {
  Home,
  PieChart,
  Calendar,
  FolderOpen
} from "lucide-react";

export const navData = {
  navMain: [
    {
      title: "Dashboard",
      url: "/dashboard",
      icon: Home,
    },
    {
      title: "Timeline",
      url: "/timeline",
      icon: Calendar,
    },
    {
      title: "Projects",
      url: "/projects",
      icon: FolderOpen
    },
    {
      title: "Insights",
      url: "/insights",
      icon: PieChart,
    }
  ],
};
