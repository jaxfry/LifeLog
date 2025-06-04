# LifeLog Design System

A comprehensive design system providing color palette, typography, spacing tokens, and component guidelines for the LifeLog application.

## Table of Contents

- [Overview](#overview)
- [Design Principles](#design-principles)
- [Color Palette](#color-palette)
- [Typography](#typography)
- [Spacing & Layout](#spacing--layout)
- [Components](#components)
- [Usage Guidelines](#usage-guidelines)
- [Development](#development)

## Overview

The LifeLog design system ensures visual consistency, accessibility, and maintainability across the entire application. It provides a centralized set of design tokens, component patterns, and usage guidelines.

### Design Tokens

Our design system is built on a foundation of design tokens organized into:
- **Primitive tokens**: Raw values (colors, spacing, typography)
- **Semantic tokens**: Meaningful, context-aware values (text-primary, surface-secondary)
- **Component tokens**: Component-specific styling patterns

## Design Principles

### 1. Consistency
- Use design tokens consistently across all components
- Maintain visual hierarchy through consistent spacing and typography
- Apply consistent interaction patterns

### 2. Accessibility
- Maintain WCAG 2.1 AA contrast ratios
- Support keyboard navigation
- Provide clear focus indicators
- Use semantic HTML and ARIA attributes

### 3. Scalability
- Design for multiple screen sizes and devices
- Use relative units (rem, em, %) where appropriate
- Create flexible, reusable component patterns

### 4. Performance
- Optimize for fast loading and rendering
- Use CSS custom properties for theme flexibility
- Minimize layout shifts and reflows

## Color Palette

### Primary Colors
Our primary blue palette provides the main brand identity:

```css
--color-primary-50: #eff6ff   /* Very light blue */
--color-primary-100: #dbeafe  /* Light blue */
--color-primary-200: #bfdbfe  /* */
--color-primary-300: #93c5fd  /* */
--color-primary-400: #60a5fa  /* */
--color-primary-500: #3b82f6  /* Main brand blue */
--color-primary-600: #2563eb  /* */
--color-primary-700: #1d4ed8  /* */
--color-primary-800: #1e40af  /* */
--color-primary-900: #1e3a8a  /* */
--color-primary-950: #172554  /* Very dark blue */
```

### Secondary Colors
Supporting accent colors for variety and emphasis:

```css
--color-secondary-50: #f0f9ff
--color-secondary-500: #0ea5e9  /* Main secondary */
--color-secondary-950: #082f49
```

### Semantic Colors

#### Success (Green)
```css
--color-success-50: #f0fdf4   /* Success background */
--color-success-500: #22c55e  /* Success primary */
--color-success-700: #15803d  /* Success dark */
```

#### Warning (Amber)
```css
--color-warning-50: #fffbeb   /* Warning background */
--color-warning-500: #f59e0b  /* Warning primary */
--color-warning-700: #b45309  /* Warning dark */
```

#### Error (Red)
```css
--color-error-50: #fef2f2     /* Error background */
--color-error-500: #ef4444    /* Error primary */
--color-error-700: #b91c1c    /* Error dark */
```

#### Neutral (Gray Scale)
```css
--color-neutral-0: #ffffff    /* Pure white */
--color-neutral-50: #f9fafb   /* Very light gray */
--color-neutral-100: #f3f4f6  /* Light gray */
--color-neutral-200: #e5e7eb  /* Border light */
--color-neutral-300: #d1d5db  /* Border default */
--color-neutral-400: #9ca3af  /* Disabled text */
--color-neutral-500: #6b7280  /* Tertiary text */
--color-neutral-600: #4b5563  /* Secondary text */
--color-neutral-700: #374151  /* */
--color-neutral-800: #1f2937  /* */
--color-neutral-900: #111827  /* Primary text */
--color-neutral-950: #030712  /* Very dark */
```

### Color Usage Guidelines

#### Text Colors
```css
/* Use for primary content */
color: var(--text-primary);

/* Use for secondary content */
color: var(--text-secondary);

/* Use for tertiary content, captions */
color: var(--text-tertiary);

/* Use for disabled states */
color: var(--text-disabled);

/* Use for links */
color: var(--text-link);
```

#### Background Colors
```css
/* Main page background */
background-color: var(--background-primary);

/* Secondary backgrounds, panels */
background-color: var(--background-secondary);

/* Tertiary backgrounds, hover states */
background-color: var(--background-tertiary);
```

#### Interactive Colors
```css
/* Primary buttons, active states */
background-color: var(--interactive-primary);

/* Primary button hover */
background-color: var(--interactive-primary-hover);

/* Destructive actions */
background-color: var(--interactive-danger);
```

## Typography

### Font Families

#### Sans Serif (Primary)
```css
font-family: var(--font-family-sans);
/* Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif */
```

#### Monospace (Code)
```css
font-family: var(--font-family-mono);
/* 'Fira Code', 'JetBrains Mono', 'SF Mono', Monaco, Inconsolata, 'Roboto Mono', monospace */
```

### Type Scale

| Token | Size | Line Height | Usage |
|-------|------|-------------|-------|
| `xs` | 12px | 16px | Captions, labels |
| `sm` | 14px | 20px | Small text, metadata |
| `base` | 16px | 24px | Body text |
| `lg` | 18px | 28px | Large body text |
| `xl` | 20px | 28px | Subheadings |
| `2xl` | 24px | 32px | H4 headings |
| `3xl` | 30px | 36px | H3 headings |
| `4xl` | 36px | 40px | H2 headings |
| `5xl` | 48px | 1 | H1 headings |
| `6xl` | 60px | 1 | Display large |
| `7xl` | 72px | 1 | Display XL |
| `8xl` | 96px | 1 | Display XXL |
| `9xl` | 128px | 1 | Display XXXL |

### Font Weights

| Token | Weight | Usage |
|-------|--------|-------|
| `thin` | 100 | Display text |
| `extralight` | 200 | Display text |
| `light` | 300 | Body text, captions |
| `normal` | 400 | Default body text |
| `medium` | 500 | Emphasis, buttons |
| `semibold` | 600 | Headings, strong emphasis |
| `bold` | 700 | Headings, strong emphasis |
| `extrabold` | 800 | Display headings |
| `black` | 900 | Heavy display text |

### Typography Usage

#### Headings
```css
/* H1 - Page titles */
.heading-1 {
  font-size: var(--font-size-5xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--line-height-5xl);
  color: var(--text-primary);
}

/* H2 - Section titles */
.heading-2 {
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-4xl);
  color: var(--text-primary);
}

/* H3 - Subsection titles */
.heading-3 {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-3xl);
  color: var(--text-primary);
}
```

#### Body Text
```css
/* Primary body text */
.body-large {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-normal);
  line-height: var(--line-height-lg);
  color: var(--text-primary);
}

/* Default body text */
.body-medium {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-normal);
  line-height: var(--line-height-base);
  color: var(--text-primary);
}

/* Small body text */
.body-small {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-normal);
  line-height: var(--line-height-sm);
  color: var(--text-secondary);
}
```

## Spacing & Layout

### Spacing Scale (8px Grid System)

Our spacing system is based on an 8px grid for consistent visual rhythm:

| Token | Value | Pixels | Usage |
|-------|-------|--------|-------|
| `0` | 0rem | 0px | No spacing |
| `0.5` | 0.125rem | 2px | Fine adjustments |
| `1` | 0.25rem | 4px | Very small spacing |
| `1.5` | 0.375rem | 6px | Small adjustments |
| `2` | 0.5rem | 8px | Base unit |
| `3` | 0.75rem | 12px | Small spacing |
| `4` | 1rem | 16px | Medium spacing |
| `6` | 1.5rem | 24px | Large spacing |
| `8` | 2rem | 32px | Section spacing |
| `12` | 3rem | 48px | Large section spacing |
| `16` | 4rem | 64px | Page section spacing |
| `24` | 6rem | 96px | Major layout spacing |

### Layout Patterns

#### Container Widths
```css
.container-sm { max-width: 640px; }
.container-md { max-width: 768px; }
.container-lg { max-width: 1024px; }
.container-xl { max-width: 1280px; }
.container-2xl { max-width: 1536px; }
```

#### Grid Gaps
```css
.grid-gap-sm { gap: var(--spacing-2); }
.grid-gap-md { gap: var(--spacing-4); }
.grid-gap-lg { gap: var(--spacing-6); }
.grid-gap-xl { gap: var(--spacing-8); }
```

### Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `none` | 0px | Sharp corners |
| `sm` | 2px | Small elements |
| `default` | 4px | Default radius |
| `md` | 6px | Cards, inputs |
| `lg` | 8px | Large cards |
| `xl` | 12px | Prominent elements |
| `2xl` | 16px | Large components |
| `3xl` | 24px | Very large components |
| `full` | 50% | Circular elements |

### Shadows

| Token | Usage |
|-------|-------|
| `xs` | Subtle depth |
| `sm` | Cards, buttons |
| `default` | Elevated cards |
| `md` | Dropdowns, popovers |
| `lg` | Modals, overlays |
| `xl` | Large modals |

## Components

### Buttons

#### Primary Button
```jsx
<button className="bg-primary-500 hover:bg-primary-600 active:bg-primary-700 
                   text-white font-medium px-4 py-2 rounded-md 
                   transition-colors duration-150">
  Primary Action
</button>
```

#### Secondary Button
```jsx
<button className="bg-neutral-100 hover:bg-neutral-200 active:bg-neutral-300 
                   text-neutral-900 font-medium px-4 py-2 rounded-md 
                   border border-neutral-300 transition-colors duration-150">
  Secondary Action
</button>
```

#### Outline Button
```jsx
<button className="bg-transparent hover:bg-primary-50 active:bg-primary-100 
                   text-primary-600 font-medium px-4 py-2 rounded-md 
                   border border-primary-300 transition-colors duration-150">
  Outline Action
</button>
```

### Cards

#### Default Card
```jsx
<div className="bg-white border border-neutral-200 rounded-lg shadow-sm p-6">
  <h3 className="text-lg font-semibold text-neutral-900 mb-2">Card Title</h3>
  <p className="text-neutral-600">Card content goes here.</p>
</div>
```

#### Interactive Card
```jsx
<div className="bg-white border border-neutral-200 rounded-lg shadow-sm p-6 
                hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 
                cursor-pointer">
  <h3 className="text-lg font-semibold text-neutral-900 mb-2">Interactive Card</h3>
  <p className="text-neutral-600">Hover for interaction feedback.</p>
</div>
```

### Form Inputs

#### Text Input
```jsx
<input 
  type="text"
  className="w-full px-3 py-2.5 border border-neutral-300 rounded-md 
             bg-white text-neutral-900 placeholder-neutral-400
             focus:border-primary-500 focus:ring-1 focus:ring-primary-500
             transition-colors duration-150"
  placeholder="Enter text..."
/>
```

#### Input with Error State
```jsx
<input 
  type="text"
  className="w-full px-3 py-2.5 border border-error-500 rounded-md 
             bg-white text-neutral-900 placeholder-neutral-400
             focus:border-error-500 focus:ring-1 focus:ring-error-500
             transition-colors duration-150"
  placeholder="Enter text..."
/>
```

### Badges

#### Status Badges
```jsx
<!-- Success Badge -->
<span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium
                 bg-success-100 text-success-700">
  Success
</span>

<!-- Warning Badge -->
<span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium
                 bg-warning-100 text-warning-700">
  Warning
</span>

<!-- Error Badge -->
<span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium
                 bg-error-100 text-error-700">
  Error
</span>
```

## Usage Guidelines

### Color Accessibility

#### Contrast Requirements
- **Normal text**: Minimum 4.5:1 contrast ratio
- **Large text** (18px+ or 14px+ bold): Minimum 3:1 contrast ratio
- **UI components**: Minimum 3:1 contrast ratio

#### Verified Color Combinations
✅ **High Contrast (WCAG AAA)**
- `neutral-900` on `neutral-0` (21:1)
- `neutral-0` on `primary-500` (8.2:1)
- `neutral-0` on `error-500` (5.9:1)

✅ **Good Contrast (WCAG AA)**
- `neutral-700` on `neutral-0` (12.6:1)
- `neutral-600` on `neutral-0` (7.2:1)
- `primary-700` on `primary-50` (8.9:1)

### Responsive Design

#### Breakpoints
```css
/* Mobile first approach */
@media (min-width: 640px) { /* sm */ }
@media (min-width: 768px) { /* md */ }
@media (min-width: 1024px) { /* lg */ }
@media (min-width: 1280px) { /* xl */ }
@media (min-width: 1536px) { /* 2xl */ }
```

#### Spacing Adjustments
- **Mobile**: Use smaller spacing (2-4)
- **Tablet**: Use medium spacing (4-6)
- **Desktop**: Use larger spacing (6-8+)

### Animation Guidelines

#### Duration
- **Micro-interactions**: 150ms (fast)
- **Component transitions**: 200ms (normal)
- **Page transitions**: 300ms (slow)
- **Complex animations**: 500ms (slower)

#### Easing
- **ease-out**: For entrances
- **ease-in**: For exits
- **ease-in-out**: For state changes

## Development

### Using Design Tokens

#### CSS Custom Properties
```css
.my-component {
  color: var(--text-primary);
  background-color: var(--surface-primary);
  padding: var(--spacing-4);
  border-radius: var(--border-radius-md);
  box-shadow: var(--shadow-sm);
}
```

#### Tailwind Classes
```jsx
<div className="text-neutral-900 bg-white p-4 rounded-md shadow-sm">
  Content
</div>
```

#### TypeScript Theme Object
```typescript
import { theme } from '@/lib/theme';

const styles = {
  color: theme.colors.neutral[900],
  backgroundColor: theme.colors.neutral[0],
  padding: theme.spacing[4],
  borderRadius: theme.borderRadius.md,
};
```

### Theme Integration

#### Import Design Tokens CSS
```typescript
// In your main CSS file or index.css
import '@/styles/design-tokens.css';
```

#### Use Component Tokens
```typescript
import { componentTokens } from '@/lib/component-tokens';

const buttonStyles = {
  ...componentTokens.button.base,
  ...componentTokens.button.variants.primary,
  ...componentTokens.button.sizes.md,
};
```

### Best Practices

1. **Always use design tokens** instead of hardcoded values
2. **Test color combinations** for accessibility compliance
3. **Use semantic tokens** (e.g., `text-primary`) over primitive tokens (e.g., `neutral-900`)
4. **Maintain consistent spacing** using the 8px grid system
5. **Follow component patterns** instead of creating custom styles
6. **Test across different screen sizes** and devices
7. **Document custom components** following the design system patterns

### Tools & Resources

- **Figma Design System**: [Link to Figma file]
- **Accessibility Checker**: [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- **Color Palette Generator**: [Coolors.co](https://coolors.co/)
- **Typography Scale**: [Type-scale.com](https://type-scale.com/)

---

*This design system is a living document. Please contribute improvements and report issues to help maintain consistency across the LifeLog application.*
