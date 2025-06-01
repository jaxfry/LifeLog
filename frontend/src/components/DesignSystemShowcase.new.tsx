/**
 * Design System Showcase
 * 
 * A component that demonstrates all the design system tokens and components.
 * This serves as both documentation and testing for the design system.
 */

import React, { useState } from 'react';
import { theme } from '../shared/theme';

const DesignSystemShowcase: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'colors' | 'typography' | 'spacing' | 'components'>('colors');

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            LifeLog Design System
          </h1>
          <p className="text-lg text-gray-600">
            A comprehensive design system for consistent UI development
          </p>
        </div>

        {/* Navigation */}
        <div className="mb-8">
          <nav className="flex space-x-1 bg-white p-1 rounded-lg border border-gray-200">
            {(['colors', 'typography', 'spacing', 'components'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-md font-medium text-sm transition-colors ${
                  activeTab === tab
                    ? 'bg-blue-500 text-white shadow-sm'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="space-y-8">
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
/*  Colors Section                                                           */
/* ────────────────────────────────────────────────────────────────────────── */

const ColorsSection: React.FC = () => {
  const ColorPalette: React.FC<{ 
    title: string; 
    colors: Record<string, string>; 
  }> = ({ title, colors }) => (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">{title}</h3>
      <div className="grid grid-cols-11 gap-2">
        {Object.entries(colors).map(([shade, value]) => (
          <div key={shade} className="text-center">
            <div
              className="w-full h-16 rounded-md border border-gray-200 mb-2"
              style={{ backgroundColor: value }}
            />
            <div className="text-xs text-gray-600 font-mono">{shade}</div>
            <div className="text-xs text-gray-600 font-mono">{value}</div>
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
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Semantic Colors</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Text Colors</h4>
            <div className="space-y-2">
              {Object.entries(theme.semantic.text).map(([name, color]) => (
                <div key={name} className="flex items-center space-x-3">
                  <div
                    className="w-6 h-6 rounded border border-gray-200"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm font-mono text-gray-600">{name}</span>
                  <span className="text-sm font-mono text-gray-400">{color}</span>
                </div>
              ))}
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Background Colors</h4>
            <div className="space-y-2">
              {Object.entries(theme.semantic.background).map(([name, color]) => (
                <div key={name} className="flex items-center space-x-3">
                  <div
                    className="w-6 h-6 rounded border border-gray-200"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm font-mono text-gray-600">{name}</span>
                  <span className="text-sm font-mono text-gray-400">{color}</span>
                </div>
              ))}
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Border Colors</h4>
            <div className="space-y-2">
              {Object.entries(theme.semantic.border).map(([name, color]) => (
                <div key={name} className="flex items-center space-x-3">
                  <div
                    className="w-6 h-6 rounded border border-gray-200"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm font-mono text-gray-600">{name}</span>
                  <span className="text-sm font-mono text-gray-400">{color}</span>
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
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Font Families</h3>
        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Sans Serif (Primary)</h4>
            <p className="text-2xl" style={{ fontFamily: theme.typography.fontFamily.sans.join(', ') }}>
              The quick brown fox jumps over the lazy dog
            </p>
            <p className="text-sm text-gray-600 font-mono mt-1">
              {theme.typography.fontFamily.sans.join(', ')}
            </p>
          </div>
          
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Monospace (Code)</h4>
            <p className="text-2xl" style={{ fontFamily: theme.typography.fontFamily.mono.join(', ') }}>
              const message = "Hello, World!";
            </p>
            <p className="text-sm text-gray-600 font-mono mt-1">
              {theme.typography.fontFamily.mono.join(', ')}
            </p>
          </div>
        </div>
      </div>

      {/* Font Sizes */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Type Scale</h3>
        <div className="space-y-4">
          {Object.entries(theme.typography.fontSize).map(([size, config]) => {
            const [fontSize, options] = Array.isArray(config) ? config : [config, {}];
            const lineHeight = typeof options === 'object' && 'lineHeight' in options ? options.lineHeight : '1.5';
            
            return (
              <div key={size} className="flex items-baseline space-x-4">
                <div className="w-16 text-sm font-mono text-gray-600">{size}</div>
                <div className="flex-1">
                  <p style={{ fontSize, lineHeight }}>
                    The quick brown fox jumps over the lazy dog
                  </p>
                </div>
                <div className="text-sm font-mono text-gray-400">
                  {fontSize} / {lineHeight}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Font Weights */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Font Weights</h3>
        <div className="space-y-2">
          {Object.entries(theme.typography.fontWeight).map(([name, weight]) => (
            <div key={name} className="flex items-center space-x-4">
              <div className="w-24 text-sm font-mono text-gray-600">{name}</div>
              <div className="flex-1">
                <p style={{ fontWeight: weight }} className="text-xl">
                  The quick brown fox jumps over the lazy dog
                </p>
              </div>
              <div className="text-sm font-mono text-gray-400">{weight}</div>
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
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Spacing Scale</h3>
        <div className="space-y-3">
          {Object.entries(theme.spacing).map(([token, value]) => (
            <div key={token} className="flex items-center space-x-4">
              <div className="w-16 text-sm font-mono text-gray-600">{token}</div>
              <div
                className="bg-blue-500 h-4"
                style={{ width: value }}
              />
              <div className="text-sm font-mono text-gray-400">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Border Radius */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Border Radius</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(theme.borderRadius).map(([token, value]) => (
            <div key={token} className="text-center">
              <div
                className="w-16 h-16 bg-blue-500 mx-auto mb-2"
                style={{ borderRadius: value }}
              />
              <div className="text-sm font-mono text-gray-600">{token}</div>
              <div className="text-xs font-mono text-gray-400">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Shadows */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Box Shadows</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {Object.entries(theme.boxShadow).map(([token, value]) => (
            <div key={token} className="text-center">
              <div
                className="w-16 h-16 bg-white mx-auto mb-2 border border-gray-100"
                style={{ boxShadow: value }}
              />
              <div className="text-sm font-mono text-gray-600">{token}</div>
              <div className="text-xs font-mono text-gray-400 break-all">{value}</div>
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
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Buttons</h3>
        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Variants</h4>
            <div className="flex flex-wrap gap-3">
              <button className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-md transition-colors">
                Primary
              </button>
              <button className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-900 font-medium rounded-md transition-colors">
                Secondary
              </button>
              <button className="px-4 py-2 bg-transparent hover:bg-blue-50 text-blue-600 font-medium rounded-md border border-blue-300 transition-colors">
                Outline
              </button>
              <button className="px-4 py-2 bg-transparent hover:bg-blue-50 text-blue-600 font-medium rounded-md transition-colors">
                Ghost
              </button>
              <button className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white font-medium rounded-md transition-colors">
                Destructive
              </button>
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Sizes</h4>
            <div className="flex flex-wrap items-center gap-3">
              <button className="px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-md transition-colors">
                Small
              </button>
              <button className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-md transition-colors">
                Base
              </button>
              <button className="px-5 py-2.5 bg-blue-500 hover:bg-blue-600 text-white text-lg font-medium rounded-md transition-colors">
                Large
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Form Inputs */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Form Inputs</h3>
        <div className="space-y-4 max-w-md">
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Default Input
            </label>
            <input
              type="text"
              placeholder="Enter text..."
              className="w-full px-3 py-2.5 border border-gray-300 rounded-md bg-white text-gray-900 placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Success State
            </label>
            <input
              type="text"
              placeholder="Success state..."
              className="w-full px-3 py-2.5 border border-green-500 rounded-md bg-white text-gray-900 placeholder-gray-500 focus:border-green-500 focus:ring-1 focus:ring-green-500 transition-colors"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Error State
            </label>
            <input
              type="text"
              placeholder="Error state..."
              className="w-full px-3 py-2.5 border border-red-500 rounded-md bg-white text-gray-900 placeholder-gray-500 focus:border-red-500 focus:ring-1 focus:ring-red-500 transition-colors"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Disabled State
            </label>
            <input
              type="text"
              placeholder="Disabled state..."
              disabled
              className="w-full px-3 py-2.5 border border-gray-200 rounded-md bg-gray-50 text-gray-400 placeholder-gray-400 cursor-not-allowed"
            />
          </div>
        </div>
      </div>

      {/* Cards */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Cards</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6">
            <h4 className="text-lg font-semibold text-gray-900 mb-2">Default Card</h4>
            <p className="text-gray-600">Basic card with subtle shadow and border.</p>
          </div>
          
          <div className="bg-white border border-gray-200 rounded-lg shadow-md p-6">
            <h4 className="text-lg font-semibold text-gray-900 mb-2">Elevated Card</h4>
            <p className="text-gray-600">Card with more prominent shadow for emphasis.</p>
          </div>
          
          <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6 hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 cursor-pointer">
            <h4 className="text-lg font-semibold text-gray-900 mb-2">Interactive Card</h4>
            <p className="text-gray-600">Card with hover effects for interactive elements.</p>
          </div>
        </div>
      </div>

      {/* Badges */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Badges</h3>
        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Badge Variants</h4>
            <div className="flex flex-wrap gap-3">
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                Primary
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                Secondary
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
                Success
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
                Warning
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700">
                Error
              </span>
            </div>
          </div>
          
          <div>
            <h4 className="font-medium text-gray-900 mb-2">Badge Sizes</h4>
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                Small
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                Base
              </span>
              <span className="inline-flex items-center px-2.5 py-1.5 rounded-full text-sm font-medium bg-blue-100 text-blue-700">
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
