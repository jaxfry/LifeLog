import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Home,
  CalendarDays,
  FolderKanban,
  LineChart,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import TimelineSidebar from "../components/TimelineSidebar";
import OtherTools from "../components/OtherTools";

export default function ShellLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const isTimeline = location.pathname.startsWith("/day");

  const navItems = [
    { to: "/", label: "Dashboard", icon: Home, end: true },
    { to: "/day/2025-05-22", label: "Timeline", icon: CalendarDays },
    { to: "/projects", label: "Projects", icon: FolderKanban },
    { to: "/insights", label: "Insights", icon: LineChart },
  ];

  return (
    <div className="h-full w-full flex overflow-hidden bg-primary">
      <motion.aside
        animate={{ width: collapsed ? 80 : 288 }}
        className="flex-shrink-0 bg-secondary text-primary h-full border-r border-light"
      >
        <div className="flex flex-col h-full">
          <header className={`flex items-center ${collapsed ? 'px-2 py-2' : 'p-4 gap-3'}`}>
            <div className="w-8 h-8 flex-shrink-0 rounded-full bg-accent-gradient flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 text-inverse" aria-hidden="true">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z" />
              </svg>
            </div>
            {!collapsed && <h1 className="type-h3 whitespace-nowrap">LifeLog</h1>}
            <button
              className="ml-auto rounded-lg p-2 hover:bg-tertiary/80 transition-colors focus-ring"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
            </button>
          </header>
          <nav className="flex flex-col px-3 space-y-1" aria-label="Main navigation">
            {navItems.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `${collapsed ? 'justify-center' : ''} nav-link ${isActive ? 'bg-neutral-100 font-semibold' : ''}`
                }
              >
                <Icon className="w-5 h-5" aria-hidden="true" />
                {!collapsed && <span>{label}</span>}
              </NavLink>
            ))}
          </nav>
          <div className="border-t border-light flex-1 overflow-y-auto">
            <AnimatePresence mode="wait">
              {!collapsed && (
                isTimeline ? (
                  <motion.div key="timeline" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <TimelineSidebar collapsed={collapsed} />
                  </motion.div>
                ) : (
                  <motion.div key="tools" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <OtherTools />
                  </motion.div>
                )
              )}
            </AnimatePresence>
          </div>
        </div>
      </motion.aside>
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
