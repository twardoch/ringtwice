#!/usr/bin/env bash
# build.sh - Build and test ringtwice
#
# Usage:
#   ./build.sh          # Run all checks and build
#   ./build.sh test     # Run tests only
#   ./build.sh lint     # Run linting only
#   ./build.sh build    # Build package only
#   ./build.sh docs     # Build documentation only
#   ./build.sh clean    # Clean build artifacts
#   ./build.sh all      # Run everything including docs

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Print colored message
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if uv is installed
check_uv() {
    if ! command -v uv &> /dev/null; then
        error "uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
}

# Sync dependencies
sync_deps() {
    info "Syncing dependencies..."
    uv sync --all-extras
    success "Dependencies synced"
}

# Run linting
run_lint() {
    info "Running ruff check..."
    uv run ruff check src tests
    success "Ruff check passed"

    info "Running ruff format check..."
    uv run ruff format --check src tests
    success "Ruff format check passed"
}

# Fix linting issues
run_fix() {
    info "Fixing linting issues..."
    uv run ruff check --fix src tests
    uv run ruff format src tests
    success "Linting issues fixed"
}

# Run type checking
run_typecheck() {
    info "Running mypy..."
    uv run mypy src/ringtwice || warn "Type errors found (non-blocking)"
}

# Run tests
run_tests() {
    info "Running tests..."
    uv run pytest --cov=src/ringtwice --cov-report=term-missing --cov-report=xml tests/
    success "Tests passed"
}

# Build package
run_build() {
    info "Building package..."
    uv build
    success "Package built in dist/"

    info "Checking package..."
    uv pip install twine --quiet
    uv run twine check dist/*
    success "Package check passed"
}

# Build documentation
run_docs() {
    info "Building documentation..."
    uv sync --extra docs
    # Copy markdown files to src_docs (zensical doesn't follow symlinks)
    mkdir -p src_docs
    cp README.md src_docs/index.md
    uv run zensical build --clean
    success "Documentation built in docs/"
}

# Serve documentation locally
serve_docs() {
    info "Serving documentation..."
    uv sync --extra docs
    # Copy markdown files to src_docs (zensical doesn't follow symlinks)
    mkdir -p src_docs
    cp README.md src_docs/index.md
    uv run zensical serve
}

# Clean build artifacts
run_clean() {
    info "Cleaning build artifacts..."
    rm -rf dist/ build/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov/
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    success "Cleaned"
}

# Show version
show_version() {
    info "Package version:"
    uv run python -c "from ringtwice._version import __version__; print(__version__)" 2>/dev/null || \
    uv run python -c "import importlib.metadata; print(importlib.metadata.version('ringtwice'))" 2>/dev/null || \
    warn "Version not available (package not installed or _version.py not generated)"
}

# Main entry point
main() {
    check_uv

    case "${1:-default}" in
        test)
            sync_deps
            run_tests
            ;;
        lint)
            sync_deps
            run_lint
            ;;
        fix)
            sync_deps
            run_fix
            ;;
        typecheck)
            sync_deps
            run_typecheck
            ;;
        build)
            sync_deps
            run_build
            ;;
        docs)
            run_docs
            ;;
        serve)
            serve_docs
            ;;
        clean)
            run_clean
            ;;
        version)
            show_version
            ;;
        all)
            sync_deps
            run_fix
            run_lint
            run_typecheck
            run_tests
            run_build
            run_docs
            show_version
            success "All checks passed!"
            ;;
        default)
            sync_deps
            run_fix
            run_lint
            run_typecheck
            run_tests
            run_build
            show_version
            success "All checks passed!"
            ;;
        *)
            echo "Usage: $0 {test|lint|fix|typecheck|build|docs|serve|clean|version|all}"
            echo ""
            echo "Commands:"
            echo "  test      - Run tests with coverage"
            echo "  lint      - Run linting checks"
            echo "  fix       - Fix linting issues automatically"
            echo "  typecheck - Run type checking with mypy"
            echo "  build     - Build package (sdist and wheel)"
            echo "  docs      - Build documentation with Zensical"
            echo "  serve     - Serve documentation locally"
            echo "  clean     - Remove build artifacts"
            echo "  version   - Show package version"
            echo "  all       - Run everything including docs"
            echo "  (default) - Run fix, lint, typecheck, test, build"
            exit 1
            ;;
    esac
}

main "$@"
