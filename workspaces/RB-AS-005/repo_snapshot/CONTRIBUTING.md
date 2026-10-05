# Contributing to AgentShield V3

Thank you for your interest in contributing to AgentShield V3. This document explains how to set up your development environment, run tests, and submit changes.

## Getting Started

### Prerequisites

- Python 3.11 or 3.12
- Git

### Setup

```bash
git clone <repo-url>
cd AgentShield_V3
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### Running the Server

```bash
# Standalone mode (port 8090)
cd backend && python app.py

# Full mode (port 8011)
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Follow existing code style and conventions.
- Keep changes focused: one feature or fix per branch.
- Add or update tests for any new functionality.

### 3. Run Tests

```bash
python -m pytest -q
```

For benchmark validation:

```bash
python benchmark/evaluate.py
python benchmark/evaluate_semireal.py
```

### 4. Commit

Use clear, descriptive commit messages:

```
feat(module): add new capability
fix(engine): correct risk score clamping
docs(readme): update API examples
test(routes): add edge case for session 404
```

### 5. Open a Pull Request

Push your branch and open a PR against `main`. Include:

- A summary of what changed and why.
- Any benchmark results if behavior was modified.
- Screenshots if UI changes were made.

## Project Structure

```
backend/
  app/
    api/routes.py          # FastAPI routes
    shield/v3_engine.py    # Core governance engine
    shield/agent_behavior_graph.py  # Behavior graph model
    shield/persistence.py  # Non-blocking SQLite persistence
    shield/redaction.py    # Credential redaction
    shield/session_store.py         # SQLite persistence
    shield/v3_audit_logger.py       # Audit chain logger
  tests/                   # All tests (pytest)
benchmark/                 # Benchmark scripts and datasets
docs/                      # Documentation (research/, papers/, experiments/)
frontend/                  # Static frontend
```

## Code Style

- Python 3.11+ syntax is acceptable.
- Use type hints where practical.
- Docstrings are encouraged for public functions.
- Do not commit `__pycache__`, `.pytest_cache`, `.venv`, `.env`, or `*.db` files.

## Reporting Issues

Open a GitHub issue with:

- A clear title and description.
- Steps to reproduce (if applicable).
- Expected vs actual behavior.
- Python version and OS.

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
