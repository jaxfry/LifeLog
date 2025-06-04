# LifeLog Design System

## Quick Start

The LifeLog design system provides a comprehensive set of design tokens, components, and utilities for building consistent user interfaces.

### Setup

1. **CSS Tokens** are automatically imported via `src/index.css`
2. **TypeScript Tokens** are available via `src/lib/theme.ts`
3. **Component Tokens** are available via `src/lib/component-tokens.ts`
4. **Utilities** are available via `src/lib/design-system-utils.ts`

### View the Design System

Visit `/design-system` in your application to see a live showcase of all tokens and components.

## Core Concepts

### Design Tokens

Design tokens are the atomic values of our design system:

- **Primitive tokens**: Raw values (colors, spacing, typography)
- **Semantic tokens**: Meaningful, context-aware values
- **Component tokens**: Component-specific styling patterns

### Usage Patterns

#### 1. CSS Custom Properties (Recommended)
```css
.my-component {
  color: var(--text-primary);
  background-color: var(--surface-primary);
  padding: var(--spacing-4);
  border-radius: var(--border-radius-md);
}
```

#### 2. Tailwind Classes
```jsx
<div className="text-neutral-900 bg-white p-4 rounded-md shadow-sm">
  Content
</div>
```

#### 3. TypeScript Theme Object
```typescript
import { theme } from '@/lib/theme';

const styles = {
  color: theme.colors.neutral[900],
  backgroundColor: theme.colors.neutral[0],
  padding: theme.spacing[4],
};
```

## Color System

### Color Palettes

- **Primary**: Main brand colors (`primary-50` to `primary-950`)
- **Secondary**: Supporting accent colors (`secondary-50` to `secondary-950`)
- **Neutral**: Grayscale for text and backgrounds (`neutral-0` to `neutral-950`)
- **Success**: Green tones for positive states (`success-50` to `success-950`)
- **Warning**: Amber tones for caution states (`warning-50` to `warning-950`)
- **Error**: Red tones for error states (`error-50` to `error-950`)

### Semantic Colors

Use semantic color tokens for better maintainability:

```css
/* Text */
--text-primary      /* Main content text */
--text-secondary    /* Supporting text */
--text-tertiary     /* Captions, metadata */
--text-disabled     /* Disabled state text */
--text-link         /* Link color */

/* Backgrounds */
--background-primary    /* Main page background */
--background-secondary  /* Panel backgrounds */
--background-tertiary   /* Hover states */

/* Interactive */
--interactive-primary         /* Primary buttons */
--interactive-primary-hover   /* Primary button hover */
--interactive-danger          /* Destructive actions */
```

### Accessibility

All color combinations meet WCAG 2.1 AA contrast requirements:
- **Normal text**: 4.5:1 minimum contrast
- **Large text**: 3:1 minimum contrast
- **UI components**: 3:1 minimum contrast

## Typography

### Font Families

- **Sans Serif**: Inter (primary) - For UI text, headings, body content
- **Monospace**: Fira Code (secondary) - For code, data display

### Type Scale

| Size | Use Case |
|------|----------|
| `xs` (12px) | Captions, labels, metadata |
| `sm` (14px) | Small text, secondary content |
| `base` (16px) | Body text, default |
| `lg` (18px) | Large body text |
| `xl` (20px) | Subheadings |
| `2xl` (24px) | Section headings |
| `3xl` (30px) | Page headings |
| `4xl` (36px) | Large headings |
| `5xl` (48px) | Display headings |

### Font Weights

- `light` (300): Captions, subtle text
- `normal` (400): Body text default
- `medium` (500): Emphasis, button text
- `semibold` (600): Headings, strong emphasis
- `bold` (700): Important headings

## Spacing & Layout

### 8px Grid System

All spacing follows an 8px grid for visual rhythm:

```css
--spacing-1  /* 4px  - Fine adjustments */
--spacing-2  /* 8px  - Base unit */
--spacing-3  /* 12px - Small spacing */
--spacing-4  /* 16px - Medium spacing */
--spacing-6  /* 24px - Large spacing */
--spacing-8  /* 32px - Section spacing */
```

### Layout Containers

```css
.container-sm  /* 640px max-width */
.container-md  /* 768px max-width */
.container-lg  /* 1024px max-width */
.container-xl  /* 1280px max-width */
```

### Responsive Padding

- **Mobile**: `spacing-4` (16px)
- **Tablet**: `spacing-6` (24px)
- **Desktop**: `spacing-8` (32px)

## Components

### Buttons

```jsx
/* Primary */
<button className="bg-primary-500 hover:bg-primary-600 text-white px-4 py-2 rounded-md font-medium">
  Primary Action
</button>

/* Secondary */
<button className="bg-neutral-100 hover:bg-neutral-200 text-neutral-900 px-4 py-2 rounded-md border border-neutral-300 font-medium">
  Secondary Action
</button>

/* Outline */
<button className="bg-transparent hover:bg-primary-50 text-primary-600 px-4 py-2 rounded-md border border-primary-300 font-medium">
  Outline Action
</button>
```

### Form Inputs

```jsx
/* Default */
<input className="w-full px-3 py-2.5 border border-neutral-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500" />

/* Error State */
<input className="w-full px-3 py-2.5 border border-error-500 rounded-md focus:border-error-500 focus:ring-1 focus:ring-error-500" />
```

### Cards

```jsx
/* Default Card */
<div className="bg-white border border-neutral-200 rounded-lg shadow-sm p-6">
  Content
</div>

/* Interactive Card */
<div className="bg-white border border-neutral-200 rounded-lg shadow-sm p-6 hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer">
  Hover me
</div>
```

### Badges

```jsx
/* Status Badges */
<span className="px-2 py-1 rounded-full text-xs font-medium bg-success-100 text-success-700">Success</span>
<span className="px-2 py-1 rounded-full text-xs font-medium bg-warning-100 text-warning-700">Warning</span>
<span className="px-2 py-1 rounded-full text-xs font-medium bg-error-100 text-error-700">Error</span>
```

## Advanced Usage

### Using Design System Utilities

```typescript
import { designSystemUtils } from '@/lib/design-system-utils';

// Get color values
const primaryColor = designSystemUtils.getColor('primary.500');

// Build component styles
const buttonStyles = designSystemUtils.buildButtonStyles('primary', 'md');

// Create transitions
const transition = designSystemUtils.createTransition(['background-color', 'border-color'], 'normal', 'easeInOut');
```

### Custom Component Creation

```typescript
import { componentTokens } from '@/lib/component-tokens';

const MyButton = styled.button`
  ${componentTokens.button.base}
  ${componentTokens.button.variants.primary}
  ${componentTokens.button.sizes.md}
`;
```

### Responsive Design

```css
/* Mobile first approach */
.responsive-component {
  padding: var(--spacing-4);
}

@media (min-width: 768px) {
  .responsive-component {
    padding: var(--spacing-6);
  }
}

@media (min-width: 1024px) {
  .responsive-component {
    padding: var(--spacing-8);
  }
}
```

## Animation Guidelines

### Durations
- **Micro-interactions**: 150ms
- **Component transitions**: 200ms
- **Page transitions**: 300ms

### Easing
- **ease-out**: For entrances
- **ease-in**: For exits
- **ease-in-out**: For state changes

```css
.animated-element {
  transition: all var(--transition-duration-normal) var(--transition-timing-ease-out);
}
```

## Dark Mode Support

The design system includes automatic dark mode support via CSS custom properties:

```css
@media (prefers-color-scheme: dark) {
  :root {
    --text-primary: var(--color-neutral-100);
    --background-primary: var(--color-neutral-900);
    /* Other dark mode overrides */
  }
}
```

## File Structure

```
frontend/src/
├── lib/
│   ├── theme.ts                    # Core design tokens
│   ├── component-tokens.ts         # Component-specific tokens
│   └── design-system-utils.ts      # Utility functions
├── styles/
│   └── design-tokens.css          # CSS custom properties
├── components/
│   └── DesignSystemShowcase.tsx   # Live documentation
└── index.css                      # Global styles & imports
```

## Best Practices

### ✅ Do

- Use semantic tokens over primitive tokens
- Follow the 8px grid system for spacing
- Test color combinations for accessibility
- Use consistent component patterns
- Maintain design token hierarchy

### ❌ Don't

- Hardcode color or spacing values
- Create custom spacing that breaks the grid
- Use colors that fail contrast requirements
- Override component tokens without purpose
- Mix different design patterns

## Contributing

When adding new tokens or components:

1. Follow existing naming conventions
2. Update both CSS and TypeScript tokens
3. Add examples to the showcase component
4. Document usage patterns
5. Ensure accessibility compliance

## Browser Support

- Modern browsers (Chrome, Firefox, Safari, Edge)
- CSS custom properties required
- Graceful degradation for older browsers

---

For live examples and interactive documentation, visit `/design-system` in your application.
