PYTHON := .venv/bin/python
DATASET := data/demo/hdrplus-static
GATE0_ARTIFACTS := artifacts/gate0
GATE1_OUTPUT ?= artifacts/gate1/hdrplus-static
GATE1_CONFIG ?= configs/gate1.yaml

.PHONY: install contracts verify-gate0 human-verify-gate0 verify-gate1 human-verify-gate1 dev-processor dev-web

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
	$(PYTHON) -m pytest -q services/processor/tests/test_dataset.py services/processor/tests/test_doctor.py services/processor/tests/test_health.py
	npm run contracts:check
	npm run lint --workspaces --if-present
	npm run typecheck --workspaces --if-present
	npm run build --workspace apps/web
	@echo "GATE 0: PASS"

human-verify-gate0: verify-gate0
	@./scripts/run-gate0.sh

verify-gate1:
	$(PYTHON) -m ruff check services/processor
	$(PYTHON) -m photofold.cli benchmark --dataset $(DATASET) --config $(GATE1_CONFIG) --output $(GATE1_OUTPUT)
	$(PYTHON) -m photofold.cli verify-package $(GATE1_OUTPUT)/moment.photofold --output $(GATE1_OUTPUT)/package-verification.json
	$(PYTHON) -m photofold.cli export $(GATE1_OUTPUT)/moment.photofold --frame 0 --format webp --output artifacts/gate1/exported-000.webp
	$(PYTHON) -m pytest -q services/processor/tests/unit services/processor/tests/integration/test_gate1.py
	$(PYTHON) -m photofold.cli verify-report $(GATE1_OUTPUT)/report.html --expected-frames 7 --output $(GATE1_OUTPUT)/report-verification.json
	@echo "GATE 1: PASS"

human-verify-gate1: verify-gate1
	@echo "Gate 1 report ready: $(GATE1_OUTPUT)/report.html"
	@echo "Open it with: open $(GATE1_OUTPUT)/report.html"

dev-processor:
	$(PYTHON) -m uvicorn photofold.main:app --host 127.0.0.1 --port 8000 --reload

dev-web:
	npm run dev --workspace apps/web
