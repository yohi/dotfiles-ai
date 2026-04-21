#!/bin/bash
# Pre-push hook to run lightweight integrity tests

set -e

echo "--- Running Pre-push Integrity Checks ---"

# Run the integrity test via Makefile
if ! make test-integrity; then
    echo "FAILED: Integrity checks failed. Please fix the issues before pushing."
    exit 1
fi

# Run the linting via Makefile
if ! make lint; then
    echo "FAILED: Linting failed. Please fix the issues before pushing."
    exit 1
fi

echo "SUCCESS: Integrity checks passed."
exit 0
