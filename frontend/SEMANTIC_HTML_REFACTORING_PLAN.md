# Semantic HTML Refactoring Plan

## Overview
This document outlines the refactoring plan to improve semantic HTML usage across the LifeLog frontend application.

## Priority 1: Layout Semantic Structure

### 1.1 DayLayout Component Improvements

#### Current Issues:
- Generic `<div>` elements used for main content areas
- Missing semantic landmarks (`<main>`, `<nav>`, `<header>`)
- Poor accessibility for screen readers

#### Proposed Changes:

```tsx
// Before (DayLayout.tsx):
<div className="h-screen w-full flex overflow-hidden">
  <aside className="w-72">
    <div className="p-5 flex items-center gap-3">
      <h1>TimeFlow</h1>
    </div>
    <div className="mt-6 px-5">
      {/* Calendar */}
    </div>
  </aside>
  <div className="flex flex-1">
    <div className="flex-1">
      <Timeline />
    </div>
  </div>
</div>

// After (Semantic Structure):
<div className="h-screen w-full flex overflow-hidden">
  <aside className="w-72" aria-label="Application sidebar">
    <header className="p-5 flex items-center gap-3">
      <h1>TimeFlow</h1>
    </header>
    <nav className="mt-6 px-5" aria-label="Date navigation">
      {/* Calendar */}
    </nav>
    <section className="mt-auto" aria-label="Daily statistics">
      {/* Focus time, break time stats */}
    </section>
  </aside>
  <main className="flex flex-1" role="main">
    <section className="flex-1" aria-label="Activity timeline">
      <Timeline />
    </section>
    <aside className="w-80" aria-label="AI insights">
      <AIInsights />
    </aside>
  </main>
</div>
```

### 1.2 ActivityCard Semantic Structure

#### Current Issues:
- Activity cards use generic `<div>` elements
- Missing semantic structure for each activity entry

#### Proposed Changes:

```tsx
// Before:
<div className="flex rounded-lg border">
  <div className="p-4 flex-1">
    <div className="flex items-center justify-between">
      <div>{formatTime(start)} - {formatTime(end)}</div>
      <div>{duration}</div>
    </div>
    <div className="flex gap-3">
      <div className="flex-1">
        <h3>{entry.activity}</h3>
        <p>{entry.summary}</p>
      </div>
    </div>
  </div>
</div>

// After:
<article className="flex rounded-lg border" aria-label={`Activity: ${entry.activity}`}>
  <div className="p-4 flex-1">
    <header className="flex items-center justify-between">
      <time dateTime={start.toISOString()}>
        {formatTime(start)} - {formatTime(end)}
      </time>
      <span className="font-medium" aria-label={`Duration: ${duration}`}>
        {duration}
      </span>
    </header>
    <div className="flex gap-3">
      <div className="flex-1">
        <h3>{entry.activity}</h3>
        <p>{entry.summary}</p>
        {entry.tags && (
          <ul className="flex flex-wrap gap-1 mt-2" role="list" aria-label="Activity tags">
            {entry.tags.map((tag) => (
              <li key={tag}>
                <span className="px-2 py-0.5 text-xs rounded-full" role="tag">
                  {tag}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  </div>
</article>
```

## Priority 2: Component Consolidation

### 2.1 DayLayout Component Consolidation

#### Issue:
Two similar DayLayout implementations exist:
- `/src/layouts/DayLayout.tsx`
- `/src/components/layout/DayLayout.tsx`

#### Proposed Solution:
1. Analyze differences between the two implementations
2. Merge into a single, comprehensive component
3. Move to `/src/components/layout/DayLayout.tsx`
4. Update all imports to use the consolidated version

### 2.2 Status Message Components

#### Issue:
`CenteredMessage` and `EmptyState` components are defined inline in multiple files

#### Proposed Solution:
Create reusable components in `/src/components/ui/StatusMessages.tsx`:

```tsx
// /src/components/ui/StatusMessages.tsx
export function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        {children}
      </div>
    </div>
  );
}

export function EmptyState({ 
  message, 
  actionLabel, 
  action 
}: {
  message: string;
  actionLabel: string;
  action?: () => void;
}) {
  return (
    <section className="flex-1 flex items-center justify-center" role="status">
      <div className="text-center">
        <p className="text-lg text-neutral-600 mb-4">{message}</p>
        {action && (
          <button 
            onClick={action}
            className="px-4 py-2 bg-primary-500 text-white rounded-md hover:bg-primary-600"
          >
            {actionLabel}
          </button>
        )}
      </div>
    </section>
  );
}
```

## Priority 3: Design Token Consistency

### 3.1 Hardcoded Color Removal

#### Remaining Issues:
- `bg-indigo-600` → Should use `bg-primary-600` or design token
- `text-gray-800` → Should use semantic token like `text-secondary`
- Inconsistent gradient usage

#### Proposed Changes:
1. Audit all components for hardcoded colors
2. Replace with appropriate design tokens
3. Update Tailwind config to include all design token colors

### 3.2 Typography Consistency

#### Issues:
- Mixed usage of Tailwind typography classes and design tokens
- Inconsistent heading hierarchy

#### Proposed Solution:
Create typography utility classes that use design tokens:

```css
.heading-page { 
  @apply text-heading-1 text-primary; 
}
.heading-section { 
  @apply text-heading-2 text-primary; 
}
.text-body-primary { 
  @apply text-body text-primary; 
}
.text-body-secondary { 
  @apply text-body text-secondary; 
}
```

## Priority 4: Accessibility Improvements

### 4.1 ARIA Labels and Roles

#### Add missing ARIA attributes:
- `role="main"` for main content areas
- `aria-label` for navigation sections
- `role="status"` for loading/empty states
- `role="list"` and `role="listitem"` for tag collections

### 4.2 Keyboard Navigation

#### Ensure all interactive elements are keyboard accessible:
- Focus indicators for all buttons
- Tab order follows logical flow
- Skip links for main content

### 4.3 Screen Reader Support

#### Improve screen reader experience:
- Semantic HTML structure
- Descriptive link text
- Time elements with proper datetime attributes
- Status announcements for dynamic content

## Implementation Timeline

### Phase 1 (Week 1):
- [ ] Consolidate DayLayout components
- [ ] Create reusable StatusMessage components
- [ ] Update Timeline component semantic structure

### Phase 2 (Week 2):
- [ ] Implement ActivityCard semantic improvements
- [ ] Add ARIA labels and roles
- [ ] Remove remaining hardcoded colors

### Phase 3 (Week 3):
- [ ] Typography consistency improvements
- [ ] Accessibility testing and fixes
- [ ] Documentation updates

## Testing Checklist

- [ ] Screen reader testing (NVDA, JAWS, VoiceOver)
- [ ] Keyboard navigation testing
- [ ] Color contrast validation
- [ ] Semantic HTML validation
- [ ] TypeScript compilation without errors
- [ ] Visual regression testing

## Success Metrics

- 100% semantic HTML landmarks
- All color values using design tokens
- WCAG 2.1 AA compliance
- Reduced code duplication
- Improved maintainability scores
