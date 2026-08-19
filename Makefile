PYTHON ?= python

.PHONY: test lint smoke

smoke:
	$(PYTHON) -m compileall src scripts

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m compileall src scripts
