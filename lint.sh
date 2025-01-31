#!/usr/bin/env bash

# Run linter
poetry run ruff check
poetry run ruff format --check