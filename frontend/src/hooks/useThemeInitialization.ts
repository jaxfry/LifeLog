import { useEffect } from 'react';

/**
 * Custom hook to initialize and manage the theme system
 * Ensures proper theme application on app startup
 */
export const useThemeInitialization = () => {
  useEffect(() => {
    const initializeTheme = () => {
      const savedTheme = localStorage.getItem('lifelog-theme');
      const root = document.documentElement;
      
      if (savedTheme && (savedTheme === 'light' || savedTheme === 'dark')) {
        // Apply saved theme
        root.setAttribute('data-theme', savedTheme);
      } else {
        // Remove any data-theme attribute to let auto-detection work
        root.removeAttribute('data-theme');
      }
    };

    // Initialize theme immediately
    initializeTheme();

    // Listen for system theme changes when in auto mode
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemThemeChange = () => {
      const savedTheme = localStorage.getItem('lifelog-theme');
      // Only respond to system changes if user hasn't set a preference
      if (!savedTheme) {
        // Force a re-render by briefly removing and re-adding the attribute
        const root = document.documentElement;
        root.removeAttribute('data-theme');
      }
    };

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    
    return () => {
      mediaQuery.removeEventListener('change', handleSystemThemeChange);
    };
  }, []);
};

export default useThemeInitialization;
