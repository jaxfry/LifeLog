# Contributing to LifeLog

We're excited that you're interested in contributing to LifeLog! This document outlines the process for contributing and provides guidelines to help you get started.

## 🎯 Ways to Contribute

### 🐛 Bug Reports
- Use the [GitHub Issues](https://github.com/yourusername/lifelog/issues) page
- Search existing issues first to avoid duplicates
- Include detailed reproduction steps
- Provide system information and logs when relevant

### 💡 Feature Requests
- Open a [GitHub Discussion](https://github.com/yourusername/lifelog/discussions) first
- Describe the problem you're trying to solve
- Provide examples of how the feature would be used
- Consider the impact on existing functionality

### 📝 Documentation
- Fix typos and improve clarity
- Add examples and use cases
- Update API documentation
- Create tutorials and guides

### 💻 Code Contributions
- Bug fixes
- Feature implementations
- Performance improvements
- Test coverage improvements

## 🚀 Getting Started

### 1. Fork and Clone
```bash
# Fork the repository on GitHub
git clone https://github.com/yourusername/lifelog.git
cd lifelog
git remote add upstream https://github.com/originalowner/lifelog.git
```

### 2. Set Up Development Environment
```bash
# Copy environment file
cp .env.example .env
# Edit .env with your configuration

# Start development services
docker-compose up -d postgres rabbitmq

# Install dependencies
pip install -r requirements.txt
cd frontend && npm install
```

### 3. Create a Branch
```bash
# Create and switch to a new branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

## 📋 Development Guidelines

### Code Style

#### Python
- **Black** for code formatting: `black .`
- **isort** for import sorting: `isort .`
- **flake8** for linting: `flake8 .`
- **mypy** for type checking: `mypy .`

```bash
# Format and lint Python code
black .
isort .
flake8 .
mypy .
```

#### TypeScript/React
- **ESLint** for linting: `npm run lint`
- **Prettier** for formatting: `npm run format`
- **TypeScript** strict mode enabled

```bash
cd frontend
npm run lint
npm run format
npm run type-check
```

### Commit Messages
Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add timeline filtering by project
fix: resolve authentication token expiry issue
docs: update API documentation for v1.1
test: add unit tests for timeline processor
refactor: simplify database connection handling
```

Types:
- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation changes
- `test`: Test additions/modifications
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Maintenance tasks

### Testing Requirements

#### Backend Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=central_server --cov-report=html

# Run specific test categories
pytest tests/api/
pytest tests/processing/
pytest tests/daemon/
```

#### Frontend Tests
```bash
cd frontend
npm test                    # Unit tests
npm run test:e2e           # End-to-end tests
npm run test:coverage      # Coverage report
```

#### Test Coverage
- Maintain >90% test coverage for new code
- Include both unit and integration tests
- Test error conditions and edge cases

### Documentation Requirements
- Update relevant documentation for new features
- Include docstrings for new functions/classes
- Update API documentation for endpoint changes
- Add examples for complex functionality

## 🔍 Code Review Process

### Before Submitting
1. **Self-review** your changes
2. **Run all tests** and ensure they pass
3. **Check code style** with linting tools
4. **Update documentation** as needed
5. **Rebase** on the latest main branch

### Pull Request Guidelines
- Use a clear, descriptive title
- Reference related issues with `Closes #123`
- Include a detailed description of changes
- Add screenshots for UI changes
- Keep PRs focused and reasonably sized

### Review Checklist
- [ ] Code follows project style guidelines
- [ ] Tests pass and coverage is maintained
- [ ] Documentation is updated
- [ ] No breaking changes (or properly documented)
- [ ] Security considerations addressed
- [ ] Performance impact considered

## 🏗️ Architecture Guidelines

### Backend Architecture
- **Microservices**: Keep services focused and loosely coupled
- **Async/Await**: Use async patterns for I/O operations
- **Type Hints**: Full type coverage for Python code
- **Error Handling**: Comprehensive error handling with proper logging

### Frontend Architecture
- **Component Structure**: Reusable, composable components
- **State Management**: Use React Context for global state
- **Type Safety**: Full TypeScript coverage
- **Accessibility**: Follow WCAG guidelines

### Database Guidelines
- **Migrations**: Always use proper migration scripts
- **Indexing**: Consider query performance implications
- **Normalization**: Follow database normalization principles
- **Security**: Use parameterized queries, avoid SQL injection

## 🚨 Security Guidelines

### General Security
- Never commit secrets or API keys
- Use environment variables for configuration
- Validate all inputs thoroughly
- Follow OWASP security guidelines

### API Security
- Implement proper authentication and authorization
- Use HTTPS in production
- Validate and sanitize all inputs
- Implement rate limiting where appropriate

### Database Security
- Use parameterized queries
- Implement proper access controls
- Regular security updates
- Backup encryption

## 🎯 Feature Development Process

### 1. Planning Phase
- Create GitHub issue with detailed requirements
- Discuss approach in issue comments
- Break down large features into smaller tasks
- Consider impact on existing functionality

### 2. Development Phase
- Create feature branch from main
- Implement functionality with tests
- Update documentation
- Regular commits with clear messages

### 3. Testing Phase
- Comprehensive unit tests
- Integration tests where applicable
- Manual testing of UI changes
- Performance testing for significant changes

### 4. Review Phase
- Self-review before submitting PR
- Address review feedback promptly
- Update based on maintainer suggestions
- Ensure CI/CD passes

## 📚 Resources

### Development Tools
- **VS Code Extensions**: Python, TypeScript, Docker, SQLTools
- **Database Tools**: pgAdmin, DBeaver, or similar
- **API Testing**: Postman, Insomnia, or curl
- **Docker**: For containerized development

### Learning Resources
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)

### Project-Specific Resources
- [API Documentation](http://localhost:8000/api/v1/docs)
- [Database Schema](postgres/init/02_schema.sql)
- [Frontend Component Library](frontend/src/components/ui/)

## 🤝 Community Guidelines

### Code of Conduct
- Be respectful and inclusive
- Welcome newcomers and help them get started
- Provide constructive feedback
- Focus on the code, not the person

### Communication
- Use clear, professional language
- Provide context for your suggestions
- Be patient with response times
- Ask questions when uncertain

## 📞 Getting Help

### Development Questions
- Check existing documentation first
- Search closed issues for similar problems
- Ask in GitHub Discussions for general questions
- Open an issue for specific bugs or problems

### Contact Maintainers
- **GitHub**: Open an issue or discussion
- **Email**: dev@lifelog.dev
- **Discord**: [Project Discord Server](https://discord.gg/lifelog)

## 🏆 Recognition

Contributors will be recognized in:
- **Contributors Section**: In the main README
- **Release Notes**: For significant contributions
- **Hall of Fame**: On the project website
- **Swag**: Stickers and merchandise for regular contributors

Thank you for contributing to LifeLog! Your efforts help make personal productivity tracking better for everyone.
