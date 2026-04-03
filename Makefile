BOOTSTRAP_PYTHON ?= python3
DEV_VENV ?= .venv-dev
PYTHON ?= $(DEV_VENV)/bin/python
PIP := $(DEV_VENV)/bin/python -m pip
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
	$(PYTHON) scripts/validate_env.py

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
	TUTORBOT_ROOT=$(CURDIR) ./scripts/healthcheck.sh

smoke:
	TUTORBOT_ROOT=$(CURDIR) ./scripts/release_smoke.sh

backup:
	TUTORBOT_ROOT=$(CURDIR) ./scripts/db_backup.sh

restore:
	@echo "Use: TUTORBOT_ROOT=$(CURDIR) TUTORBOT_ALLOW_RESTORE=1 ./scripts/db_restore.sh /path/to/backup.sql.gz"
