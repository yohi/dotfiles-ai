# Global Variables
REQUIRE_NODEJS := 1
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PYTHON := uv run --with-requirements requirements.txt
