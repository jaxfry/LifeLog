/**
 * Design System Showcase
 * 
 * A component that demonstrates all the design system tokens and components.
 * This serves as both documentation and testing for the design system.
 */

import React, { useState } from 'react';
import { theme } from '../shared/theme';
import { ThemeSwitcher } from './ui';

const DesignSystemShowcase: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'themes' | 'colors' | 'typography' | 'spacing' | 'components'>('themes');

  return (
    <div className="min-h-screen bg-surface-light p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex justify-between items-start">
          <div>
            <h1 className="text-4xl font-bold text-on-surface mb-2">
              LifeLog Design System
            </h1>
            <p className="text-lg text-on-surface-variant">
              A comprehensive design system for consistent UI development
            </p>
          </div>
          <ThemeSwitcher />
        </div>

        {/* Navigation */}
        <div className="mb-8">
          <nav className="flex space-x-1 bg-surface-primary p-1 rounded-lg border border-outline">
            {(['themes', 'colors', 'typography', 'spacing', 'components'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-md font-medium transition-colors duration-150 capitalize ${
                  activeTab === tab
                    ? 'bg-primary-500 text-on-primary'
                    : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-light'
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="space-y-8">
          {activeTab === 'themes' && <ThemesSection />}
          {activeTab === 'colors' && <ColorsSection />}
          {activeTab === 'typography' && <TypographySection />}
          {activeTab === 'spacing' && <SpacingSection />}
          {activeTab === 'components' && <ComponentsSection />}
        </div>
      </div>
    </div>
  );
};

/* ────────────────────────────────────────────────────────────────────────── */
/*  Themes Section                                                           */
/* ────────────────────────────────────────────────────────────────────────── */

const ThemesSection: React.FC = () => {
  return (
    <div className="space-y-8">
      {/* Theme Overview */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-2xl font-semibold text-on-surface mb-4">Theme System</h3>
        <p className="text-on-surface-variant mb-6">
          LifeLog features a sophisticated dual-theme system with "Clarity at Dawn" (light) and "Midnight Momentum" (dark) themes. 
          The theme switcher allows users to choose their preference or follow their system setting.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Clarity at Dawn */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h4 className="text-lg font-semibold text-gray-900 mb-3">Clarity at Dawn</h4>
            <p className="text-gray-600 text-sm mb-4">
              A crisp, paper-white workstation theme that maintains the analytical journal feel with airy neutrals and confident electric-blue accents.
            </p>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full bg-white border border-gray-300"></div>
                <span className="text-sm text-gray-700">Sheet White (#FFFFFF)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full" style={{backgroundColor: '#F6F7F9'}}></div>
                <span className="text-sm text-gray-700">Porcelain (#F6F7F9)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full" style={{backgroundColor: '#006BFF'}}></div>
                <span className="text-sm text-gray-700">Electric Blue (#006BFF)</span>
              </div>
            </div>
          </div>

          {/* Midnight Momentum */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h4 className="text-lg font-semibold text-gray-100 mb-3">Midnight Momentum</h4>
            <p className="text-gray-300 text-sm mb-4">
              A deep, sophisticated dark theme with midnight blues and purple accents, designed for extended work sessions and reduced eye strain.
            </p>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full" style={{backgroundColor: '#0E1323'}}></div>
                <span className="text-sm text-gray-300">Deep Midnight (#0E1323)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full" style={{backgroundColor: '#151B2E'}}></div>
                <span className="text-sm text-gray-300">Side Panel (#151B2E)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full" style={{backgroundColor: '#55DDFB'}}></div>
                <span className="text-sm text-gray-300">Cyan Accent (#55DDFB)</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Theme Features */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-xl font-semibold text-on-surface mb-4">Theme Features</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-primary-500 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            </div>
            <h4 className="font-semibold text-on-surface mb-2">Light Theme</h4>
            <p className="text-sm text-on-surface-variant">Clean, bright interface optimized for daytime use and high-contrast environments.</p>
          </div>
          
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-secondary-500 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            </div>
            <h4 className="font-semibold text-on-surface mb-2">Dark Theme</h4>
            <p className="text-sm text-on-surface-variant">Sophisticated dark interface designed for extended work sessions and low-light environments.</p>
          </div>
          
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-success-500 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h4 className="font-semibold text-on-surface mb-2">Auto Detection</h4>
            <p className="text-sm text-on-surface-variant">Automatically respects your system preference when no manual theme is selected.</p>
          </div>
        </div>
      </div>

      {/* Implementation Details */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-xl font-semibold text-on-surface mb-4">Implementation</h3>
        <div className="space-y-4">
          <div>
            <h4 className="font-semibold text-on-surface mb-2">CSS Custom Properties</h4>
            <p className="text-sm text-on-surface-variant mb-3">
              The theme system uses CSS custom properties (variables) for instant theme switching without page reload.
            </p>
            <div className="bg-surface-light rounded border border-outline p-4 font-mono text-sm">
              <div className="text-success-600">/* Light theme (default) */</div>
              <div>:root {'{'}</div>
              <div className="ml-4">--background-primary: #FFFFFF;</div>
              <div className="ml-4">--text-primary: #182033;</div>
              <div>{'}'}</div>
              <br />
              <div className="text-success-600">/* Dark theme */</div>
              <div>:root[data-theme="dark"] {'{'}</div>
              <div className="ml-4">--background-primary: #0E1323;</div>
              <div className="ml-4">--text-primary: #E7ECF4;</div>
              <div>{'}'}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ────────────────────────────────────────────────────────────────────────── */
/*  Colors Section                                                           */
/* ────────────────────────────────────────────────────────────────────────── */

const ColorsSection: React.FC = () => {
  const ColorPalette: React.FC<{ 
    title: string; 
    colors: Record<string, string>; 
  }> = ({ title, colors }) => (
    <div className="bg-surface-primary rounded-lg border border-outline p-6">
      <h3 className="text-lg font-semibold text-on-surface mb-4">{title}</h3>
      <div className="grid grid-cols-11 gap-2">
        {Object.entries(colors).map(([shade, value]) => (
          <div key={shade} className="text-center">
            <div
              className="w-full h-16 rounded-md border border-outline mb-2"
              style={{ backgroundColor: value }}
            />
            <div className="text-xs text-on-surface-variant font-mono">{shade}</div>
            <div className="text-xs text-on-surface-variant font-mono">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <ColorPalette title="Primary Colors" colors={theme.colors.primary} />
      <ColorPalette title="Secondary Colors" colors={theme.colors.secondary} />
      <ColorPalette title="Neutral Colors" colors={theme.colors.neutral} />
      <ColorPalette title="Success Colors" colors={theme.colors.success} />
      <ColorPalette title="Warning Colors" colors={theme.colors.warning} />
      <ColorPalette title="Error Colors" colors={theme.colors.error} />
      
      {/* Semantic Colors */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Semantic Colors</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div>
            <h4 className="font-medium text-on-surface mb-2">Text Colors</h4>
            <div className="space-y-2">
              {Object.entries(theme.semantic.text).map(([name, color]) => (
                <div key={name} className="flex items-center space-x-3">
                  <div
                    className="w-6 h-6 rounded border border-outline"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm font-mono">{name}</span>
                </div>
              ))}
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-on-surface mb-2">Background Colors</h4>
            <div className="space-y-2">
              {Object.entries(theme.semantic.background).map(([name, color]) => (
                <div key={name} className="flex items-center space-x-3">
                  <div
                    className="w-6 h-6 rounded border border-outline"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm font-mono">{name}</span>
                </div>
              ))}
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-on-surface mb-2">Border Colors</h4>
            <div className="space-y-2">
              {Object.entries(theme.semantic.border).map(([name, color]) => (
                <div key={name} className="flex items-center space-x-3">
                  <div
                    className="w-6 h-6 rounded border border-outline"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm font-mono">{name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ────────────────────────────────────────────────────────────────────────── */
/*  Typography Section                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

const TypographySection: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Font Families */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Font Families</h3>
        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-on-surface mb-2">Sans Serif (Primary)</h4>
            <p className="text-2xl" style={{ fontFamily: theme.typography.fontFamily.sans.join(', ') }}>
              The quick brown fox jumps over the lazy dog
            </p>
            <p className="text-sm text-on-surface-variant font-mono mt-1">
              {theme.typography.fontFamily.sans[0]}
            </p>
          </div>
          
          <div>
            <h4 className="font-medium text-on-surface mb-2">Monospace (Code)</h4>
            <p className="text-2xl" style={{ fontFamily: theme.typography.fontFamily.mono.join(', ') }}>
              const message = "Hello, World!";
            </p>
            <p className="text-sm text-on-surface-variant font-mono mt-1">
              {theme.typography.fontFamily.mono[0]}
            </p>
          </div>
        </div>
      </div>

      {/* Font Sizes */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Type Scale</h3>
        <div className="space-y-4">
          {Object.entries(theme.typography.fontSize).map(([size, config]) => (
            <div key={size} className="flex items-baseline space-x-4">
              <div className="w-16 text-sm text-on-surface-variant font-mono">{size}</div>
              <div className="flex-1">
                <p
                  style={{
                    fontSize: config[0],
                    lineHeight: config[1]?.lineHeight,
                  }}
                >
                  The quick brown fox jumps over the lazy dog
                </p>
                <p className="text-xs text-on-surface-variant font-mono">
                  {config[0]} / {config[1]?.lineHeight}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Font Weights */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Font Weights</h3>
        <div className="space-y-2">
          {Object.entries(theme.typography.fontWeight).map(([name, weight]) => (
            <div key={name} className="flex items-center space-x-4">
              <div className="w-24 text-sm text-on-surface-variant font-mono">{name}</div>
              <p
                className="text-lg flex-1"
                style={{ fontWeight: weight }}
              >
                The quick brown fox jumps over the lazy dog
              </p>
              <div className="text-sm text-on-surface-variant font-mono">{weight}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

/* ────────────────────────────────────────────────────────────────────────── */
/*  Spacing Section                                                          */
/* ────────────────────────────────────────────────────────────────────────── */

const SpacingSection: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Spacing Scale */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Spacing Scale</h3>
        <div className="space-y-3">
          {Object.entries(theme.spacing).map(([token, value]) => (
            <div key={token} className="flex items-center space-x-4">
              <div className="w-12 text-sm text-on-surface-variant font-mono">{token}</div>
              <div className="w-20 text-sm text-on-surface-variant font-mono">{value}</div>
              <div
                className="bg-primary-500 h-4"
                style={{ width: value }}
              />
              <div className="text-sm text-on-surface-variant">
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Border Radius */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Border Radius</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(theme.borderRadius).map(([token, value]) => (
            <div key={token} className="text-center">
              <div
                className="w-16 h-16 bg-primary-500 mx-auto mb-2"
                style={{ borderRadius: value }}
              />
              <div className="text-sm font-mono text-on-surface-variant">{token}</div>
              <div className="text-xs font-mono text-on-surface-variant">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Shadows */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Box Shadows</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {Object.entries(theme.boxShadow).map(([token, value]) => (
            <div key={token} className="text-center">
              <div
                className="w-16 h-16 bg-surface-primary mx-auto mb-2 border border-outline-light"
                style={{ boxShadow: value }}
              />
              <div className="text-sm font-mono text-on-surface-variant">{token}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

/* ────────────────────────────────────────────────────────────────────────── */
/*  Components Section                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

const ComponentsSection: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Buttons */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Buttons</h3>
        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-on-surface mb-2">Variants</h4>
            <div className="flex flex-wrap gap-3">
              <button className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-on-primary font-medium rounded-md transition-colors">
                Primary
              </button>
              <button className="px-4 py-2 bg-surface-light hover:bg-surface-light text-on-surface font-medium rounded-md border border-outline transition-colors">
                Secondary
              </button>
              <button className="px-4 py-2 bg-transparent hover:bg-primary-50 text-primary-600 font-medium rounded-md border border-primary-300 transition-colors">
                Outline
              </button>
              <button className="px-4 py-2 bg-transparent hover:bg-primary-50 text-primary-600 font-medium rounded-md transition-colors">
                Ghost
              </button>
              <button className="px-4 py-2 bg-error-500 hover:bg-error-600 text-on-error font-medium rounded-md transition-colors">
                Danger
              </button>
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-on-surface mb-2">Sizes</h4>
            <div className="flex flex-wrap items-center gap-3">
              <button className="px-2 py-1 bg-primary-500 hover:bg-primary-600 text-on-primary text-xs font-medium rounded transition-colors">
                Extra Small
              </button>
              <button className="px-3 py-1.5 bg-primary-500 hover:bg-primary-600 text-on-primary text-sm font-medium rounded-md transition-colors">
                Small
              </button>
              <button className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-on-primary font-medium rounded-md transition-colors">
                Medium
              </button>
              <button className="px-5 py-2.5 bg-primary-500 hover:bg-primary-600 text-on-primary text-lg font-medium rounded-md transition-colors">
                Large
              </button>
              <button className="px-6 py-3 bg-primary-500 hover:bg-primary-600 text-on-primary text-xl font-medium rounded-md transition-colors">
                Extra Large
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Form Inputs */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Form Inputs</h3>
        <div className="space-y-4 max-w-md">
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1">
              Default Input
            </label>
            <input
              type="text"
              placeholder="Enter text..."
              className="w-full px-3 py-2.5 border border-outline rounded-md bg-surface-primary text-on-surface placeholder-on-surface-variant focus:border-primary-500 focus:ring-1 focus:ring-primary-500 transition-colors"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1">
              Success State
            </label>
            <input
              type="text"
              placeholder="Success state..."
              className="w-full px-3 py-2.5 border border-success-500 rounded-md bg-surface-primary text-on-surface placeholder-on-surface-variant focus:border-success-500 focus:ring-1 focus:ring-success-500 transition-colors"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1">
              Error State
            </label>
            <input
              type="text"
              placeholder="Error state..."
              className="w-full px-3 py-2.5 border border-error-500 rounded-md bg-surface-primary text-on-surface placeholder-on-surface-variant focus:border-error-500 focus:ring-1 focus:ring-error-500 transition-colors"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1">
              Disabled State
            </label>
            <input
              type="text"
              placeholder="Disabled state..."
              disabled
              className="w-full px-3 py-2.5 border border-outline-light rounded-md bg-surface-light text-on-surface-variant placeholder-on-surface-variant cursor-not-allowed"
            />
          </div>
        </div>
      </div>

      {/* Cards */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Cards</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-surface-primary border border-outline rounded-lg shadow-sm p-6">
            <h4 className="text-lg font-semibold text-on-surface mb-2">Default Card</h4>
            <p className="text-on-surface-variant">Basic card with subtle shadow and border.</p>
          </div>
          
          <div className="bg-surface-primary border border-outline rounded-lg shadow-md p-6">
            <h4 className="text-lg font-semibold text-on-surface mb-2">Elevated Card</h4>
            <p className="text-on-surface-variant">Card with more prominent shadow for emphasis.</p>
          </div>
          
          <div className="bg-surface-primary border border-outline rounded-lg shadow-sm p-6 hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 cursor-pointer">
            <h4 className="text-lg font-semibold text-on-surface mb-2">Interactive Card</h4>
            <p className="text-on-surface-variant">Hover me for interaction feedback!</p>
          </div>
        </div>
      </div>

      {/* Badges */}
      <div className="bg-surface-primary rounded-lg border border-outline p-6">
        <h3 className="text-lg font-semibold text-on-surface mb-4">Badges</h3>
        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-on-surface mb-2">Variants</h4>
            <div className="flex flex-wrap gap-2">
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-surface-light text-on-surface">
                Default
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-primary-100 text-primary-700">
                Primary
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-success-100 text-success-700">
                Success
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-warning-100 text-warning-700">
                Warning
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-error-100 text-error-700">
                Error
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-transparent text-on-surface-variant border border-outline">
                Outline
              </span>
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-on-surface mb-2">Sizes</h4>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-primary-100 text-primary-700">
                Small
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-primary-100 text-primary-700">
                Medium
              </span>
              <span className="inline-flex items-center px-2.5 py-1.5 rounded-full text-sm font-medium bg-primary-100 text-primary-700">
                Large
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DesignSystemShowcase;
