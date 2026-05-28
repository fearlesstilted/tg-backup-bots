PY ?= .venv/bin/python

.PHONY: test check simulate health run

test:
	$(PY) -m unittest discover -s tests

check:
	$(PY) -m compileall app tests
	$(PY) -m unittest discover -s tests

simulate:
	$(PY) -m app.simulate_broadcast --db /tmp/tg_backup_sim.db --users 1000 --bot reviews --segment test

health:
	$(PY) -m app.healthcheck

run:
	$(PY) -m app.main
