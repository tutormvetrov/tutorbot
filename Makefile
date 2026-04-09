DEV_VENV ?= .venv-dev
ifeq ($(OS),Windows_NT)
BOOTSTRAP_PYTHON ?= py -3
DEV_PYTHON := $(DEV_VENV)/Scripts/python.exe
else
BOOTSTRAP_PYTHON ?= python3
DEV_PYTHON := $(DEV_VENV)/bin/python
endif
PYTHON ?= $(DEV_PYTHON)
PIP := $(PYTHON) -m pip
RUFF := $(PYTHON) -m ruff
MYPY := $(PYTHON) -m mypy
PYTEST := $(PYTHON) -m pytest
COMPILE_TARGETS := app.py loader.py data handlers keyboards states utils tests

.PHONY: install-dev validate-env lint typecheck test compile check healthcheck smoke backup restore

install-dev:
	$(BOOTSTRAP_PYTHON) -m venv $(DEV_VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-dev.txt

validate-env:
	$(PYTHON) scripts/validate_env.py --mode local

lint:
	$(RUFF) check .

typecheck:
	$(MYPY)

test:
	$(PYTEST)

compile:
	$(PYTHON) -m compileall -q $(COMPILE_TARGETS)

check: validate-env lint typecheck test compile

healthcheck:
	TUTORBOT_ROOT=$(CURDIR) $(PYTHON) scripts/healthcheck.py --mode local

smoke:
	TUTORBOT_ROOT=$(CURDIR) $(PYTHON) scripts/release_smoke.py --mode local

backup:
	TUTORBOT_ROOT=$(CURDIR) $(PYTHON) scripts/db_backup.py

restore:
	@echo "Use: TUTORBOT_ROOT=$(CURDIR) TUTORBOT_ALLOW_RESTORE=1 $(PYTHON) scripts/db_restore.py /path/to/backup.sql.gz"
