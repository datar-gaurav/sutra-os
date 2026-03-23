# Contributing to Sutra

Thank you for your interest in contributing to Sutra! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Git

### Quick Start (Docker)

The fastest way to get a development environment running:

```bash
git clone https://github.com/datar-gaurav/sutra.git
cd sutra
./start.sh --build
```

This starts PostgreSQL, Redis, the backend API, frontend, and Celery worker.

### Local Development (without Docker)

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
cp .env.example .env
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

You'll also need PostgreSQL 16+ and Redis 7+ running locally (or via Docker).

### Running Tests

```bash
# Backend
cd backend
pytest -v

# Frontend
cd frontend
npm run lint
```

### Code Style

**Backend:**
- We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Line length: 100 characters
- Target: Python 3.11

```bash
cd backend
ruff check .
ruff format .
```

**Frontend:**
- ESLint with the Next.js config
- TypeScript strict mode

```bash
cd frontend
npm run lint
```

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feat/agent-memory-search` — new feature
- `fix/streaming-disconnect` — bug fix
- `docs/api-examples` — documentation
- `refactor/tool-registry` — code improvement

### Commit Messages

Write clear, concise commit messages:
- Use imperative mood: "Add feature" not "Added feature"
- First line under 72 characters
- Reference issues when applicable: "Fix streaming timeout (#42)"

### Pull Request Process

1. Fork the repository and create your branch from `main`
2. Make your changes with tests where applicable
3. Run linting (`ruff check .` + `npm run lint`) and fix any issues
4. Update documentation if you changed public APIs or behavior
5. Open a PR with a clear description of what and why

### What Makes a Good PR

- **Small and focused** — one concern per PR
- **Tested** — include tests for new behavior
- **Documented** — update docs for user-facing changes
- **Clean history** — squash fixup commits before requesting review

## Reporting Issues

Use [GitHub Issues](https://github.com/datar-gaurav/sutra/issues) to report bugs or request features. Please include:

- **Bug reports:** Steps to reproduce, expected vs actual behavior, environment details
- **Feature requests:** Use case, proposed solution, alternatives considered

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
