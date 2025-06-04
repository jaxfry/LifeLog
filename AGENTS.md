# LifeLog Agents Guide for AI Assistants

This `AGENTS.md` file provides comprehensive guidance for AI assistants (including GitHub Copilot, Claude, ChatGPT, and other AI coding agents) working with the LifeLog codebase. LifeLog is a personal activity tracking and analysis application that combines Python data processing with a modern React frontend.

## 🏗️ Project Architecture Overview

LifeLog follows a clean, modular architecture with clear separation between data processing, API, and frontend concerns:

```
LifeLog/                    # Core Python package for data processing
├── ingestion/              # Data import from ActivityWatch and other sources
├── enrichment/             # AI-powered timeline generation using LLMs
├── summary/                # Daily summary generation
├── storage/                # Data storage (raw, curated, cached)
├── models.py               # Pydantic data models
├── config.py               # Configuration using pydantic-settings
├── cli.py                  # Command-line interface
└── prompts.py              # LLM prompts for enrichment

backend/                    # FastAPI web API
├── app/
│   ├── main.py             # FastAPI application setup
│   └── routes/             # API endpoints (day, timeline, summary)

frontend/                   # React + TypeScript + Vite frontend
├── src/
│   ├── components/         # React components
│   ├── pages/              # Page-level components
│   ├── hooks/              # Custom React hooks
│   ├── api/                # API client functions
│   ├── shared/             # Utilities and theme
│   └── types.ts            # TypeScript type definitions

tests/                      # Python test suite using pytest
docs/                       # Documentation including design system
```

## 💻 Technology Stack

### Backend (Python)
- **Framework**: FastAPI for web API
- **Data Processing**: Polars for high-performance data manipulation
- **Validation**: Pydantic for data models and settings
- **AI Integration**: Support for google gemini
- **Testing**: pytest with fixtures and parametrized tests
- **Config**: Environment-based configuration with pydantic-settings

### Frontend (TypeScript/React)
- **Framework**: React 19 with TypeScript
- **Build Tool**: Vite for fast development and building
- **Styling**: TailwindCSS with custom design system
- **Animation**: Framer Motion for smooth animations
- **Icons**: Lucide React for consistent iconography
- **Routing**: React Router for navigation
- **State Management**: Custom hooks with React's built-in state

### Development Tools
- **Linting**: ESLint with TypeScript support
- **Type Checking**: TypeScript strict mode
- **Testing**: pytest for Python, frontend testing setup available
- **Version Control**: Git with comprehensive .gitignore

## 📝 Coding Conventions

### Python Code Standards
AI assistants should follow these Python conventions:

```python
# Use type hints consistently
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel

# Follow Pydantic patterns for data models
class TimelineEntry(BaseModel):
    start: datetime
    end: datetime
    activity: str
    project: Optional[str] = None
    notes: str
    
    class Config:
        # Include configuration as needed
        pass

# Use Polars for data processing (not pandas)
import polars as pl

# Configuration via pydantic-settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    raw_dir: Path = Path("LifeLog/storage/raw")
    model_name: str = "gemini-2.5-flash-preview-05-20"
```

**Key Python Guidelines:**
- Use Polars instead of pandas for data processing
- All datetime objects should be timezone-aware (prefer UTC)
- Use Pydantic models for data validation and serialization
- Follow the existing import organization (standard library, third-party, local)
- Use descriptive variable names and type hints
- Include docstrings for complex functions
- Use pathlib.Path for file system operations

### TypeScript/React Standards
AI assistants should follow these frontend conventions:

```tsx
// Use functional components with TypeScript
import React from 'react';
import type { TimelineEntry } from '../types';

interface TimelineProps {
  entries: TimelineEntry[];
  onEntryClick?: (entry: TimelineEntry) => void;
}

export function Timeline({ entries, onEntryClick }: TimelineProps) {
  // Component implementation
}

// Use custom hooks for state management
import { useDayData } from '../hooks/useDayData';

// Follow TailwindCSS utility-first approach
<div className="flex flex-col space-y-4 p-6 bg-neutral-50">
  <h2 className="text-2xl font-semibold text-neutral-900">
    Timeline
  </h2>
</div>
```

**Key Frontend Guidelines:**
- Use functional components with hooks (no class components)
- Always include TypeScript interfaces for props
- Use the custom design system colors and spacing
- Prefer composition over inheritance
- Use meaningful component and file names (PascalCase for components)
- Import types with `type` keyword: `import type { ... }`
- Use custom hooks for reusable logic
- Follow the existing animation patterns with Framer Motion

### CSS/Styling Guidelines
```css
/* Use CSS custom properties for design tokens */
:root {
  --color-primary-500: #8b5cf6;
  --color-neutral-50: #fafafa;
  --spacing-4: 1rem;
}

/* Follow BEM-like naming for custom CSS classes */
.timeline__entry {
  /* styles */
}

.timeline__entry--active {
  /* modifier styles */
}
```

**Styling Best Practices:**
- Use TailwindCSS utility classes as the primary styling method
- Reference design tokens via CSS custom properties
- Use custom CSS only when TailwindCSS utilities are insufficient
- Follow the established color palette and spacing system
- Ensure responsive design with mobile-first approach
- Maintain accessibility standards (WCAG 2.1 AA)

## 🧪 Testing Protocols

### Python Testing with pytest
Run tests using these commands:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_activitywatch.py

# Run with verbose output
pytest -v

# Run tests matching pattern
pytest -k "test_filtering"
```

**Testing Conventions:**
- Use pytest fixtures for test setup (see `conftest.py`)
- Use `tmp_path` fixture for file system tests
- Use `monkeypatch` for environment variable testing
- Parametrize tests when testing multiple scenarios
- Mock external dependencies (LLM calls, file system)
- Test both success and error cases

### Frontend Testing
```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run linting
npm run lint
```

**Frontend Testing Guidelines:**
- Test component rendering and interactions
- Mock API calls in tests
- Test accessibility features
- Validate TypeScript compilation
- Test responsive behavior

## 🚀 Development Workflow

### Getting Started
```bash
# Clone and setup
git clone <repository>
cd LifeLog

# Setup Python environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -e .

# Setup frontend
cd frontend
npm install

# Setup backend
cd ../backend
# Install dependencies as needed

# Run development servers
# Terminal 1: Frontend
cd frontend && npm run dev

# Terminal 2: Backend
cd backend && uvicorn app.main:app --reload

# Terminal 3: Data processing
cd LifeLog && python -m LifeLog.cli --help
```

### File Organization Patterns
When creating new files, follow these patterns:

**Python Files:**
- Models: `LifeLog/models.py` or dedicated files in modules
- API Routes: `backend/app/routes/<entity>.py`
- Data Processing: `LifeLog/<module>/<specific_function>.py`
- Tests: `tests/test_<module_name>.py`

**Frontend Files:**
- Components: `frontend/src/components/<ComponentName>.tsx`
- Pages: `frontend/src/pages/<PageName>.tsx`
- Hooks: `frontend/src/hooks/use<HookName>.ts`
- Types: Add to `frontend/src/types.ts` or create specific type files
- Utilities: `frontend/src/shared/<utility>.ts`

## 📋 Pull Request Guidelines

When AI assistants help create PRs, ensure they:

### PR Description Template
```markdown
## 🎯 Purpose
Brief description of what this PR accomplishes.

## 🔧 Changes Made
- [ ] Frontend changes (specify components/pages modified)
- [ ] Backend changes (specify API endpoints/models modified)
- [ ] Python data processing changes (specify modules modified)
- [ ] Test additions/modifications
- [ ] Documentation updates

## 🧪 Testing
- [ ] All existing tests pass
- [ ] New tests added for new functionality
- [ ] Manual testing completed for UI changes
- [ ] Data processing verified with sample data

## 📸 Screenshots (if applicable)
Include screenshots for UI changes.

## 🔗 Related Issues
Closes #[issue number]
```

### PR Checklist
- Follows established coding conventions
- Includes appropriate tests
- Updates documentation if needed
- Maintains backwards compatibility
- No breaking changes without clear justification
- Code is properly formatted and linted

## 🔍 Code Quality Checks

Before submitting changes, AI assistants should ensure:

### Python Quality Checks
```bash
# Type checking (if mypy is configured)
mypy LifeLog/

# Run tests
pytest

# Check imports and basic syntax
python -m py_compile LifeLog/**/*.py
```

### Frontend Quality Checks
```bash
# TypeScript compilation
npm run build

# Linting
npm run lint

# Check for unused dependencies
# (manual review recommended)
```

### Common Code Patterns

**Error Handling:**
```python
# Python: Use specific exceptions
try:
    result = process_data(data)
except ValidationError as e:
    log.error(f"Data validation failed: {e}")
    raise
except Exception as e:
    log.error(f"Unexpected error: {e}")
    raise
```

```tsx
// TypeScript: Handle async operations
try {
  const data = await fetchDayData(date);
  setTimelineData(data);
} catch (error) {
  console.error('Failed to fetch timeline data:', error);
  setError('Failed to load timeline data');
}
```

**Configuration Access:**
```python
# Python: Use Settings class
from LifeLog.config import Settings

settings = Settings()
model_name = settings.model_name
```

**API Integration:**
```tsx
// TypeScript: Use the API client
import { lifelogApi } from '../api/lifelog';

const data = await lifelogApi.getDayData(selectedDate);
```

## 🎨 Design System Integration

LifeLog includes a comprehensive design system. AI assistants should:

- Use design tokens defined in `frontend/src/styles/design-tokens.css`
- Follow the color palette and spacing system
- Reference the design system documentation in `docs/DESIGN_SYSTEM.md`
- Maintain consistency with existing component patterns
- Ensure accessibility standards are met

## 🤖 AI-Specific Guidelines

### LLM Integration
When working with LLM-related code:
- Understand that prompts are stored in `LifeLog/prompts.py`
- LLM responses are cached in `LifeLog/storage/cache/`
- Model configuration is managed through `Settings`
- Always handle LLM failures gracefully

### Data Processing
- Prefer Polars over pandas for performance
- Understand the data flow: Raw → Curated → Summary
- Respect timezone handling (UTC for storage, local for display)
- Use the existing caching mechanisms

### Frontend State Management
- Use custom hooks for complex state logic
- Leverage React's built-in state management
- Follow the established patterns for API data fetching
- Maintain component isolation and reusability

---

This `AGENTS.md` file should be updated as the codebase evolves. AI assistants should refer to this document for consistent code generation and modifications that align with the LifeLog project's architecture and conventions. If outdated, then good luck, I guess!