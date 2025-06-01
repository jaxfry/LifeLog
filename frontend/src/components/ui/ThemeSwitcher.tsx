import React, { useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'auto';

interface ThemeSwitcherProps {
  className?: string;
}

export const ThemeSwitcher: React.FC<ThemeSwitcherProps> = ({ className = '' }) => {
  const [theme, setTheme] = useState<Theme>(() => {
    // Get theme from localStorage or default to 'auto'
    const savedTheme = localStorage.getItem('lifelog-theme') as Theme;
    return savedTheme || 'auto';
  });

  useEffect(() => {
    const applyTheme = (themeValue: Theme) => {
      const root = document.documentElement;
      
      if (themeValue === 'auto') {
        // Remove data-theme attribute to let CSS auto-detection work
        root.removeAttribute('data-theme');
        localStorage.removeItem('lifelog-theme');
      } else {
        // Set explicit theme
        root.setAttribute('data-theme', themeValue);
        localStorage.setItem('lifelog-theme', themeValue);
      }
    };

    applyTheme(theme);
  }, [theme]);

  const handleThemeChange = (newTheme: Theme) => {
    setTheme(newTheme);
  };

  const getIcon = (themeType: Theme) => {
    switch (themeType) {
      case 'light':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        );
      case 'dark':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        );
      case 'auto':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        );
    }
  };

  return (
    <div 
      className={`flex items-center gap-1 rounded-lg p-1 ${className}`}
      style={{
        backgroundColor: 'var(--background-secondary)',
        border: '1px solid var(--border-light)',
      }}
    >
      {(['light', 'dark', 'auto'] as const).map((themeOption) => (
        <button
          key={themeOption}
          onClick={() => handleThemeChange(themeOption)}
          className={`
            flex items-center justify-center w-8 h-8 rounded-md transition-hover
            ${theme === themeOption 
              ? 'bg-accent-500 text-white shadow-sm' 
              : 'text-secondary hover:bg-tertiary hover:text-primary'
            }
          `}
          style={{
            backgroundColor: theme === themeOption ? 'var(--interactive-primary)' : 'transparent',
            color: theme === themeOption ? 'var(--text-inverse)' : 'var(--text-secondary)',
          }}
          onMouseEnter={(e) => {
            if (theme !== themeOption) {
              e.currentTarget.style.backgroundColor = 'var(--interactive-secondary-hover)';
              e.currentTarget.style.color = 'var(--text-primary)';
            }
          }}
          onMouseLeave={(e) => {
            if (theme !== themeOption) {
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = 'var(--text-secondary)';
            }
          }}
          title={`Switch to ${themeOption} theme`}
          aria-label={`Switch to ${themeOption} theme`}
        >
          {getIcon(themeOption)}
        </button>
      ))}
    </div>
  );
};

export default ThemeSwitcher;
