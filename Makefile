PYTHON ?= python3

.PHONY: test integration check

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

integration:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s integration_tests -v

check: test integration
