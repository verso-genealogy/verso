# verso — the library's repository (verso-core, verso-ru). Every path here is this directory's.
#
#   make bootstrap      .venv with both distributions editable and the dev tools (requirements-dev.txt)
#   make ci             what CI runs, in its order (.github/workflows/ci.yml)

SHELL := /bin/bash
PY ?= $(CURDIR)/.venv/bin/python
SRC_PATH := $(CURDIR)/packages/verso-core/src:$(CURDIR)/packages/verso-ru/src
# The tests import the code from the two src/ and this directory (`tests`, `tools`), never an installed copy.
export PYTHONPATH := $(SRC_PATH):$(CURDIR)

.PHONY: bootstrap ci premerge test test-core lint ruff pyright ui-ratchet layering reference reference-check dsl-surface records-schema ui-schema standalone secrets-check build stamp

bootstrap:
	@if command -v uv >/dev/null 2>&1; then \
		[ -d .venv ] || uv venv --quiet --python 3.14 .venv; \
		uv pip install --quiet --python .venv/bin/python -e 'packages/verso-core[schema]' \
			-e 'packages/verso-ru[xlsx,sheets,dsl-tools]' -r requirements-dev.txt; \
	else \
		[ -d .venv ] || python3 -m venv .venv; \
		.venv/bin/pip install --quiet -e 'packages/verso-core[schema]' \
			-e 'packages/verso-ru[xlsx,sheets,dsl-tools]' -r requirements-dev.txt; \
	fi
	@echo "==> ready: $$(.venv/bin/python --version) in .venv"

ci: lint test test-core ui-ratchet layering reference-check dsl-surface records-schema ui-schema

# Before a merge or a release: what CI runs on a PR, and standalone, which it runs on main and not on a PR (ci.yml).
premerge: ci standalone

test:
	$(PY) -m pytest tests --doctest-modules -q

# The core alone: tests/core on the toy plugin with verso.ru blocked (tests/core/block.py).
test-core:
	$(PY) -m pytest -p tests.core.block tests/core -q

lint: ruff pyright

ruff:
	$(PY) -m ruff check .

pyright:
	$(PY) -m pyright -p pyrightconfig.json --pythonpath "$$($(PY) -c 'import sys; print(sys.executable)')"

# The interface's Cyrillic text only shrinks (tests/ui_text.py): `update=1` writes a fall down,
# `base=REV` holds the counts to REV's, as CI does.
ui-ratchet:
	$(PY) -m tests.ui_text $(if $(update),--update,$(if $(base),--base "$(base)",--check))

# The library's layers (tools/layers.toml, tools/layers.py).
layering:
	$(PY) -m tools.layers $(if $(update),--update) $(if $(base),--base "$(base)")

# docs/reference, written from the code (tools/reference.py): `check=1` says what is stale.
reference:
	$(PY) -m tools.reference $(if $(check),--check)

reference-check:
	$(PY) -m tools.reference --check

# The DSL's facade, written down (packages/verso-ru/src/verso/ru/dsl/api-v1.json): it only grows.
dsl-surface:
	$(PY) -m verso.core.cli --workspace tests/fixtures/workspace dsl-surface --check $(if $(base),--base "$(base)")

# records-v1.json is what the vocabulary says.
records-schema:
	cd tests/fixtures/workspace && $(PY) -m verso.core.records.schema --check

# ui-v1.json is what the vocabulary and the plugin's hints say.
ui-schema:
	cd tests/fixtures/workspace && $(PY) -m verso.core.records.ui --check

# The tests from `git archive HEAD` outside the checkout, from wheels in a clean venv, the sentinel on.
standalone:
	$(PY) tools/standalone.py $(if $(keep),--keep "$(keep)")

secrets-check:
	bash tools/secrets_check.sh

build:
	rm -rf dist && for d in packages/verso-core packages/verso-ru; do uv build --out-dir dist "$$d" || exit 1; done

# A version into both distributions at once: their `version` and the sister pin (tools/release.py).
stamp:
	$(if $(v),,$(error make stamp v=X.Y.Z))
	$(PY) tools/release.py stamp "$(v)"
