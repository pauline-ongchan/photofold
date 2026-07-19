PYTHON := .venv/bin/python
DATASET := data/demo/hdrplus-static
GATE0_ARTIFACTS := artifacts/gate0

.PHONY: install contracts verify-gate0 human-verify-gate0 dev-processor dev-web

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install --constraint services/processor/requirements.lock -e 'services/processor[dev]'
	npm ci

contracts:
	npm run contracts:generate

verify-gate0:
	@mkdir -p $(GATE0_ARTIFACTS)
	$(PYTHON) -m photofold.cli doctor --output $(GATE0_ARTIFACTS)/doctor.json
	$(PYTHON) -m photofold.cli validate-dataset $(DATASET) --output $(GATE0_ARTIFACTS)/dataset-validation.json
	$(PYTHON) -m ruff check services/processor
	$(PYTHON) -m pytest -q services/processor/tests
	npm run contracts:check
	npm run lint --workspaces --if-present
	npm run typecheck --workspaces --if-present
	npm run build --workspace apps/web
	@echo "GATE 0: PASS"

human-verify-gate0: verify-gate0
	@./scripts/run-gate0.sh

dev-processor:
	$(PYTHON) -m uvicorn photofold.main:app --host 127.0.0.1 --port 8000 --reload

dev-web:
	npm run dev --workspace apps/web
