import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import TimelineSidebar from "../components/TimelineSidebar";
import OtherTools from "../components/OtherTools";

export default function ShellLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const isTimeline = location.pathname.startsWith("/day");

  return (
    <div className="h-full w-full flex overflow-hidden bg-primary">
      <motion.aside
        animate={{ width: collapsed ? 72 : 288 }}
        className="flex-shrink-0 bg-secondary text-primary h-full border-r border-light flex flex-col"
      >
        <header className="p-5 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-accent-gradient flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 text-inverse" aria-hidden="true">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z" />
            </svg>
          </div>
          {!collapsed && <h1 className="type-h3">LifeLog</h1>}
        </header>
        <nav className="flex flex-col px-5 space-y-1" aria-label="Main navigation">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'font-semibold' : ''}`}>Dashboard</NavLink>
          <NavLink to="/day/2025-05-22" className={({ isActive }) => `nav-link ${isActive ? 'font-semibold' : ''}`}>Timeline</NavLink>
          <NavLink to="/projects" className={({ isActive }) => `nav-link ${isActive ? 'font-semibold' : ''}`}>Projects</NavLink>
          <NavLink to="/insights" className={({ isActive }) => `nav-link ${isActive ? 'font-semibold' : ''}`}>Insights</NavLink>
        </nav>
        <div className="mt-auto p-5">
          <button
            className="w-full rounded-lg bg-tertiary hover:bg-tertiary/80 text-primary transition-colors focus-ring"
            onClick={() => setCollapsed(!collapsed)}
            aria-label="Toggle sidebar"
          >
            {collapsed ? '›' : '‹'}
          </button>
        </div>
        <div className="border-t border-light flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            {isTimeline ? (
              <motion.div key="timeline" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <TimelineSidebar collapsed={collapsed} />
              </motion.div>
            ) : (
              <motion.div key="tools" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <OtherTools />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.aside>
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
