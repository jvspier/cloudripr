.PHONY: build-web install-web test-web lint-web dev-web dev-backend dev-backend-sim build test test-backend test-frontend coverage check-upstream screenshots

install-web:
	cd web && npm ci

build-web: install-web
	cd web && npm run build

test-web:
	cd web && npm test

lint-web:
	cd web && npm run lint && npm run format

dev-web:
	cd web && npm run dev

dev-backend:
	uv run cloudripr --data-dir ./.dev-data --host 127.0.0.1 --port 8000

# Backend against the icloudpd simulator (no Apple account needed). Scenarios via
# ICLOUDPD_SIM_* env vars, see tests/fixtures/icloudpd_sim.py, e.g. ICLOUDPD_SIM_MODE=twofa.
dev-backend-sim:
	CLOUDRIPR_ICLOUDPD_CMD="$(CURDIR)/.venv/bin/python $(CURDIR)/tests/fixtures/icloudpd_sim.py" \
	  uv run cloudripr --data-dir ./.dev-data-sim --host 127.0.0.1 --port 8000

build: build-web
	uv build
	uv export --frozen --no-dev --no-emit-project -o dist/requirements.txt

test: test-backend test-frontend

test-backend:
	uv run pytest -q

test-frontend:
	cd web && npm test && npm run lint && npm run type-check

coverage:
	uv run pytest --cov-report=term --cov-report=html:.coverage-html

check-upstream:
	uv run icloudpd --version
	uv run pytest tests/engine/test_argv_real_binary.py -q --no-cov

# README images from a generated demo (never real photos): docs/images/
screenshots:
	uv run python scripts/screenshots/seed.py .screenshots-demo
	uv run --with playwright python scripts/screenshots/shoot.py .screenshots-demo docs/images
	rm -rf .screenshots-demo
