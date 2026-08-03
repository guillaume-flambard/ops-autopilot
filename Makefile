# Ops Autopilot - one-command local operations.
# Everything runs from the checked-out repo; no system installs required.

.PHONY: install run test coverage reset demo

install: ## Create the venv and install pinned deps
	uv venv
	uv pip install --python .venv/bin/python -r requirements.txt

run: ## Launch the Streamlit UI
	cp -n .env.example .env || true
	.venv/bin/streamlit run ui/app.py

test: ## Run the full test suite
	.venv/bin/python -m pytest -q

coverage: ## Test with coverage report + spec targets
	.venv/bin/python -m pytest -q \
		--cov=domain --cov=graph --cov=crew --cov=llm --cov=app --cov=db \
		--cov-report=term

reset: ## Delete the local SQLite DBs (app + checkpoints)
	rm -f ops_autopilot.db ops_autopilot_checkpoints.db
	@echo "Local SQLite databases removed."

demo: ## Offline 6-minute demo arc (mock LLM)
	.venv/bin/python -m graph.cli run --preset lumea --non-interactive
