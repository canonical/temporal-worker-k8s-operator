# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

# Makefile to help automate tasks

# build and dist folders
BUILD := build
DIST := dist

# The name of the python package/project
PY_PACKAGE := resource_sample

# Paths to venv executables
POETRY := poetry
PY := python3
PYTEST := pytest
BANDIT := bandit
BLACK := black
FLAKE8 := flake8
ISORT := isort
MYPY := mypy
PYLINT := pylint
PYDOCSTYLE := pydocstyle

.PHONY: help
help:  ## Print help about available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: run
run: ## Run the application
	$(POETRY) run $(PY) -m $(PY_PACKAGE)

.PHONY: install
install:
	$(POETRY) install --only main --no-root

# Development tools.
.PHONY: install-dev
install-dev:
	$(POETRY) install --with dev --no-root

.PHONY: lint
lint: ## Run linter
	$(POETRY) run $(FLAKE8) $(PY_PACKAGE) tests
	$(POETRY) run $(PYLINT) $(PY_PACKAGE) tests --disable=E0401,W1203,W0613,W0718,R0903,W1514,C0301,C0103,C0104,R0914,R0913,W0719,R0902
	$(POETRY) run $(ISORT) --check $(PY_PACKAGE) tests
	$(POETRY) run $(BLACK) --check $(PY_PACKAGE) tests
	$(POETRY) run $(BANDIT) --configfile pyproject.toml --quiet --recursive $(PY_PACKAGE) tests
	$(POETRY) run $(PYDOCSTYLE) $(PY_PACKAGE)

.PHONY: fmt
fmt: ## Reformat code for linter
	$(POETRY) run $(ISORT) $(PY_PACKAGE) tests
	$(POETRY) run $(BLACK) $(PY_PACKAGE) tests

.PHONY: test
test: ## Run tests
	$(POETRY) run $(PYTEST) --cov=$(PY_PACKAGE) tests

.PHONY: check
check: clean install-dev lint test  ## Runs linter and tests from a clean directory


# Release management.

.PHONY: changelog
changelog:  ## Add a new entry to the Changelog and bump the package version
	./scripts/update_changelog.sh

.PHONY: build
build: ## Create a Python source distribution and a wheel in dist
	$(POETRY) build

.PHONY: publish
publish: ## Publish the package to PYPI
	$(POETRY) publish

# Cleaning up.

.PHONY: clean-dist
clean-dist:
	rm -rf $(BUILD) $(DIST)

.PHONY: clean-pyc
clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	rm -rf .pytest_cache .coverage .mypy_cache

.PHONY: clean-venv
clean-venv:
	$(POETRY) env remove --all

.PHONY: clean
clean: clean-dist clean-pyc clean-venv  ## Clean up the virtualenv, Python bytecode and docs
	rm -rf *.egg-info
